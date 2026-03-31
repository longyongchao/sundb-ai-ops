"""
Tests for report API endpoints.
Source: server/report/report.py
Endpoints: histories, histories(alias), llm_model_list, delete, clear, user_stats
"""
import pytest
import json
from unittest.mock import patch, MagicMock


class TestHistories:
    """GET /report/histories and GET /reports."""

    def test_histories_empty(self, client):
        with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", return_value=[]):
            with patch("server.db.repository.diagnosis_report_repository.get_report_by_record_id", return_value=None):
                resp = client.get("/report/histories")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_reports_alias_empty(self, client):
        with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", return_value=[]):
            with patch("server.db.repository.diagnosis_report_repository.get_report_by_record_id", return_value=None):
                resp = client.get("/reports")
        data = resp.json()
        assert data["code"] == 200

    def test_histories_with_records(self, client):
        records = [{
            "id": 1, "anomaly_type": "cpu_high", "status": "completed",
            "create_time": "2026-01-01T12:00:00", "confidence": 0.85,
            "anomaly_description": "CPU使用率异常", "anomaly_severity": "high",
            "root_causes": [{"type": "slow_sql", "description": "慢查询"}],
            "solutions": [{"action": "创建索引", "sql": "", "explanation": "优化查询"}],
            "diagnosis_time": 15,
        }]
        with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", return_value=records):
            with patch("server.db.repository.diagnosis_report_repository.get_report_by_record_id", return_value=None):
                resp = client.get("/report/histories")
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]) == 1
        assert data["data"][0]["anomaly_type"] == "cpu_high"

    def test_histories_db_error_still_returns(self, client):
        with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", side_effect=Exception("DB fail")):
            resp = client.get("/report/histories")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_histories_with_time_filter(self, client):
        with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", return_value=[]):
            resp = client.get("/report/histories", params={"start": "1700000000", "end": "1800000000"})
        assert resp.json()["code"] == 200


class TestDiagnoseLlmModelList:
    """GET /report/diagnose_llm_model_list."""

    def test_returns_model_list(self, client):
        resp = client.get("/report/diagnose_llm_model_list")
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)


class TestDeleteHistory:
    """DELETE /report/histories/{file_name}."""

    def test_delete_by_record_id(self, client):
        with patch("server.db.repository.diagnosis_record_repository.delete_diagnosis_record", return_value=True):
            with patch("server.db.repository.diagnosis_report_repository.delete_diagnosis_report_by_record_id", return_value=True):
                with patch("os.path.exists", return_value=False):
                    resp = client.delete("/report/histories/1.json")
        data = resp.json()
        assert data["code"] in (200, 404)

    def test_delete_nonexistent(self, client):
        with patch("server.db.repository.diagnosis_record_repository.delete_diagnosis_record", side_effect=Exception("not found")):
            with patch("server.db.repository.diagnosis_report_repository.delete_diagnosis_report_by_record_id", side_effect=Exception("not found")):
                with patch("os.path.exists", return_value=False):
                    resp = client.delete("/report/histories/nonexistent.json")
        data = resp.json()
        assert data["code"] == 404

    def test_delete_with_file(self, client, tmp_path):
        # Create a temp file to delete
        f = tmp_path / "test.json"
        f.write_text("{}")
        with patch("server.db.repository.diagnosis_record_repository.delete_diagnosis_record", return_value=True):
            with patch("server.db.repository.diagnosis_report_repository.delete_diagnosis_report_by_record_id", return_value=True):
                with patch("server.report.report.DIAGNOSTIC_RESULTS_PATH", str(tmp_path)):
                    resp = client.delete("/report/histories/1.json")
        data = resp.json()
        assert data["code"] in (200, 404)


class TestClearAllHistories:
    """DELETE /report/histories."""

    def test_clear_empty(self, client):
        with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", return_value=[]):
            with patch("os.path.exists", return_value=False):
                resp = client.delete("/report/histories")
        data = resp.json()
        assert data["code"] == 200

    def test_clear_with_records(self, client):
        records = [{"id": 1}, {"id": 2}]
        with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", return_value=records):
            with patch("server.db.repository.diagnosis_record_repository.delete_diagnosis_record", return_value=True):
                with patch("server.db.repository.diagnosis_report_repository.delete_diagnosis_report_by_record_id", return_value=True):
                    with patch("os.path.exists", return_value=False):
                        resp = client.delete("/report/histories")
        data = resp.json()
        assert data["code"] == 200


class TestGetUserStats:
    """GET /api/user/stats."""

    def test_stats_from_db(self, client):
        records = [
            {"id": 1, "anomaly_type": "cpu_high", "status": "completed",
             "created_at": "2026-01-01T12:00:00", "root_causes": []},
        ]
        with patch("server.db.repository.diagnosis_record_repository.count_diagnosis_records", return_value=1):
            with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", return_value=records):
                resp = client.get("/api/user/stats")
        data = resp.json()
        assert data["code"] == 200
        assert "total_diagnoses" in data["data"]
        assert "success_rate" in data["data"]
        assert "saved_reports" in data["data"]

    def test_stats_empty(self, client):
        with patch("server.db.repository.diagnosis_record_repository.count_diagnosis_records", return_value=0):
            with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", return_value=[]):
                resp = client.get("/api/user/stats")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total_diagnoses"] == 0
        assert data["data"]["success_rate"] == 0

    def test_stats_db_fallback_to_file(self, client, tmp_path):
        with patch("server.db.repository.diagnosis_record_repository.count_diagnosis_records", side_effect=Exception("DB fail")):
            with patch("server.db.repository.diagnosis_record_repository.list_diagnosis_records", side_effect=Exception("DB fail")):
                with patch("server.report.report.DIAGNOSTIC_RESULTS_PATH", str(tmp_path)):
                    resp = client.get("/api/user/stats")
        data = resp.json()
        assert data["code"] == 200
