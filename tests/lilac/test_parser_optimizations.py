"""批量去重 & 静态快捷路径单元测试"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestStaticShortcut:
    """静态行快捷路径 — 无变量的行跳过 LLM"""

    def _make_parser(self, tmp_cache_db):
        os.environ["LILAC_CACHE_DB_PATH"] = tmp_cache_db
        os.environ["LILAC_ENABLE_LLM"] = "false"
        os.environ["LILAC_ENABLE_DRAIN3"] = "false"
        from server.diagnose.lilac.config import LilacConfig
        from server.diagnose.lilac.parser import LilacParser
        return LilacParser(LilacConfig())

    def test_pure_static_line(self, tmp_cache_db):
        parser = self._make_parser(tmp_cache_db)
        entry = parser.parse_line("2024-01-01 10:00:00 INFO Startup SUNDB")
        assert entry.template is not None
        assert entry.template.source == "static"
        assert entry.template.template_str == "Startup SUNDB"

    def test_static_line_cached_on_second_call(self, tmp_cache_db):
        parser = self._make_parser(tmp_cache_db)
        parser.parse_line("2024-01-01 10:00:00 INFO Startup SUNDB")

        entry = parser.parse_line("2024-01-01 10:00:01 INFO Startup SUNDB")
        assert entry.metadata.get("_parse_source") == "cache"

    def test_variable_line_not_static(self, tmp_cache_db):
        parser = self._make_parser(tmp_cache_db)
        entry = parser.parse_line("2024-01-01 10:00:00 INFO Connected from 192.168.1.1")
        # Contains IP → preprocessor masks it → not static, falls to LLM/drain3
        # With both disabled → template is None
        assert entry.template is None

    def test_static_shortcuts_metric(self, tmp_cache_db):
        parser = self._make_parser(tmp_cache_db)
        content = "\n".join([
            "2024-01-01 10:00:00 INFO Server started",
            "2024-01-01 10:00:01 INFO Server started",
            "2024-01-01 10:00:02 INFO Database ready",
        ])
        result = parser.parse_content(content)
        # 2 unique static lines, 1 batch dedup
        assert result.static_shortcuts == 2
        assert result.batch_dedup == 1


class TestBatchDedup:
    """批量解析去重"""

    def _make_parser(self, tmp_cache_db):
        os.environ["LILAC_CACHE_DB_PATH"] = tmp_cache_db
        os.environ["LILAC_ENABLE_LLM"] = "false"
        os.environ["LILAC_ENABLE_DRAIN3"] = "false"
        from server.diagnose.lilac.config import LilacConfig
        from server.diagnose.lilac.parser import LilacParser
        return LilacParser(LilacConfig())

    def test_identical_lines_deduped(self, tmp_cache_db):
        from server.diagnose.lilac.models import LogTemplate
        parser = self._make_parser(tmp_cache_db)

        tpl = LogTemplate.from_template_str("User <*> logged in", source="seed")
        parser.get_cache().insert(tpl)

        content = "\n".join([
            "2024-01-01 10:00:00 INFO User alice logged in",
            "2024-01-01 10:00:01 INFO User alice logged in",
            "2024-01-01 10:00:02 INFO User alice logged in",
        ])
        result = parser.parse_content(content)
        assert result.cache_hits == 1
        assert result.batch_dedup == 2
        assert len(result.entries) == 3
        # All entries should have the same template
        for e in result.entries:
            assert e.template is not None
            assert e.template.template_str == "User <*> logged in"

    def test_different_lines_not_deduped(self, tmp_cache_db):
        parser = self._make_parser(tmp_cache_db)
        content = "\n".join([
            "2024-01-01 10:00:00 INFO Server started",
            "2024-01-01 10:00:01 INFO Database ready",
            "2024-01-01 10:00:02 INFO Cache warmed",
        ])
        result = parser.parse_content(content)
        assert result.batch_dedup == 0
        assert result.static_shortcuts == 3

    def test_entries_preserve_order(self, tmp_cache_db):
        parser = self._make_parser(tmp_cache_db)
        content = "\n".join([
            "2024-01-01 10:00:00 INFO Alpha event",
            "2024-01-01 10:00:01 INFO Beta event",
            "2024-01-01 10:00:02 INFO Alpha event",
        ])
        result = parser.parse_content(content)
        assert result.entries[0].message == "Alpha event"
        assert result.entries[1].message == "Beta event"
        assert result.entries[2].message == "Alpha event"

    def test_empty_lines_skipped(self, tmp_cache_db):
        parser = self._make_parser(tmp_cache_db)
        content = "2024-01-01 10:00:00 INFO Hello\n\n\n2024-01-01 10:00:01 INFO World"
        result = parser.parse_content(content)
        assert len(result.entries) == 2

    def test_large_batch_dedup(self, tmp_cache_db):
        parser = self._make_parser(tmp_cache_db)
        lines = ["2024-01-01 10:00:00 INFO Heartbeat OK"] * 100
        result = parser.parse_content("\n".join(lines))
        assert result.static_shortcuts == 1
        assert result.batch_dedup == 99
        assert len(result.entries) == 100
