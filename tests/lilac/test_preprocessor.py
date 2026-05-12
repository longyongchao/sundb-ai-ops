"""预处理器单元测试"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.diagnose.lilac.preprocessor import LogPreprocessor, PLACEHOLDER


class TestHeaderStripping:
    """日志头剥离测试"""

    def test_sundb_system_header(self, preprocessor, sample_sundb_system_log):
        result = preprocessor.preprocess(sample_sundb_system_log)
        assert result.header_format == "sundb_system"
        assert result.header_fields["timestamp"] == "2024-03-12 15:49:05.591941"
        assert result.header_fields["instance"] == "G1N1"
        assert result.header_fields["thread_pid"] == "2586375"
        assert result.header_fields["thread_tid"] == "281464209690016"
        assert result.header_fields["level"] == "INFORMATION"

    def test_sundb_simple_header(self, preprocessor, sample_sundb_simple_log):
        result = preprocessor.preprocess(sample_sundb_simple_log)
        assert result.header_format == "sundb_simple"
        assert result.header_fields["timestamp"] == "2024-02-05 16:18:28.406162"
        assert result.header_fields["thread_pid"] == "1347044"
        assert "Listener" in result.body

    def test_syslog_header(self, preprocessor, sample_syslog):
        result = preprocessor.preprocess(sample_syslog)
        assert result.header_format == "syslog"
        assert result.header_fields["timestamp"] == "Mar 15 10:23:01"
        assert result.header_fields["hostname"] == "webserver01"
        assert result.header_fields["program"] == "nginx"
        assert result.header_fields["pid"] == "12345"

    def test_iso_level_header(self, preprocessor, sample_iso_log):
        result = preprocessor.preprocess(sample_iso_log)
        assert result.header_format == "iso_level"
        assert result.header_fields["timestamp"] == "2024-03-15 10:23:05"
        assert result.header_fields["level"] == "ERROR"
        assert "Connection timeout" in result.body

    def test_unknown_format(self, preprocessor):
        line = "Some random log without standard header"
        result = preprocessor.preprocess(line)
        assert result.header_format == "unknown"
        assert result.body == line


class TestRegexMasking:
    """正则掩码测试"""

    def test_mask_ipv4(self, preprocessor):
        result = preprocessor.preprocess("2024-01-01 10:00:00 INFO Connected from 192.168.1.100")
        assert PLACEHOLDER in result.masked_body
        assert "192.168.1.100" not in result.masked_body

    def test_mask_hex(self, preprocessor):
        result = preprocessor.preprocess("2024-01-01 10:00:00 INFO Memory at 0x7f4a2b3c freed")
        assert PLACEHOLDER in result.masked_body
        assert "0x7f4a2b3c" not in result.masked_body

    def test_mask_path(self, preprocessor):
        result = preprocessor.preprocess("2024-01-01 10:00:00 INFO Loading /usr/local/lib/sundb.so")
        assert PLACEHOLDER in result.masked_body
        assert "/usr/local/lib/sundb.so" not in result.masked_body

    def test_mask_uuid(self, preprocessor):
        result = preprocessor.preprocess(
            "2024-01-01 10:00:00 INFO Session a1b2c3d4-e5f6-7890-abcd-ef1234567890 created"
        )
        assert PLACEHOLDER in result.masked_body
        assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890" not in result.masked_body

    def test_mask_long_number(self, preprocessor):
        result = preprocessor.preprocess("2024-01-01 10:00:00 INFO Thread 281464209690016 started")
        assert PLACEHOLDER in result.masked_body
        assert "281464209690016" not in result.masked_body

    def test_short_numbers_preserved(self, preprocessor):
        result = preprocessor.preprocess("2024-01-01 10:00:00 INFO HTTP 500 error on port 80")
        # Short numbers (< 4 digits) should NOT be masked
        assert "500" in result.masked_body
        assert "80" in result.masked_body


class TestTokenization:
    """Token化测试"""

    def test_basic_tokenize(self, preprocessor):
        result = preprocessor.preprocess("2024-01-01 10:00:00 INFO User logged in")
        assert result.tokens == ["User", "logged", "in"]

    def test_empty_line(self, preprocessor):
        result = preprocessor.preprocess("")
        assert result.tokens == []
        assert result.token_count == 0
        assert result.first_token == ""

    def test_whitespace_only(self, preprocessor):
        result = preprocessor.preprocess("   \t  ")
        assert result.tokens == []

    def test_token_count_and_first(self, preprocessor):
        result = preprocessor.preprocess("2024-01-01 10:00:00 INFO Connection established successfully")
        assert result.token_count == len(result.tokens)
        assert result.first_token == result.tokens[0] if result.tokens else ""
