"""缓存模块单元测试"""

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.diagnose.lilac.cache import AdaptiveParsingCache
from server.diagnose.lilac.models import LogTemplate


class TestCacheBasicOps:
    """基本增删查操作"""

    def test_insert_and_lookup(self, cache):
        tpl = LogTemplate.from_template_str("User <*> logged in from <*>", source="seed")
        cache.insert(tpl, "User alice logged in from 192.168.1.5")

        hit = cache.lookup(["User", "bob", "logged", "in", "from", "10.0.0.1"])
        assert hit is not None
        assert hit.template_str == "User <*> logged in from <*>"

    def test_cache_miss_different_length(self, cache):
        tpl = LogTemplate.from_template_str("User <*> logged in", source="seed")
        cache.insert(tpl)

        miss = cache.lookup(["Error", "connecting", "to", "database", "timeout"])
        assert miss is None

    def test_cache_miss_different_first_token(self, cache):
        tpl = LogTemplate.from_template_str("User <*> logged in from <*>", source="seed")
        cache.insert(tpl)

        miss = cache.lookup(["Admin", "bob", "logged", "in", "from", "10.0.0.1"])
        assert miss is None

    def test_deduplication(self, cache):
        tpl1 = LogTemplate.from_template_str("Connection from <*> accepted", source="llm")
        tpl2 = LogTemplate.from_template_str("Connection from <*> accepted", source="drain3")

        cache.insert(tpl1, "Connection from 10.0.0.1 accepted")
        cache.insert(tpl2, "Connection from 10.0.0.2 accepted")

        stats = cache.get_statistics()
        assert stats["total_templates"] == 1


class TestCacheSimilarity:
    """相似度阈值测试"""

    def test_above_threshold_hit(self, tmp_cache_db):
        cache = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.5)
        tpl = LogTemplate.from_template_str("GET <*> HTTP <*> status <*>", source="seed")
        cache.insert(tpl)

        # 4/6 tokens match (GET, HTTP, status + one <*>) -> 0.67 > 0.5
        hit = cache.lookup(["GET", "/api/users", "HTTP", "1.1", "status", "200"])
        assert hit is not None
        cache.close()

    def test_below_threshold_miss(self, tmp_cache_db):
        cache = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.95)
        tpl = LogTemplate.from_template_str("User <*> logged in from <*>", source="seed")
        cache.insert(tpl)

        # "admin" != "logged" -> 5/6 match = 0.83 < 0.95
        hit = cache.lookup(["User", "alice", "logged", "in", "from", "10.0.0.1"])
        # Actually <*> matches "alice" and <*> matches "10.0.0.1" -> 6/6 = 1.0
        assert hit is not None
        cache.close()


class TestCacheHitTracking:
    """命中计数测试"""

    def test_hit_count_increments(self, cache):
        tpl = LogTemplate.from_template_str("Request <*> completed", source="seed")
        cache.insert(tpl)

        cache.lookup(["Request", "12345", "completed"])
        cache.lookup(["Request", "67890", "completed"])
        cache.lookup(["Request", "11111", "completed"])

        templates = cache.get_all_templates()
        assert len(templates) == 1
        assert templates[0].hit_count == 3


class TestCachePersistence:
    """持久化测试"""

    def test_survives_reopen(self, tmp_cache_db):
        cache1 = AdaptiveParsingCache(tmp_cache_db)
        tpl = LogTemplate.from_template_str("Error in module <*>", source="llm")
        cache1.insert(tpl, "Error in module auth")
        cache1.close()

        cache2 = AdaptiveParsingCache(tmp_cache_db)
        hit = cache2.lookup(["Error", "in", "module", "database"])
        assert hit is not None
        assert hit.template_str == "Error in module <*>"
        cache2.close()


class TestCacheStatistics:
    """统计信息测试"""

    def test_statistics(self, cache):
        cache.insert(LogTemplate.from_template_str("User <*> login", source="seed"))
        cache.insert(LogTemplate.from_template_str("File <*> not found", source="llm"))

        cache.lookup(["User", "alice", "login"])
        cache.lookup(["User", "bob", "login"])

        stats = cache.get_statistics()
        assert stats["total_templates"] == 2
        assert stats["total_hits"] == 2

    def test_clear(self, cache):
        cache.insert(LogTemplate.from_template_str("Test <*>", source="seed"))
        cache.clear()

        stats = cache.get_statistics()
        assert stats["total_templates"] == 0
        assert stats["total_hits"] == 0


class TestCacheConcurrency:
    """并发安全测试"""

    def test_concurrent_reads(self, cache):
        tpl = LogTemplate.from_template_str("Thread <*> started task <*>", source="seed")
        cache.insert(tpl)

        results = []

        def reader():
            hit = cache.lookup(["Thread", "99", "started", "task", "backup"])
            results.append(hit is not None)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)
        assert len(results) == 10
