"""缓存模板合并 & 模糊查找单元测试"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.diagnose.lilac.cache import AdaptiveParsingCache
from server.diagnose.lilac.models import LogTemplate


@pytest.fixture
def merge_cache(tmp_cache_db):
    """启用合并的缓存实例"""
    c = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.85, merge_enabled=True)
    yield c
    c.close()


@pytest.fixture
def no_merge_cache(tmp_cache_db):
    """禁用合并的缓存实例"""
    c = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.85, merge_enabled=False)
    yield c
    c.close()


class TestTemplateMerge:
    """模板自动合并"""

    def test_numeric_suffix_merges(self, merge_cache):
        t1 = LogTemplate.from_template_str("[CDISPATCHER-S10] connecting member", source="llm")
        t2 = LogTemplate.from_template_str("[CDISPATCHER-S2] connecting member", source="llm")

        merge_cache.insert(t1)
        merge_cache.insert(t2)

        templates = merge_cache.get_all_templates()
        assert len(templates) == 1
        assert "<*>" in templates[0].template_str
        assert "connecting member" in templates[0].template_str

    def test_merged_template_matches_variants(self, merge_cache):
        t1 = LogTemplate.from_template_str("[CDISPATCHER-S10] connecting member", source="llm")
        t2 = LogTemplate.from_template_str("[CDISPATCHER-S2] connecting member", source="llm")

        merge_cache.insert(t1)
        merge_cache.insert(t2)

        hit = merge_cache.lookup(["[CDISPATCHER-S5]", "connecting", "member"])
        assert hit is not None
        assert "[CDISPATCHER-S<*>]" in hit.template_str

    def test_hit_count_accumulated(self, merge_cache):
        t1 = LogTemplate.from_template_str("worker-1 started", source="llm")
        t1.hit_count = 5
        t2 = LogTemplate.from_template_str("worker-2 started", source="llm")
        t2.hit_count = 3

        merge_cache.insert(t1)
        merge_cache.insert(t2)

        templates = merge_cache.get_all_templates()
        assert len(templates) == 1
        assert templates[0].hit_count == 8

    def test_multiple_diffs_no_merge(self, merge_cache):
        t1 = LogTemplate.from_template_str("user alice from host1", source="llm")
        t2 = LogTemplate.from_template_str("user bob from host2", source="llm")

        merge_cache.insert(t1)
        merge_cache.insert(t2)

        # 2 positions differ → no merge
        templates = merge_cache.get_all_templates()
        assert len(templates) == 2

    def test_non_numeric_diff_no_merge(self, merge_cache):
        t1 = LogTemplate.from_template_str("ERROR connection refused", source="llm")
        t2 = LogTemplate.from_template_str("WARNING connection refused", source="llm")

        merge_cache.insert(t1)
        merge_cache.insert(t2)

        # "ERROR" vs "WARNING" — not numeric-like (too long non-numeric)
        templates = merge_cache.get_all_templates()
        assert len(templates) == 2

    def test_merge_disabled(self, no_merge_cache):
        t1 = LogTemplate.from_template_str("[CDISPATCHER-S10] connecting", source="llm")
        t2 = LogTemplate.from_template_str("[CDISPATCHER-S2] connecting", source="llm")

        no_merge_cache.insert(t1)
        no_merge_cache.insert(t2)

        templates = no_merge_cache.get_all_templates()
        assert len(templates) == 2

    def test_merge_with_existing_wildcard(self, merge_cache):
        t1 = LogTemplate.from_template_str("session <*> on node-1", source="llm")
        t2 = LogTemplate.from_template_str("session <*> on node-2", source="llm")

        merge_cache.insert(t1)
        merge_cache.insert(t2)

        templates = merge_cache.get_all_templates()
        assert len(templates) == 1
        assert "node-<*>" in templates[0].template_str

    def test_merge_persists_to_db(self, tmp_cache_db):
        cache1 = AdaptiveParsingCache(tmp_cache_db, merge_enabled=True)
        t1 = LogTemplate.from_template_str("port-8080 listening", source="llm")
        t2 = LogTemplate.from_template_str("port-9090 listening", source="llm")
        cache1.insert(t1)
        cache1.insert(t2)
        cache1.close()

        cache2 = AdaptiveParsingCache(tmp_cache_db, merge_enabled=True)
        templates = cache2.get_all_templates()
        assert len(templates) == 1
        assert "<*>" in templates[0].template_str
        cache2.close()


class TestMergeTokensHelper:
    """_merge_tokens 和 _is_numeric_like 边界测试"""

    def test_both_wildcard(self):
        result = AdaptiveParsingCache._merge_tokens("<*>", "<*>")
        assert result == "<*>"

    def test_one_wildcard(self):
        result = AdaptiveParsingCache._merge_tokens("<*>", "hello")
        assert result == "<*>"

    def test_numeric_diff(self):
        result = AdaptiveParsingCache._merge_tokens("port-8080", "port-9090")
        assert result == "port-<*>"

    def test_no_common_prefix(self):
        result = AdaptiveParsingCache._merge_tokens("abc", "xyz")
        # Pure letters without digits on either side → no merge
        assert result is None

    def test_short_alnum_with_digits(self):
        result = AdaptiveParsingCache._merge_tokens("v1", "v2")
        assert result == "v<*>"

    def test_hex_digits_merge(self):
        # Both are hex but at least one has digits
        result = AdaptiveParsingCache._merge_tokens("0x1234", "0xABCD")
        assert result == "0x<*>"

    def test_long_non_numeric_refuses(self):
        result = AdaptiveParsingCache._merge_tokens("authentication", "authorization")
        assert result is None

    def test_is_numeric_like_digits(self):
        assert AdaptiveParsingCache._is_numeric_like("12345") is True

    def test_is_numeric_like_hex(self):
        assert AdaptiveParsingCache._is_numeric_like("dead1234") is True
        # Pure hex letters accepted (blocked at _is_variable_segment level if no digit in pair)
        assert AdaptiveParsingCache._is_numeric_like("deadbeef") is True

    def test_is_numeric_like_short_alnum(self):
        assert AdaptiveParsingCache._is_numeric_like("v2") is True
        # Pure letters without digits → rejected
        assert AdaptiveParsingCache._is_numeric_like("hello") is False

    def test_is_variable_segment_requires_digit(self):
        # Pure letters on both sides → no merge
        assert AdaptiveParsingCache._is_variable_segment("abc", "xyz") is False
        # One side has digit → OK
        assert AdaptiveParsingCache._is_variable_segment("abc", "12") is True
        # Both have digits → OK
        assert AdaptiveParsingCache._is_variable_segment("1a", "2b") is True

    def test_is_numeric_like_empty(self):
        assert AdaptiveParsingCache._is_numeric_like("") is True

    def test_is_numeric_like_long_string_refuses(self):
        assert AdaptiveParsingCache._is_numeric_like("verylongstring123") is False


class TestFuzzyLookup:
    """缓存模糊 ±1 token 查找"""

    def test_fuzzy_one_extra_token_hits(self, tmp_cache_db):
        cache = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.85)
        tpl = LogTemplate.from_template_str("took <*> ms", source="llm")
        cache.insert(tpl)

        # Log has 4 tokens, template has 3
        hit = cache.lookup(["took", "123", "ms", "elapsed"])
        assert hit is not None
        assert hit.template_str == "took <*> ms"
        cache.close()

    def test_fuzzy_one_fewer_token_hits(self, tmp_cache_db):
        cache = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.85)
        tpl = LogTemplate.from_template_str("request <*> completed OK", source="llm")
        cache.insert(tpl)

        # Log has 3 tokens, template has 4 — diff=1 → fuzzy kicks in
        # Skip "OK" in template → ["request", "<*>", "completed"] matches 3/3 * 0.95
        hit = cache.lookup(["request", "42", "completed"])
        assert hit is not None
        assert hit.template_str == "request <*> completed OK"
        cache.close()

    def test_fuzzy_diff_two_misses(self, tmp_cache_db):
        cache = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.85)
        tpl = LogTemplate.from_template_str("a b c d e", source="llm")
        cache.insert(tpl)

        # Log has 3 tokens vs template 5 → diff=2 → skip fuzzy
        hit = cache.lookup(["a", "b", "c"])
        assert hit is None
        cache.close()

    def test_exact_preferred_over_fuzzy(self, tmp_cache_db):
        cache = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.85)
        exact = LogTemplate.from_template_str("GET <*> HTTP <*>", source="llm")
        fuzzy = LogTemplate.from_template_str("GET <*> HTTP <*> OK", source="llm")
        cache.insert(exact)
        cache.insert(fuzzy)

        hit = cache.lookup(["GET", "/api", "HTTP", "1.1"])
        assert hit is not None
        assert hit.template_str == "GET <*> HTTP <*>"
        cache.close()
