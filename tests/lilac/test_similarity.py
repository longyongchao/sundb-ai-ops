"""相似度计算单元测试"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.diagnose.lilac.similarity import (
    _token_matches,
    token_similarity,
    token_similarity_fuzzy,
)


class TestTokenMatches:
    """_token_matches 单 token 匹配"""

    def test_exact_match(self):
        assert _token_matches("hello", "hello") is True

    def test_exact_mismatch(self):
        assert _token_matches("hello", "world") is False

    def test_wildcard_matches_anything(self):
        assert _token_matches("anything", "<*>") is True
        assert _token_matches("", "<*>") is True

    def test_embedded_wildcard_prefix(self):
        assert _token_matches("[SESSION:472][DDL", "[SESSION:<*>][DDL") is True
        assert _token_matches("[SESSION:99999][DDL", "[SESSION:<*>][DDL") is True

    def test_embedded_wildcard_mismatch(self):
        assert _token_matches("[OTHER:472][DDL", "[SESSION:<*>][DDL") is False

    def test_embedded_wildcard_suffix(self):
        assert _token_matches("file_v2.log", "file_<*>.log") is True
        assert _token_matches("file_v2.txt", "file_<*>.log") is False

    def test_embedded_wildcard_middle(self):
        assert _token_matches("CDISPATCHER-S10", "CDISPATCHER-S<*>") is True
        assert _token_matches("CDISPATCHER-S2", "CDISPATCHER-S<*>") is True
        assert _token_matches("XDISPATCHER-S2", "CDISPATCHER-S<*>") is False


class TestTokenSimilarity:
    """token_similarity 精确长度匹配"""

    def test_perfect_match(self):
        assert token_similarity(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_all_wildcards(self):
        assert token_similarity(["x", "y", "z"], ["<*>", "<*>", "<*>"]) == 1.0

    def test_partial_match(self):
        score = token_similarity(["GET", "/api", "200"], ["GET", "<*>", "200"])
        assert score == 1.0

    def test_one_mismatch(self):
        score = token_similarity(["a", "b", "c", "d"], ["a", "x", "c", "d"])
        assert score == 0.75

    def test_different_length_returns_zero(self):
        assert token_similarity(["a", "b"], ["a", "b", "c"]) == 0.0

    def test_empty_returns_zero(self):
        assert token_similarity([], []) == 0.0


class TestTokenSimilarityFuzzy:
    """token_similarity_fuzzy 模糊 ±1 匹配"""

    def test_same_length_delegates(self):
        score = token_similarity_fuzzy(["a", "b", "c"], ["a", "b", "c"])
        assert score == 1.0

    def test_one_extra_token_in_log(self):
        # log has 4 tokens, template has 3
        # Skip any one in log, best alignment: skip "extra" → ["took", "123", "ms"] vs ["took", "<*>", "ms"]
        score = token_similarity_fuzzy(
            ["took", "extra", "123", "ms"],
            ["took", "<*>", "ms"],
            penalty=0.95,
        )
        assert score == pytest.approx(1.0 * 0.95)

    def test_one_extra_token_in_template(self):
        # template has 4 tokens, log has 3
        score = token_similarity_fuzzy(
            ["error", "in", "module"],
            ["error", "in", "sub", "module"],
            penalty=0.95,
        )
        # best skip: skip "sub" → ["error", "in", "module"] matches 3/3
        assert score == pytest.approx(1.0 * 0.95)

    def test_length_diff_greater_than_one_returns_zero(self):
        score = token_similarity_fuzzy(["a", "b"], ["a", "b", "c", "d"])
        assert score == 0.0

    def test_penalty_applied(self):
        score = token_similarity_fuzzy(
            ["a", "b", "c", "d"],
            ["a", "b", "c"],
            penalty=0.90,
        )
        # Perfect 3/3 alignment * 0.90
        assert score == pytest.approx(1.0 * 0.90)

    def test_empty_sequences(self):
        assert token_similarity_fuzzy([], ["a"]) == 0.0
        assert token_similarity_fuzzy(["a"], []) == 0.0
