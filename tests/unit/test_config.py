"""
Tests for system configuration API endpoints.
Source: server/config/config_api.py
Endpoints: 11 settings GET/POST + test_connection + test_llm_connection
"""
import pytest
import json
import os
from unittest.mock import patch, MagicMock


class TestGetAllSettings:
    """GET /api/settings/all."""

    def test_returns_all_defaults(self, client, tmp_path):
        with patch("server.config.config_api.SETTINGS_FILE", str(tmp_path / "nonexistent.json")):
            resp = client.get("/api/settings/all")
        data = resp.json()
        assert data["code"] == 200
        assert "llm" in data["data"]
        assert "database" in data["data"]
        assert "notification" in data["data"]
        assert "security" in data["data"]

    def test_returns_saved_settings(self, client, tmp_path):
        settings = {
            "llm": {"model_type": "openai", "model_name": "gpt-4"},
            "database": {},
            "notification": {},
            "security": {},
        }
        f = tmp_path / "settings.json"
        f.write_text(json.dumps(settings))
        with patch("server.config.config_api.SETTINGS_FILE", str(f)):
            resp = client.get("/api/settings/all")
        data = resp.json()
        assert data["data"]["llm"]["model_type"] == "openai"


class TestLLMSettings:
    """GET/POST /api/settings/llm."""

    def test_get_llm_defaults(self, client, tmp_path):
        with patch("server.config.config_api.SETTINGS_FILE", str(tmp_path / "no.json")):
            resp = client.get("/api/settings/llm")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["model_type"] == "deepseek"

    def test_save_llm_settings(self, client, tmp_path):
        f = tmp_path / "settings.json"
        with patch("server.config.config_api.SETTINGS_FILE", str(f)):
            resp = client.post("/api/settings/llm", json={
                "model_type": "openai",
                "model_name": "gpt-4",
                "api_key": "sk-test",
                "api_base": "https://api.openai.com",
                "temperature": 0.5,
                "max_tokens": 2048,
            })
        data = resp.json()
        assert data["code"] == 200
        assert "保存成功" in data["msg"]
        saved = json.loads(f.read_text())
        assert saved["llm"]["model_type"] == "openai"

    def test_save_then_read_llm(self, client, tmp_path):
        f = tmp_path / "settings.json"
        with patch("server.config.config_api.SETTINGS_FILE", str(f)):
            client.post("/api/settings/llm", json={
                "model_type": "local",
                "model_name": "llama",
                "temperature": 0.3,
                "max_tokens": 1024,
                "api_base": "http://localhost",
            })
            resp = client.get("/api/settings/llm")
        data = resp.json()
        assert data["data"]["model_type"] == "local"


class TestDatabaseSettings:
    """GET/POST /api/settings/database."""

    def test_get_database_defaults(self, client, tmp_path):
        with patch("server.config.config_api.SETTINGS_FILE", str(tmp_path / "no.json")):
            resp = client.get("/api/settings/database")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["db_type"] == "postgresql"

    def test_save_database_settings(self, client, tmp_path):
        f = tmp_path / "settings.json"
        with patch("server.config.config_api.SETTINGS_FILE", str(f)):
            resp = client.post("/api/settings/database", json={
                "db_type": "mysql",
                "host": "db.example.com",
                "port": 3306,
                "username": "root",
                "password": "secret",
                "database": "mydb",
            })
        data = resp.json()
        assert data["code"] == 200


class TestNotificationSettings:
    """GET/POST /api/settings/notification."""

    def test_get_notification_defaults(self, client, tmp_path):
        with patch("server.config.config_api.SETTINGS_FILE", str(tmp_path / "no.json")):
            resp = client.get("/api/settings/notification")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["email_enabled"] is False

    def test_save_notification_settings(self, client, tmp_path):
        f = tmp_path / "settings.json"
        with patch("server.config.config_api.SETTINGS_FILE", str(f)):
            resp = client.post("/api/settings/notification", json={
                "email_enabled": True,
                "dingtalk_enabled": False,
                "wechat_enabled": False,
                "cpu_threshold": 90,
                "memory_threshold": 95,
            })
        data = resp.json()
        assert data["code"] == 200


class TestSecuritySettings:
    """GET/POST /api/settings/security."""

    def test_get_security_defaults(self, client, tmp_path):
        with patch("server.config.config_api.SETTINGS_FILE", str(tmp_path / "no.json")):
            resp = client.get("/api/settings/security")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["api_auth_enabled"] is True

    def test_save_security_settings(self, client, tmp_path):
        f = tmp_path / "settings.json"
        with patch("server.config.config_api.SETTINGS_FILE", str(f)):
            resp = client.post("/api/settings/security", json={
                "api_auth_enabled": False,
                "cors_enabled": True,
                "log_level": "DEBUG",
            })
        data = resp.json()
        assert data["code"] == 200


class TestTestDatabaseConnection:
    """POST /api/settings/database/test."""

    def test_postgresql_success(self, client):
        mock_pg = MagicMock()
        mock_conn = MagicMock()
        mock_pg.connect.return_value = mock_conn
        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            resp = client.post("/api/settings/database/test", json={
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "username": "test",
                "password": "test",
                "database": "testdb",
            })
        data = resp.json()
        assert data["code"] == 200
        assert "PostgreSQL 连接成功" in data["msg"]

    def test_postgresql_failure(self, client):
        mock_pg = MagicMock()
        mock_pg.connect.side_effect = Exception("Connection refused")
        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            resp = client.post("/api/settings/database/test", json={
                "db_type": "postgresql",
                "host": "badhost",
                "port": 5432,
                "username": "test",
                "database": "testdb",
            })
        data = resp.json()
        assert data["code"] == 500
        assert "连接失败" in data["msg"]

    def test_sqlite_success(self, client, tmp_path):
        db_path = str(tmp_path / "test.db")
        resp = client.post("/api/settings/database/test", json={
            "db_type": "sqlite",
            "host": "localhost",
            "port": 0,
            "username": "",
            "database": db_path,
        })
        data = resp.json()
        assert data["code"] == 200
        assert "SQLite 连接成功" in data["msg"]

    def test_unsupported_db_type(self, client):
        resp = client.post("/api/settings/database/test", json={
            "db_type": "oracle",
            "host": "localhost",
            "port": 1521,
            "username": "sys",
            "database": "orcl",
        })
        data = resp.json()
        assert data["code"] == 400
        assert "不支持的数据库类型" in data["msg"]


class TestTestLLMConnection:
    """POST /api/settings/llm/test."""

    def test_llm_connection_success(self, client):
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = MagicMock()
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client_instance
        with patch.dict("sys.modules", {"openai": mock_openai_module}):
            resp = client.post("/api/settings/llm/test", json={
                "model_type": "deepseek",
                "model_name": "deepseek-chat",
                "api_key": "sk-test",
                "api_base": "https://api.deepseek.com",
                "temperature": 0.7,
                "max_tokens": 4096,
            })
        data = resp.json()
        assert data["code"] == 200

    def test_llm_connection_failure(self, client):
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.side_effect = Exception("auth failed")
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client_instance
        with patch.dict("sys.modules", {"openai": mock_openai_module}):
            resp = client.post("/api/settings/llm/test", json={
                "model_type": "deepseek",
                "model_name": "deepseek-chat",
                "api_key": "bad-key",
                "api_base": "https://api.deepseek.com",
                "temperature": 0.7,
                "max_tokens": 4096,
            })
        data = resp.json()
        assert data["code"] == 500
        assert "连接失败" in data["msg"]
