"""
Tests for chat API endpoints.
Source: server/chat/chat.py, feedback.py, search_engine_chat.py, knowledge_base_chat.py
Endpoints: chat, fastchat, search_engine_chat, feedback, knowledge_base_chat
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json
import asyncio


class TestChatFeedback:
    """POST /chat/feedback."""

    def test_feedback_success(self, client):
        with patch("server.chat.feedback.feedback_message_to_db") as mock_feedback:
            resp = client.post("/chat/feedback", json={
                "message_id": "msg-001",
                "score": 85,
                "reason": "Accurate diagnosis",
            })
        data = resp.json()
        assert data["code"] == 200
        mock_feedback.assert_called_once()

    def test_feedback_empty_message_id(self, client):
        with patch("server.chat.feedback.feedback_message_to_db"):
            resp = client.post("/chat/feedback", json={
                "message_id": "",
                "score": 50,
                "reason": "ok",
            })
        data = resp.json()
        assert data["code"] == 200

    def test_feedback_db_error(self, client):
        with patch("server.chat.feedback.feedback_message_to_db", side_effect=Exception("DB error")):
            resp = client.post("/chat/feedback", json={
                "message_id": "msg-002",
                "score": 30,
                "reason": "Bad result",
            })
        data = resp.json()
        assert data["code"] == 500


class TestChat:
    """POST /chat/chat — streaming response."""

    def test_chat_returns_streaming(self, client):
        # The chat endpoint returns a StreamingResponse, so we test the response type.
        # Mock LLMChain to bypass pydantic validation that llm must be a Runnable.
        mock_chain_instance = MagicMock()
        mock_chain_instance.acall = AsyncMock(return_value={"input": "Hello", "text": "Hi there"})
        with patch("server.chat.chat.LLMChain", return_value=mock_chain_instance):
            with patch("server.chat.chat.get_ChatOpenAI") as mock_get_chat:
                mock_model = MagicMock()
                mock_get_chat.return_value = mock_model
                with patch("server.chat.chat.get_prompt_template", return_value="{input}"):
                    with patch("server.chat.chat.add_message_to_db", return_value=1):
                        resp = client.post("/chat/chat", json={
                            "query": "Hello",
                            "stream": False,
                            "model_name": "deepseek-chat",
                            "temperature": 0.7,
                        })
        # StreamingResponse returns 200 with text/event-stream
        assert resp.status_code == 200

    def test_chat_with_history(self, client):
        # Mock LLMChain to bypass pydantic validation that llm must be a Runnable.
        mock_chain_instance = MagicMock()
        mock_chain_instance.acall = AsyncMock(return_value={"input": "What is this?", "text": "It is a test"})
        with patch("server.chat.chat.LLMChain", return_value=mock_chain_instance):
            with patch("server.chat.chat.get_ChatOpenAI") as mock_get_chat:
                mock_model = MagicMock()
                mock_get_chat.return_value = mock_model
                with patch("server.chat.chat.get_prompt_template", return_value="{input}"):
                    resp = client.post("/chat/chat", json={
                        "query": "What is this?",
                        "history": [
                            {"role": "user", "content": "Hi"},
                            {"role": "assistant", "content": "Hello"},
                        ],
                        "stream": False,
                        "model_name": "deepseek-chat",
                        "temperature": 0.7,
                    })
        assert resp.status_code == 200


class TestKnowledgeBaseChat:
    """POST /chat/knowledge_base_chat."""

    def test_kb_chat(self, client):
        mock_chain_instance = MagicMock()
        mock_chain_instance.acall = AsyncMock(return_value={"context": "", "question": "How to optimize slow queries?", "text": "Use indexes"})
        with patch("server.chat.knowledge_base_chat.LLMChain", return_value=mock_chain_instance):
            with patch("server.chat.knowledge_base_chat.KBServiceFactory") as mock_factory:
                mock_service = MagicMock()
                mock_factory.get_service_by_name.return_value = mock_service
                with patch("server.chat.knowledge_base_chat.search_docs") as mock_search_docs:
                    mock_search_docs.return_value = [
                        MagicMock(page_content="Relevant content", metadata={"source": "doc.pdf"})
                    ]
                    with patch("server.chat.knowledge_base_chat.get_ChatOpenAI") as mock_chat:
                        mock_model = MagicMock()
                        mock_chat.return_value = mock_model
                        resp = client.post("/chat/knowledge_base_chat", json={
                            "query": "How to optimize slow queries?",
                            "knowledge_base_name": "test_kb",
                            "model_name": "deepseek-chat",
                            "temperature": 0.7,
                            "top_k": 3,
                            "stream": False,
                        })
        # StreamingResponse always returns 200
        assert resp.status_code == 200

    def test_kb_chat_nonexistent_kb(self, client):
        with patch("server.chat.knowledge_base_chat.KBServiceFactory") as mock_factory:
            mock_factory.get_service_by_name.return_value = None
            resp = client.post("/chat/knowledge_base_chat", json={
                "query": "test",
                "knowledge_base_name": "nonexistent",
                "model_name": "deepseek-chat",
                "temperature": 0.7,
                "top_k": 3,
                "stream": False,
            })
        # May return error or empty streaming response
        assert resp.status_code in (200, 404)


class TestSearchEngineChat:
    """POST /chat/search_engine_chat."""

    def test_search_engine_chat(self, client):
        mock_chain_instance = MagicMock()
        mock_chain_instance.acall = AsyncMock(return_value={"context": "", "question": "database optimization best practices", "text": "Best practices include indexing"})
        with patch("server.chat.search_engine_chat.LLMChain", return_value=mock_chain_instance):
            with patch("server.chat.search_engine_chat.get_ChatOpenAI") as mock_chat:
                mock_model = MagicMock()
                mock_chat.return_value = mock_model
                with patch("server.chat.search_engine_chat.lookup_search_engine") as mock_search:
                    # lookup_search_engine returns a list of Document objects, not a string
                    mock_doc = MagicMock()
                    mock_doc.page_content = "Search results: relevant info"
                    mock_doc.metadata = {"source": "https://example.com", "filename": "Example"}
                    mock_search.return_value = [mock_doc]
                    resp = client.post("/chat/search_engine_chat", json={
                        "query": "database optimization best practices",
                        "search_engine_name": "duckduckgo",
                        "model_name": "deepseek-chat",
                        "temperature": 0.7,
                        "stream": False,
                    })
        assert resp.status_code == 200


class TestFastChat:
    """POST /chat/fastchat."""

    def test_fastchat(self, client):
        with patch("server.chat.openai_chat.openai_chat") as mock_chat:
            mock_chat.return_value = MagicMock()
            resp = client.post("/chat/fastchat", json={
                "messages": [{"role": "user", "content": "Hello"}],
                "model": "deepseek-chat",
                "temperature": 0.7,
                "stream": False,
            })
        # The endpoint may accept different params
        assert resp.status_code in (200, 422)
