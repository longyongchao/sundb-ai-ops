"""
Tests for SunDB TRC API endpoints.
Source: server/diagnose/sundb_trc_api.py
Endpoints: upload_trc, upload_trc_directory, fault_events, timeline, aeu_list
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGetTrcFaultEvents:
    """GET /diagnose/trc/fault_events."""

    def test_empty_cache(self, client):
        with patch("server.diagnose.sundb_trc_api._last_faults", []):
            resp = client.get("/diagnose/trc/fault_events")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 0
        assert data["data"]["faults"] == []

    def test_with_faults(self, client):
        mock_fault = MagicMock()
        mock_fault.event_type = "FATAL"
        mock_fault.timestamp = "2026-01-01T12:00:00"
        mock_fault.instance = "G1N1"
        mock_fault.description = "Fatal error"
        mock_fault.error_code = "SDB-1001"
        mock_fault.severity = "critical"
        with patch("server.diagnose.sundb_trc_api._last_faults", [mock_fault]):
            resp = client.get("/diagnose/trc/fault_events")
        data = resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["faults"][0]["event_type"] == "FATAL"

    def test_filter_by_severity(self, client):
        f1 = MagicMock(event_type="FATAL", severity="critical", timestamp="t1",
                       instance="G1N1", description="", error_code="")
        f2 = MagicMock(event_type="WARN", severity="medium", timestamp="t2",
                       instance="G1N2", description="", error_code="")
        with patch("server.diagnose.sundb_trc_api._last_faults", [f1, f2]):
            resp = client.get("/diagnose/trc/fault_events", params={"severity": "critical"})
        data = resp.json()
        assert data["data"]["total"] == 1

    def test_filter_by_event_type(self, client):
        f1 = MagicMock(event_type="FATAL", severity="critical", timestamp="t1",
                       instance="G1N1", description="", error_code="")
        with patch("server.diagnose.sundb_trc_api._last_faults", [f1]):
            resp = client.get("/diagnose/trc/fault_events", params={"event_type": "DEADLOCK"})
        data = resp.json()
        assert data["data"]["total"] == 0


class TestGetTrcTimeline:
    """GET /diagnose/trc/timeline."""

    def test_empty_cache(self, client):
        with patch("server.diagnose.sundb_trc_api._last_entries", []):
            resp = client.get("/diagnose/trc/timeline")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 0

    def test_with_entries(self, client):
        entry = MagicMock()
        entry.timestamp = "2026-01-01T12:00:00"
        entry.instance = "G1N1"
        entry.level = "INFORMATION"
        entry.message = "startup"
        entry.category = "SYSTEM"
        entry.error_code = None
        entry.error_message = None
        entry.source_file = "system.trc"
        with patch("server.diagnose.sundb_trc_api._last_entries", [entry]):
            resp = client.get("/diagnose/trc/timeline")
        data = resp.json()
        assert data["data"]["total"] == 1

    def test_filter_by_level(self, client):
        e1 = MagicMock(timestamp="t1", instance="G1N1", level="FATAL",
                       message="", category="", error_code=None,
                       error_message=None, source_file="system.trc")
        e2 = MagicMock(timestamp="t2", instance="G1N1", level="INFORMATION",
                       message="", category="", error_code=None,
                       error_message=None, source_file="system.trc")
        with patch("server.diagnose.sundb_trc_api._last_entries", [e1, e2]):
            resp = client.get("/diagnose/trc/timeline", params={"level": "FATAL"})
        data = resp.json()
        assert data["data"]["total"] == 1

    def test_filter_by_instance(self, client):
        e1 = MagicMock(timestamp="t1", instance="G1N1", level="INFO",
                       message="", category="", error_code=None,
                       error_message=None, source_file="system.trc")
        with patch("server.diagnose.sundb_trc_api._last_entries", [e1]):
            resp = client.get("/diagnose/trc/timeline", params={"instance": "G2N2"})
        data = resp.json()
        assert data["data"]["total"] == 0


class TestGetTrcAeuList:
    """GET /diagnose/trc/aeu_list."""

    def test_empty_cache(self, client):
        with patch("server.diagnose.sundb_trc_api._last_aeu_list", []):
            resp = client.get("/diagnose/trc/aeu_list")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 0

    def test_with_aeu(self, client):
        aeu = MagicMock()
        aeu.event_id = "AEU-001"
        aeu.timestamp = "2026-01-01T12:00:00"
        aeu.event_type = "FATAL"
        aeu.key_fields = {"error_code": "SDB-1001"}
        aeu.raw_log_snippet = "Fatal error occurred"
        with patch("server.diagnose.sundb_trc_api._last_aeu_list", [aeu]):
            resp = client.get("/diagnose/trc/aeu_list")
        data = resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["aeu_list"][0]["event_id"] == "AEU-001"

    def test_filter_by_event_type(self, client):
        aeu = MagicMock(event_id="AEU-001", timestamp="t1",
                        event_type="FATAL", key_fields={}, raw_log_snippet="")
        with patch("server.diagnose.sundb_trc_api._last_aeu_list", [aeu]):
            resp = client.get("/diagnose/trc/aeu_list", params={"event_type": "DEADLOCK"})
        data = resp.json()
        assert data["data"]["total"] == 0

    def test_filter_matching(self, client):
        aeu = MagicMock(event_id="AEU-001", timestamp="t1",
                        event_type="FATAL", key_fields={}, raw_log_snippet="")
        with patch("server.diagnose.sundb_trc_api._last_aeu_list", [aeu]):
            resp = client.get("/diagnose/trc/aeu_list", params={"event_type": "FATAL"})
        data = resp.json()
        assert data["data"]["total"] == 1
