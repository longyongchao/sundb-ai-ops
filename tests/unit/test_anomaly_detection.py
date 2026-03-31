"""
Tests for anomaly detection API endpoints (inline closures in api.py).
Source: server/api.py -> mount_anomaly_detector_routes()
Endpoints: anomaly status/alerts/thresholds + scheduler status/auto/start/stop + monitoring toggle/status

The closures inside mount_anomaly_detector_routes() capture ``get_detector``
and ``get_scheduler`` references at mount time via
``from server.diagnose.anomaly_detector import get_detector``.  The closures
hold a direct reference to those function objects.

When the real modules loaded successfully (not MagicMock stubs), the captured
``get_detector`` / ``get_scheduler`` are real functions that read from the
module-level singletons ``_detector_instance`` / ``_scheduler_instance``.
Setting ``.return_value`` on a real function is a no-op.

The correct approach is to patch the module-level singleton variables
``server.diagnose.anomaly_detector._detector_instance`` and
``server.diagnose.scheduler_service._scheduler_instance`` so that when
the closure calls ``get_detector()`` (which checks ``if _detector_instance
is None``), it returns our mock instead of the real instance.
"""
import sys

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixture – inject mock detector / scheduler via the module-level singletons
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _inject_mocks(mock_detector_and_scheduler):
    """Replace the module-level singleton instances so get_detector() /
    get_scheduler() return our mocks.

    This works for both the real-module path and the MagicMock-stub path:
    - Real modules: ``get_detector()`` checks ``_detector_instance``; we
      replace it with the mock so the ``if ... is None`` guard is skipped.
    - MagicMock stubs: setting the attribute on MagicMock also works.

    This fixture is autouse so every test in this module automatically gets
    the mock injection.
    """
    detector, scheduler = mock_detector_and_scheduler

    det_mod = sys.modules.get("server.diagnose.anomaly_detector")
    sch_mod = sys.modules.get("server.diagnose.scheduler_service")

    patches = []

    if det_mod is not None:
        p1 = patch.object(det_mod, "_detector_instance", detector)
        p1.start()
        patches.append(p1)

    if sch_mod is not None:
        p2 = patch.object(sch_mod, "_scheduler_instance", scheduler)
        p2.start()
        patches.append(p2)

    yield

    for p in reversed(patches):
        p.stop()


# ===================================================================
# Tests
# ===================================================================


class TestGetAnomalyStatus:
    """GET /api/anomaly/status."""

    def test_status_success(self, client, mock_detector_and_scheduler):
        detector, _ = mock_detector_and_scheduler
        resp = client.get("/api/anomaly/status")
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], dict)


class TestGetAnomalyAlerts:
    """GET /api/anomaly/alerts."""

    def test_alerts_empty(self, client, mock_detector_and_scheduler):
        resp = client.get("/api/anomaly/alerts")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_alerts_with_limit(self, client, mock_detector_and_scheduler):
        detector, _ = mock_detector_and_scheduler
        detector.get_alert_history.return_value = [{"id": 1, "type": "cpu"}]
        resp = client.get("/api/anomaly/alerts", params={"limit": 50})
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == [{"id": 1, "type": "cpu"}]


class TestClearAnomalyAlerts:
    """DELETE /api/anomaly/alerts."""

    def test_clear_alerts(self, client, mock_detector_and_scheduler):
        resp = client.delete("/api/anomaly/alerts")
        data = resp.json()
        assert data["code"] == 200
        assert "cleared" in data["msg"]


class TestUpdateAnomalyThresholds:
    """POST /api/anomaly/thresholds."""

    def test_update_thresholds(self, client, mock_detector_and_scheduler):
        resp = client.post("/api/anomaly/thresholds", json={"cpu": 90, "memory": 95})
        data = resp.json()
        assert data["code"] == 200
        assert "updated" in data["msg"].lower()


class TestGetSchedulerStatus:
    """GET /api/scheduler/status."""

    def test_scheduler_status(self, client, mock_detector_and_scheduler):
        resp = client.get("/api/scheduler/status")
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], dict)


class TestSetAutoDiagnosis:
    """POST /api/scheduler/auto_diagnosis."""

    def test_enable(self, client, mock_detector_and_scheduler):
        resp = client.post("/api/scheduler/auto_diagnosis", json={"enabled": True})
        data = resp.json()
        assert data["code"] == 200
        assert "enabled" in data["msg"]

    def test_disable(self, client, mock_detector_and_scheduler):
        resp = client.post("/api/scheduler/auto_diagnosis", json={"enabled": False})
        data = resp.json()
        assert data["code"] == 200
        assert "disabled" in data["msg"]


class TestStartScheduler:
    """POST /api/scheduler/start."""

    def test_start(self, client, mock_detector_and_scheduler):
        resp = client.post("/api/scheduler/start")
        data = resp.json()
        assert data["code"] == 200
        assert "started" in data["msg"].lower()


class TestStopScheduler:
    """POST /api/scheduler/stop."""

    def test_stop(self, client, mock_detector_and_scheduler):
        resp = client.post("/api/scheduler/stop")
        data = resp.json()
        assert data["code"] == 200
        assert "stopped" in data["msg"].lower()


class TestToggleMonitoring:
    """POST /api/monitoring/toggle."""

    def test_enable_monitoring(self, client, mock_detector_and_scheduler):
        _, scheduler = mock_detector_and_scheduler
        # resume_monitoring returns True by default (from fixture)
        resp = client.post("/api/monitoring/toggle", json={"enabled": True})
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["monitoring_enabled"] is True

    def test_disable_monitoring(self, client, mock_detector_and_scheduler):
        _, scheduler = mock_detector_and_scheduler
        # pause_monitoring returns True by default (from fixture)
        resp = client.post("/api/monitoring/toggle", json={"enabled": False})
        data = resp.json()
        assert data["code"] == 200

    def test_enable_fails(self, client, mock_detector_and_scheduler):
        _, scheduler = mock_detector_and_scheduler
        scheduler.resume_monitoring.return_value = False
        scheduler.is_monitoring_active.return_value = False
        resp = client.post("/api/monitoring/toggle", json={"enabled": True})
        data = resp.json()
        # When resume_monitoring() returns False, the endpoint returns code=500
        assert data["code"] == 500
        assert data["data"]["success"] is False
        assert data["data"]["monitoring_enabled"] is False


class TestGetMonitoringStatus:
    """GET /api/monitoring/status."""

    def test_status(self, client, mock_detector_and_scheduler):
        resp = client.get("/api/monitoring/status")
        data = resp.json()
        assert data["code"] == 200
        assert "monitoring_enabled" in data["data"]
        assert "auto_diagnosis_enabled" in data["data"]
        assert "scheduler_status" in data["data"]
