"""
Tests for LLM model management API endpoints.
Source: server/llm_api.py, server/utils.py
Endpoints: llm_model, embed_models, list_running, list_config, stop, change
"""
import pytest
from unittest.mock import patch, MagicMock


class TestLlmModel:
    """GET /llm_model/list_models."""

    def test_returns_model_list(self, client):
        resp = client.get("/llm_model/list_models")
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)


class TestEmbedModels:
    """GET /llm_model/embed_models."""

    def test_returns_embed_models(self, client):
        resp = client.get("/llm_model/embed_models")
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)


class TestListRunningModels:
    """POST /llm_model/list_running_models."""

    def test_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": ["model-a"]}
        with patch("server.llm_api.get_httpx_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_factory.return_value = mock_client
            with patch("server.llm_api.get_model_config") as mock_cfg:
                mock_cfg.return_value = MagicMock(data={"some": "config"})
                resp = client.post("/llm_model/list_running_models", json={
                    "controller_address": None,
                    "placeholder": None,
                })
        data = resp.json()
        assert data["code"] == 200

    def test_controller_unreachable(self, client):
        with patch("server.llm_api.get_httpx_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = ConnectionError("refused")
            mock_factory.return_value = mock_client
            resp = client.post("/llm_model/list_running_models", json={
                "controller_address": "http://127.0.0.1:9999",
                "placeholder": None,
            })
        data = resp.json()
        assert data["code"] == 500


class TestListConfigModels:
    """POST /llm_model/list_config_models."""

    def test_list_config_models(self, client):
        resp = client.post("/llm_model/list_config_models", json={
            "types": ["local", "online"],
            "placeholder": None,
        })
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], dict)


class TestStopLlmModel:
    """POST /llm_model/stop."""

    def test_stop_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 200, "msg": "stopped"}
        with patch("server.llm_api.get_httpx_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_factory.return_value = mock_client
            resp = client.post("/llm_model/stop", json={
                "model_name": "test-model",
                "controller_address": "http://127.0.0.1:21001",
            })
        data = resp.json()
        assert data["code"] == 200

    def test_stop_failure(self, client):
        with patch("server.llm_api.get_httpx_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = Exception("fail")
            mock_factory.return_value = mock_client
            resp = client.post("/llm_model/stop", json={
                "model_name": "test-model",
                "controller_address": "http://127.0.0.1:21001",
            })
        data = resp.json()
        assert data["code"] == 500


class TestChangeLlmModel:
    """POST /llm_model/change."""

    def test_change_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 200, "msg": "changed"}
        with patch("server.llm_api.get_httpx_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_factory.return_value = mock_client
            resp = client.post("/llm_model/change", json={
                "model_name": "old-model",
                "new_model_name": "new-model",
                "controller_address": "http://127.0.0.1:21001",
            })
        data = resp.json()
        assert data["code"] == 200

    def test_change_failure(self, client):
        with patch("server.llm_api.get_httpx_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = Exception("connection refused")
            mock_factory.return_value = mock_client
            resp = client.post("/llm_model/change", json={
                "model_name": "old-model",
                "new_model_name": "new-model",
                "controller_address": "http://127.0.0.1:21001",
            })
        data = resp.json()
        assert data["code"] == 500
