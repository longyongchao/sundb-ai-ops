"""LILAC API 端点测试"""

import io
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def client():
    """创建 FastAPI TestClient"""
    from fastapi.testclient import TestClient

    import server.diagnose.lilac_api as lilac_api
    lilac_api._parser = None

    from server.diagnose.lilac_api import (
        lilac_parse,
        lilac_parse_text,
        lilac_cache_stats,
        lilac_cache_templates,
        lilac_cache_clear,
        lilac_seed,
    )
    from fastapi import FastAPI

    app = FastAPI()
    app.post("/diagnose/lilac/parse")(lilac_parse)
    app.post("/diagnose/lilac/parse_text")(lilac_parse_text)
    app.get("/diagnose/lilac/cache/stats")(lilac_cache_stats)
    app.get("/diagnose/lilac/cache/templates")(lilac_cache_templates)
    app.delete("/diagnose/lilac/cache")(lilac_cache_clear)
    app.post("/diagnose/lilac/seed")(lilac_seed)

    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_env(tmp_cache_db):
    """确保每个测试使用临时缓存"""
    os.environ["LILAC_CACHE_DB_PATH"] = tmp_cache_db
    os.environ["LILAC_ENABLE_LLM"] = "false"
    os.environ["LILAC_ENABLE_DRAIN3"] = "false"
    import server.diagnose.lilac_api as lilac_api
    lilac_api._parser = None
    yield


class TestLilacParseEndpoint:
    """POST /diagnose/lilac/parse 测试"""

    def test_parse_file_upload(self, client, sample_logs_dir):
        syslog_path = os.path.join(sample_logs_dir, "syslog_sample.log")
        with open(syslog_path, "rb") as f:
            content = f.read()

        response = client.post(
            "/diagnose/lilac/parse",
            files={"file": ("syslog_sample.log", io.BytesIO(content), "text/plain")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total_entries"] > 0
        assert "cache_hits" in data["data"]
        assert "parse_time_ms" in data["data"]

    def test_parse_empty_file(self, client):
        response = client.post(
            "/diagnose/lilac/parse",
            files={"file": ("empty.log", io.BytesIO(b""), "text/plain")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total_entries"] == 0


class TestLilacParseTextEndpoint:
    """POST /diagnose/lilac/parse_text 测试"""

    def test_parse_text(self, client):
        response = client.post(
            "/diagnose/lilac/parse_text",
            json={"text": "2024-01-01 10:00:00 INFO Server started on port 8080"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total_entries"] == 1
        assert data["data"]["entries"][0]["message"] is not None

    def test_parse_multiline_text(self, client):
        text = "\n".join([
            "2024-01-01 10:00:00 INFO Request processed",
            "2024-01-01 10:00:01 ERROR Connection failed",
            "2024-01-01 10:00:02 INFO Retrying connection",
        ])
        response = client.post(
            "/diagnose/lilac/parse_text",
            json={"text": text},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_entries"] == 3

    def test_parse_text_with_parse_mode(self, client):
        response = client.post(
            "/diagnose/lilac/parse_text",
            json={
                "text": "2024-01-01 10:00:00 INFO Server started",
                "parse_mode": "drain3",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["parse_mode"] == "drain3"

    def test_parse_text_with_regex_and_parse_mode(self, client):
        response = client.post(
            "/diagnose/lilac/parse_text",
            json={
                "text": "2024-01-01 10:00:00 INFO User alice from 10.0.0.1",
                "parse_mode": "llm",
                "regex": [{"pattern": "alice", "replacement": "<*>"}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["parse_mode"] == "llm"
        assert data["data"]["entries"][0]["message"] == "User <*> from 10.0.0.1"


class TestLilacCacheEndpoints:
    """缓存相关端点测试"""

    def test_cache_stats(self, client):
        response = client.get("/diagnose/lilac/cache/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "total_templates" in data["data"]

    def test_cache_templates_empty(self, client):
        response = client.get("/diagnose/lilac/cache/templates")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 0
        assert data["data"]["templates"] == []

    def test_cache_templates_after_parse(self, client):
        client.post(
            "/diagnose/lilac/parse_text",
            json={"text": "2024-01-01 10:00:00 INFO Test message"},
        )

        response = client.get("/diagnose/lilac/cache/templates")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_cache_clear(self, client):
        client.post(
            "/diagnose/lilac/parse_text",
            json={"text": "2024-01-01 10:00:00 INFO Test message"},
        )

        response = client.delete("/diagnose/lilac/cache")
        assert response.status_code == 200
        assert response.json()["code"] == 200

        stats_resp = client.get("/diagnose/lilac/cache/stats")
        assert stats_resp.json()["data"]["total_templates"] == 0


class TestLilacSeedEndpoint:
    """POST /diagnose/lilac/seed 测试"""

    def test_seed_from_samples(self, client, sample_logs_dir):
        response = client.post(
            "/diagnose/lilac/seed",
            json={"sample_dir": sample_logs_dir},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["templates_added"] >= 0

    def test_seed_nonexistent_dir(self, client):
        response = client.post(
            "/diagnose/lilac/seed",
            json={"sample_dir": "/nonexistent/path"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["templates_added"] == 0
