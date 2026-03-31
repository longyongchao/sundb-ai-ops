"""
Tests for history API endpoints.
Source: server/diagnose/history_api.py
Endpoints: monitoring, alerts, statistics, trend, alerts/{id}/status
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGetMonitoringHistory:
    """GET /api/history/monitoring."""

    def test_default_params(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_repo:
            mock_repo.get_history.return_value = []
            resp = client.get("/api/history/monitoring")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_with_custom_hours(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_repo:
            mock_repo.get_history.return_value = [{"timestamp": "2026-01-01T00:00:00", "cpu_usage": 0.5}]
            resp = client.get("/api/history/monitoring", params={"hours": 48})
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]) == 1

    def test_with_start_end_time(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_repo:
            mock_repo.get_history.return_value = []
            resp = client.get("/api/history/monitoring", params={
                "start_time": "2026-01-01T00:00:00",
                "end_time": "2026-01-02T00:00:00",
            })
        assert resp.json()["code"] == 200

    def test_error_handling(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_repo:
            mock_repo.get_history.side_effect = Exception("DB error")
            resp = client.get("/api/history/monitoring")
        data = resp.json()
        assert data["code"] == 500


class TestGetAlertHistory:
    """GET /api/history/alerts."""

    def test_default_params(self, client):
        with patch("server.diagnose.history_api.AlertRepository") as mock_repo:
            mock_repo.get_alerts.return_value = []
            resp = client.get("/api/history/alerts")
        assert resp.json()["code"] == 200

    def test_filter_by_type(self, client):
        with patch("server.diagnose.history_api.AlertRepository") as mock_repo:
            mock_repo.get_alerts.return_value = [{"id": 1, "alert_type": "cpu"}]
            resp = client.get("/api/history/alerts", params={"alert_type": "cpu"})
        data = resp.json()
        assert data["code"] == 200

    def test_filter_by_level(self, client):
        with patch("server.diagnose.history_api.AlertRepository") as mock_repo:
            mock_repo.get_alerts.return_value = []
            resp = client.get("/api/history/alerts", params={"alert_level": "critical"})
        assert resp.json()["code"] == 200

    def test_error_handling(self, client):
        with patch("server.diagnose.history_api.AlertRepository") as mock_repo:
            mock_repo.get_alerts.side_effect = Exception("fail")
            resp = client.get("/api/history/alerts")
        assert resp.json()["code"] == 500


class TestGetHistoryStatistics:
    """GET /api/history/statistics."""

    def test_default_7days(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_mon:
            with patch("server.diagnose.history_api.AlertRepository") as mock_alert:
                mock_mon.get_statistics.return_value = {
                    "count": 100, "avg_cpu_usage": 0.4, "max_cpu_usage": 0.8,
                    "avg_memory_usage": 0.5, "max_memory_usage": 0.9,
                }
                mock_alert.get_statistics.return_value = {
                    "total_count": 10, "diagnosis_rate": 0.8,
                }
                mock_alert.get_active_alerts_count.return_value = 3
                resp = client.get("/api/history/statistics")
        data = resp.json()
        assert data["code"] == 200
        assert "monitoring" in data["data"]
        assert "alerts" in data["data"]
        assert "summary" in data["data"]

    def test_custom_days(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_mon:
            with patch("server.diagnose.history_api.AlertRepository") as mock_alert:
                mock_mon.get_statistics.return_value = {"count": 0, "avg_cpu_usage": 0, "max_cpu_usage": 0, "avg_memory_usage": 0, "max_memory_usage": 0}
                mock_alert.get_statistics.return_value = {"total_count": 0, "diagnosis_rate": 0}
                mock_alert.get_active_alerts_count.return_value = 0
                resp = client.get("/api/history/statistics", params={"days": 30})
        assert resp.json()["code"] == 200

    def test_error_handling(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_mon:
            mock_mon.get_statistics.side_effect = Exception("DB error")
            resp = client.get("/api/history/statistics")
        assert resp.json()["code"] == 500


class TestGetTrendData:
    """GET /api/history/trend."""

    def test_cpu_trend_with_data(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_repo:
            mock_repo.get_history.return_value = [
                {"timestamp": "2026-01-01T01:00:00", "cpu_usage": 0.45},
                {"timestamp": "2026-01-01T02:00:00", "cpu_usage": 0.60},
            ]
            resp = client.get("/api/history/trend", params={"metric_type": "cpu", "hours": 24})
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]["timestamps"]) == 2
        assert data["data"]["unit"] == "%"

    def test_trend_no_data(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_repo:
            mock_repo.get_history.return_value = []
            resp = client.get("/api/history/trend")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["timestamps"] == []

    def test_memory_trend(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_repo:
            mock_repo.get_history.return_value = [
                {"timestamp": "t1", "memory_usage": 0.7},
            ]
            resp = client.get("/api/history/trend", params={"metric_type": "memory"})
        assert resp.json()["code"] == 200

    def test_error_handling(self, client):
        with patch("server.diagnose.history_api.MonitoringRepository") as mock_repo:
            mock_repo.get_history.side_effect = Exception("fail")
            resp = client.get("/api/history/trend")
        assert resp.json()["code"] == 500


class TestUpdateAlertStatus:
    """PUT /api/history/alerts/{alert_id}/status."""

    def test_update_success(self, client):
        with patch("server.diagnose.history_api.AlertRepository") as mock_repo:
            mock_repo.update_status.return_value = True
            resp = client.put("/api/history/alerts/1/status", json={"status": "resolved"})
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["status"] == "resolved"

    def test_update_not_found(self, client):
        with patch("server.diagnose.history_api.AlertRepository") as mock_repo:
            mock_repo.update_status.return_value = False
            resp = client.put("/api/history/alerts/999/status", json={"status": "resolved"})
        data = resp.json()
        assert data["code"] == 404

    def test_update_error(self, client):
        with patch("server.diagnose.history_api.AlertRepository") as mock_repo:
            mock_repo.update_status.side_effect = Exception("DB error")
            resp = client.put("/api/history/alerts/1/status", json={"status": "resolved"})
        assert resp.json()["code"] == 500
