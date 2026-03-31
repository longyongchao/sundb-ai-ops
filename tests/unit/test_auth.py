"""
Tests for authentication API endpoints.
Source: server/auth/auth_service.py
Endpoints: login, logout, register, verify_token, check_auth
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import time


class TestCheckAuth:
    """GET /api/auth/check — always returns 200."""

    def test_check_auth_returns_200(self, client):
        resp = client.get("/api/auth/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "认证服务正常" in data["msg"]


class TestRegister:
    """POST /api/auth/register."""

    def test_register_success(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with patch("server.auth.auth_service.SessionLocal", return_value=mock_session):
            resp = client.post("/api/auth/register", json={
                "username": "newuser1",
                "password": "pass12345",
            })
        data = resp.json()
        assert data["code"] == 200
        assert "注册成功" in data["msg"]

    def test_register_duplicate_username(self, client):
        existing_user = MagicMock()
        existing_user.username = "admin"
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = existing_user
        with patch("server.auth.auth_service.SessionLocal", return_value=mock_session):
            resp = client.post("/api/auth/register", json={
                "username": "admin",
                "password": "pass12345",
            })
        data = resp.json()
        assert data["code"] == 400
        assert "用户名已存在" in data["msg"]

    def test_register_short_username(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "ab",
            "password": "pass12345",
        })
        data = resp.json()
        assert data["code"] == 400
        assert "3个字符" in data["msg"]

    def test_register_invalid_username_chars(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "user@name",
            "password": "pass12345",
        })
        data = resp.json()
        assert data["code"] == 400
        assert "英文字母和数字" in data["msg"]

    def test_register_short_password(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "testuser",
            "password": "ab1",
        })
        data = resp.json()
        assert data["code"] == 400
        assert "5个字符" in data["msg"]

    def test_register_long_password(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "testuser",
            "password": "abcdefghijk",
        })
        data = resp.json()
        assert data["code"] == 400
        assert "10个字符" in data["msg"]

    def test_register_invalid_password_chars(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "testuser",
            "password": "pa$$word1",
        })
        data = resp.json()
        assert data["code"] == 400


class TestLogin:
    """POST /api/auth/login."""

    def test_login_success(self, client):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "admin"
        mock_user.password_hash = __import__("hashlib").sha256(b"admin").hexdigest()
        mock_user.role = "admin"
        mock_user.is_active = True
        mock_user.last_login = None

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        with patch("server.auth.auth_service.SessionLocal", return_value=mock_session):
            resp = client.post("/api/auth/login", json={
                "username": "admin",
                "password": "admin",
            })
        data = resp.json()
        assert data["code"] == 200
        assert "token" in data["data"]
        assert data["data"]["username"] == "admin"

    def test_login_wrong_password(self, client):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "admin"
        mock_user.password_hash = __import__("hashlib").sha256(b"admin").hexdigest()
        mock_user.role = "admin"
        mock_user.is_active = True

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        with patch("server.auth.auth_service.SessionLocal", return_value=mock_session):
            resp = client.post("/api/auth/login", json={
                "username": "admin",
                "password": "wrong_password",
            })
        data = resp.json()
        assert data["code"] == 401

    def test_login_user_not_found(self, client):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with patch("server.auth.auth_service.SessionLocal", return_value=mock_session):
            resp = client.post("/api/auth/login", json={
                "username": "nonexistent",
                "password": "any_pass",
            })
        data = resp.json()
        assert data["code"] == 401


class TestVerifyToken:
    """GET /api/auth/verify."""

    def test_verify_valid_token(self, client):
        with patch("server.auth.auth_service.active_tokens", {
            "test-token-123": {
                "user_id": 1,
                "username": "admin",
                "role": "admin",
                "login_time": time.time(),
            }
        }):
            resp = client.get("/api/auth/verify", params={"token": "test-token-123"})
        data = resp.json()
        assert data["code"] == 200

    def test_verify_invalid_token(self, client):
        with patch("server.auth.auth_service.active_tokens", {}):
            resp = client.get("/api/auth/verify", params={"token": "invalid"})
        data = resp.json()
        assert data["code"] == 401

    def test_verify_no_token(self, client):
        resp = client.get("/api/auth/verify")
        data = resp.json()
        assert data["code"] == 401

    def test_verify_expired_token(self, client):
        with patch("server.auth.auth_service.active_tokens", {
            "expired-token": {
                "user_id": 1,
                "username": "admin",
                "role": "admin",
                "login_time": time.time() - 100000,  # > 86400 seconds ago
            }
        }):
            resp = client.get("/api/auth/verify", params={"token": "expired-token"})
        data = resp.json()
        assert data["code"] == 401


class TestLogout:
    """POST /api/auth/logout."""

    def test_logout_success(self, client):
        with patch("server.auth.auth_service.active_tokens", {"tok-1": {"user_id": 1}}):
            resp = client.post("/api/auth/logout", json={"token": "tok-1"})
        data = resp.json()
        assert data["code"] == 200
        assert "退出成功" in data["msg"]

    def test_logout_nonexistent_token(self, client):
        with patch("server.auth.auth_service.active_tokens", {}):
            resp = client.post("/api/auth/logout", json={"token": "does-not-exist"})
        data = resp.json()
        assert data["code"] == 200
