"""
Tests for notification API endpoints.
Source: server/diagnose/notification_api.py
Endpoints: unread, all, read, read-all, count
"""
import pytest
from unittest.mock import patch, MagicMock
from contextlib import contextmanager


def _make_session_scope(mock_session):
    """Create a mock session_scope context manager."""
    @contextmanager
    def fake_scope():
        yield mock_session
    return fake_scope


class TestGetUnreadNotifications:
    """GET /api/notifications/unread."""

    def test_no_unread(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.get("/api/notifications/unread")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_with_unread_notifications(self, client):
        mock_notif = MagicMock()
        mock_notif.to_dict.return_value = {"id": 1, "title": "Test", "is_read": False}
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_notif]
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.get("/api/notifications/unread")
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]) == 1

    def test_custom_limit(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.get("/api/notifications/unread", params={"limit": 5})
        assert resp.json()["code"] == 200


class TestGetAllNotifications:
    """GET /api/notifications/all."""

    def test_returns_all(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.order_by.return_value.limit.return_value.all.return_value = []
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.get("/api/notifications/all")
        data = resp.json()
        assert data["code"] == 200

    def test_filter_by_type(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.get("/api/notifications/all", params={"notification_type": "alert"})
        assert resp.json()["code"] == 200

    def test_db_error(self, client):
        @contextmanager
        def fail_scope():
            raise Exception("DB error")
            yield
        with patch("server.diagnose.notification_api.session_scope", fail_scope):
            resp = client.get("/api/notifications/all")
        data = resp.json()
        assert data["code"] == 500


class TestMarkNotificationRead:
    """PUT /api/notifications/read."""

    def test_mark_existing_read(self, client):
        mock_notif = MagicMock()
        mock_notif.to_dict.return_value = {"id": 1, "is_read": True}
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_notif
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.put("/api/notifications/read", json={"notification_id": 1})
        data = resp.json()
        assert data["code"] == 200
        assert "标记成功" in data["msg"]

    def test_mark_nonexistent(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.put("/api/notifications/read", json={"notification_id": 999})
        data = resp.json()
        assert data["code"] == 404


class TestMarkAllRead:
    """PUT /api/notifications/read-all."""

    def test_mark_all_success(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.update.return_value = 5
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.put("/api/notifications/read-all")
        data = resp.json()
        assert data["code"] == 200


class TestGetUnreadCount:
    """GET /api/notifications/count."""

    def test_count_zero(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 0
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.get("/api/notifications/count")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["count"] == 0

    def test_count_nonzero(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 7
        with patch("server.diagnose.notification_api.session_scope", _make_session_scope(mock_session)):
            resp = client.get("/api/notifications/count")
        data = resp.json()
        assert data["data"]["count"] == 7

    def test_count_db_error(self, client):
        @contextmanager
        def fail_scope():
            raise Exception("DB error")
            yield
        with patch("server.diagnose.notification_api.session_scope", fail_scope):
            resp = client.get("/api/notifications/count")
        data = resp.json()
        assert data["code"] == 500
        assert data["data"]["count"] == 0
