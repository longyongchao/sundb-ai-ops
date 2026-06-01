"""LILAC 测试共享 fixtures"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def tmp_cache_db(tmp_path):
    """临时 SQLite 缓存路径"""
    return str(tmp_path / "test_cache.db")


@pytest.fixture
def lilac_config(tmp_cache_db, monkeypatch):
    """使用临时 DB 的 LilacConfig"""
    monkeypatch.setenv("LILAC_CACHE_DB_PATH", tmp_cache_db)
    monkeypatch.setenv("LILAC_ENABLE_LLM", "false")
    monkeypatch.setenv("LILAC_ENABLE_DRAIN3", "false")
    from server.diagnose.lilac.config import LilacConfig
    return LilacConfig()


@pytest.fixture
def cache(tmp_cache_db):
    """临时 AdaptiveParsingCache 实例"""
    from server.diagnose.lilac.cache import AdaptiveParsingCache
    c = AdaptiveParsingCache(tmp_cache_db, similarity_threshold=0.85)
    yield c
    c.close()


@pytest.fixture
def preprocessor():
    """LogPreprocessor 实例"""
    from server.diagnose.lilac.preprocessor import LogPreprocessor
    return LogPreprocessor()


@pytest.fixture
def sample_sundb_system_log():
    """SunDB system.trc 样本日志行"""
    return (
        "[2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] "
        "[INFORMATION] [SERVER STARTUP] Database instance started successfully"
    )


@pytest.fixture
def sample_sundb_simple_log():
    """SunDB listener.trc 样本日志行"""
    return (
        "[2024-02-05 16:18:28.406162 THREAD(1347044,281465167431120)] "
        "Listener started on port 5236"
    )


@pytest.fixture
def sample_syslog():
    """标准 syslog 样本"""
    return "Mar 15 10:23:01 webserver01 nginx[12345]: GET /api/users 200 0.032s"


@pytest.fixture
def sample_iso_log():
    """ISO8601 带级别的日志行"""
    return "2024-03-15 10:23:05 ERROR Connection timeout on port 8080 from 192.168.1.100"


@pytest.fixture
def sample_logs_dir():
    """sample_logs 目录路径"""
    return os.path.join(os.path.dirname(__file__), "sample_logs")
