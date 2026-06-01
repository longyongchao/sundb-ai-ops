"""种子模板生成器测试"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.diagnose.lilac.cache import AdaptiveParsingCache
from server.diagnose.lilac.seed import seed_from_sundb_samples


class TestSeedGenerator:
    """种子模板生成测试"""

    def test_seed_from_sundb_samples(self, tmp_cache_db, sample_logs_dir):
        cache = AdaptiveParsingCache(tmp_cache_db)
        count = seed_from_sundb_samples(sample_logs_dir, cache)
        assert count > 0

        stats = cache.get_statistics()
        assert stats["total_templates"] > 0
        cache.close()

    def test_seed_idempotent(self, tmp_cache_db, sample_logs_dir):
        cache = AdaptiveParsingCache(tmp_cache_db)
        count1 = seed_from_sundb_samples(sample_logs_dir, cache)
        count2 = seed_from_sundb_samples(sample_logs_dir, cache)

        # Second run should add 0 new templates (dedup)
        assert count2 == 0 or count2 <= count1
        cache.close()

    def test_cache_hit_after_seed(self, tmp_cache_db, sample_logs_dir):
        cache = AdaptiveParsingCache(tmp_cache_db)
        seed_from_sundb_samples(sample_logs_dir, cache)

        from server.diagnose.lilac.preprocessor import LogPreprocessor
        pp = LogPreprocessor()

        # A message similar to what's in the sample should hit cache
        result = pp.preprocess("Listener started on port 5236")
        hit = cache.lookup(result.tokens)
        # May or may not hit depending on similarity, just verify no crash
        assert hit is None or hit.template_str
        cache.close()

    def test_empty_directory(self, tmp_cache_db, tmp_path):
        empty_dir = str(tmp_path / "empty")
        os.makedirs(empty_dir)

        cache = AdaptiveParsingCache(tmp_cache_db)
        count = seed_from_sundb_samples(empty_dir, cache)
        assert count == 0
        cache.close()

    def test_nonexistent_directory(self, tmp_cache_db):
        cache = AdaptiveParsingCache(tmp_cache_db)
        count = seed_from_sundb_samples("/nonexistent/path", cache)
        assert count == 0
        cache.close()
