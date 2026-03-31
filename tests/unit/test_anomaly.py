"""
Tests for anomaly injection API endpoints.
Source: server/anomaly/api.py
Endpoints: inject, inject_async, types, eval results, add eval, clear eval
"""
import pytest
from unittest.mock import patch, MagicMock
import subprocess


class TestGetAnomalyTypes:
    """GET /api/anomaly/types — static list, no side effects."""

    def test_returns_types_list(self, client):
        resp = client.get("/api/anomaly/types")
        data = resp.json()
        assert data["code"] == 200
        types = data["data"]["types"]
        assert len(types) == 3
        values = [t["value"] for t in types]
        assert "slow_sql" in values
        assert "lock" in values
        assert "log" in values

    def test_types_have_required_fields(self, client):
        resp = client.get("/api/anomaly/types")
        for t in resp.json()["data"]["types"]:
            assert "value" in t
            assert "label" in t
            assert "description" in t
            assert "params" in t


class TestInjectAnomaly:
    """POST /api/anomaly/inject — sync injection."""

    def test_inject_success(self, client, mock_subprocess):
        mock_run, _ = mock_subprocess
        mock_run.return_value = MagicMock(returncode=0, stdout="injected OK", stderr="")
        resp = client.post("/api/anomaly/inject", json={
            "anomaly_type": "slow_sql",
            "duration": 10,
            "threads": 2,
            "count": 50,
        })
        data = resp.json()
        assert data["code"] == 200
        assert "成功" in data["msg"]
        assert data["data"]["type"] == "slow_sql"

    def test_inject_script_failure(self, client, mock_subprocess):
        mock_run, _ = mock_subprocess
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="script error")
        resp = client.post("/api/anomaly/inject", json={
            "anomaly_type": "lock",
            "duration": 5,
            "threads": 3,
            "count": 10,
        })
        data = resp.json()
        assert data["code"] == 500
        assert "失败" in data["msg"]

    def test_inject_timeout(self, client):
        with patch("server.anomaly.api.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            resp = client.post("/api/anomaly/inject", json={
                "anomaly_type": "log",
                "duration": 5,
                "threads": 1,
                "count": 100,
            })
        data = resp.json()
        assert data["code"] == 500
        assert "超时" in data["msg"]

    def test_inject_unexpected_exception(self, client):
        with patch("server.anomaly.api.subprocess.run", side_effect=FileNotFoundError("no script")):
            resp = client.post("/api/anomaly/inject", json={
                "anomaly_type": "slow_sql",
                "duration": 5,
                "threads": 1,
                "count": 10,
            })
        data = resp.json()
        assert data["code"] == 500


class TestInjectAnomalyAsync:
    """POST /api/anomaly/inject_async — async injection (returns immediately)."""

    def test_async_inject_returns_immediately(self, client):
        with patch("server.anomaly.api.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            resp = client.post("/api/anomaly/inject_async", json={
                "anomaly_type": "slow_sql",
                "duration": 30,
                "threads": 5,
                "count": 100,
            })
        data = resp.json()
        assert data["code"] == 200
        assert "已启动" in data["msg"]
        assert data["data"]["status"] == "running"


class TestEvaluationResults:
    """GET/POST/DELETE evaluation results CRUD."""

    def test_get_evaluation_results_empty(self, client):
        with patch("server.anomaly.api.evaluation_results", []):
            resp = client.get("/api/evaluation/results")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_get_evaluation_results_with_data(self, client):
        mock_results = [{"id": 1, "anomaly_type": "slow_sql", "is_hit": True}]
        with patch("server.anomaly.api.evaluation_results", mock_results):
            resp = client.get("/api/evaluation/results")
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]) == 1

    def test_add_evaluation_result(self, client):
        with patch("server.anomaly.api.evaluation_results", []):
            with patch("server.anomaly.api.save_evaluation_results"):
                resp = client.post("/api/evaluation/add", json={
                    "anomaly_type": "slow_sql",
                    "diagnosis_time": 12.5,
                    "root_cause": "Missing index",
                    "is_hit": True,
                    "suggestion": "Create index on table_a(col_b)",
                })
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["anomaly_type"] == "slow_sql"
        assert data["data"]["hit_status"] == "Hit"

    def test_add_evaluation_result_miss(self, client):
        with patch("server.anomaly.api.evaluation_results", []):
            with patch("server.anomaly.api.save_evaluation_results"):
                resp = client.post("/api/evaluation/add", json={
                    "anomaly_type": "lock",
                    "diagnosis_time": 5.0,
                    "root_cause": "Unknown",
                    "is_hit": False,
                    "suggestion": "Check locks",
                })
        data = resp.json()
        assert data["data"]["hit_status"] == "Miss"

    def test_add_evaluation_result_truncates_long_suggestion(self, client):
        with patch("server.anomaly.api.evaluation_results", []):
            with patch("server.anomaly.api.save_evaluation_results"):
                resp = client.post("/api/evaluation/add", json={
                    "anomaly_type": "log",
                    "diagnosis_time": 1.0,
                    "root_cause": "err",
                    "is_hit": True,
                    "suggestion": "x" * 200,
                })
        data = resp.json()
        assert data["data"]["suggestion"].endswith("...")
        assert len(data["data"]["suggestion"]) == 103

    def test_clear_evaluation_results(self, client):
        with patch("server.anomaly.api.evaluation_results", [{"id": 1}]):
            with patch("server.anomaly.api.save_evaluation_results"):
                resp = client.delete("/api/evaluation/clear")
        data = resp.json()
        assert data["code"] == 200
        assert "清空" in data["msg"]
