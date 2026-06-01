"""LILAC 集成测试"""

import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestParserIntegration:
    """LilacParser 端到端集成测试"""

    def _make_parser(self, tmp_cache_db):
        os.environ["LILAC_CACHE_DB_PATH"] = tmp_cache_db
        os.environ["LILAC_ENABLE_LLM"] = "false"
        os.environ["LILAC_ENABLE_DRAIN3"] = "false"
        from server.diagnose.lilac.config import LilacConfig
        from server.diagnose.lilac.parser import LilacParser
        return LilacParser(LilacConfig())

    def test_cache_warmup_then_hit(self, tmp_cache_db):
        from server.diagnose.lilac.models import LogTemplate
        parser = self._make_parser(tmp_cache_db)

        tpl = LogTemplate.from_template_str("User <*> logged in from <*>", source="seed")
        parser.get_cache().insert(tpl)

        content = "\n".join([
            "2024-01-01 10:00:00 INFO User alice logged in from 192.168.1.1",
            "2024-01-01 10:00:01 INFO User bob logged in from 10.0.0.5",
            "2024-01-01 10:00:02 INFO User charlie logged in from 172.16.0.1",
        ])
        result = parser.parse_content(content)
        assert result.cache_hits == 3
        assert result.llm_calls == 0

    @patch("server.utils.get_ChatOpenAI")
    def test_llm_path_with_mock(self, mock_get_llm, tmp_cache_db):
        mock_llm = MagicMock()
        mock_llm.predict.return_value = '{"template": "Error connecting to <*> on port <*>", "variables": ["192.168.1.100", "5432"]}'
        mock_get_llm.return_value = mock_llm

        os.environ["LILAC_CACHE_DB_PATH"] = tmp_cache_db
        os.environ["LILAC_ENABLE_LLM"] = "true"
        os.environ["LILAC_ENABLE_DRAIN3"] = "false"
        from server.diagnose.lilac.config import LilacConfig
        from server.diagnose.lilac.parser import LilacParser
        parser = LilacParser(LilacConfig())

        entry = parser.parse_line("2024-01-01 10:00:00 ERROR Error connecting to 192.168.1.100 on port 5432")
        assert entry.template is not None
        assert entry.template.source == "llm"
        assert "<*>" in entry.template.template_str

    @patch("server.utils.get_ChatOpenAI", side_effect=Exception("timeout"))
    def test_llm_failure_graceful(self, mock_get_llm, tmp_cache_db):
        os.environ["LILAC_CACHE_DB_PATH"] = tmp_cache_db
        os.environ["LILAC_ENABLE_LLM"] = "true"
        os.environ["LILAC_ENABLE_DRAIN3"] = "false"
        from server.diagnose.lilac.config import LilacConfig
        from server.diagnose.lilac.parser import LilacParser
        parser = LilacParser(LilacConfig())

        entry = parser.parse_line("2024-01-01 10:00:00 ERROR Connection to 10.0.0.5 failed after 30s")
        # LLM init fails, no drain3 → template should be None for variable-containing lines
        assert entry.template is None
        assert "Connection to" in entry.message

    def test_parse_file(self, tmp_cache_db, sample_logs_dir):
        parser = self._make_parser(tmp_cache_db)
        syslog_path = os.path.join(sample_logs_dir, "syslog_sample.log")
        result = parser.parse_file(syslog_path)

        assert len(result.entries) > 0
        for e in result.entries:
            assert e.raw_text
            assert e.timestamp or e.message

    def test_to_sundb_log_entry_conversion(self, tmp_cache_db):
        from server.diagnose.lilac.models import to_sundb_log_entry
        parser = self._make_parser(tmp_cache_db)

        entry = parser.parse_line(
            "[2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] "
            "[INFORMATION] Database started"
        )
        sundb_entry = to_sundb_log_entry(entry)

        assert sundb_entry.timestamp == "2024-03-12 15:49:05.591941"
        assert sundb_entry.instance == "G1N1"
        assert sundb_entry.thread_pid == 2586375
        assert sundb_entry.level == "INFORMATION"
        assert "Database started" in sundb_entry.message

    def test_concurrent_parse(self, tmp_cache_db):
        from server.diagnose.lilac.models import LogTemplate
        parser = self._make_parser(tmp_cache_db)

        tpl = LogTemplate.from_template_str("Request <*> processed in <*> ms", source="seed")
        parser.get_cache().insert(tpl)

        results = []

        def worker(idx):
            entry = parser.parse_line(f"2024-01-01 10:00:00 INFO Request {idx} processed in 42 ms")
            results.append(entry.template is not None)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)
        assert len(results) == 10

    def test_parse_result_metrics(self, tmp_cache_db):
        from server.diagnose.lilac.models import LogTemplate
        parser = self._make_parser(tmp_cache_db)

        tpl = LogTemplate.from_template_str("Status <*> OK", source="seed")
        parser.get_cache().insert(tpl)

        content = "2024-01-01 10:00:00 INFO Status 200 OK\n2024-01-01 10:00:01 INFO Unknown event occurred"
        result = parser.parse_content(content)

        assert result.cache_hits == 1
        assert result.parse_time_ms > 0
        assert len(result.entries) == 2
