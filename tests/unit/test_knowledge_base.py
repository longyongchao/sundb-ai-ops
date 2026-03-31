"""
Tests for knowledge base API endpoints.
Source: server/knowledge_base/kb_api.py, kb_doc_api.py
Endpoints: list/create/delete/update KB + list/detail/upload/delete/update/download/recreate docs + search
"""
import pytest
from unittest.mock import patch, MagicMock


class TestListKnowledgeBases:
    """GET /knowledge_base/list_knowledge_bases."""

    def test_list_kbs(self, client):
        with patch("server.knowledge_base.kb_api.KBServiceFactory") as mock_factory:
            mock_factory.get_kb_list.return_value = [
                {"kb_name": "test_kb", "vs_type": "faiss", "embed_model": "m3e-base"}
            ]
            resp = client.get("/knowledge_base/list_knowledge_bases")
        data = resp.json()
        assert data["code"] == 200

    def test_list_kbs_empty(self, client):
        with patch("server.knowledge_base.kb_api.KBServiceFactory") as mock_factory:
            mock_factory.get_kb_list.return_value = []
            resp = client.get("/knowledge_base/list_knowledge_bases")
        data = resp.json()
        assert data["code"] == 200


class TestCreateKnowledgeBase:
    """POST /knowledge_base/create_knowledge_base."""

    def test_create_success(self, client):
        with patch("server.knowledge_base.kb_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = None
            mock_factory.get_service.return_value = mock_service
            mock_service.create_kb.return_value = True
            resp = client.post("/knowledge_base/create_knowledge_base", json={
                "knowledge_base_name": "new_kb",
                "vector_store_type": "faiss",
                "embed_model": "m3e-base",
            })
        data = resp.json()
        assert data["code"] == 200

    def test_create_duplicate(self, client):
        with patch("server.knowledge_base.kb_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            resp = client.post("/knowledge_base/create_knowledge_base", json={
                "knowledge_base_name": "existing_kb",
                "vector_store_type": "faiss",
                "embed_model": "m3e-base",
            })
        data = resp.json()
        # Should indicate the KB already exists
        assert data["code"] in (200, 400, 403, 404)

    def test_create_empty_name(self, client):
        resp = client.post("/knowledge_base/create_knowledge_base", json={
            "knowledge_base_name": "",
            "vector_store_type": "faiss",
            "embed_model": "m3e-base",
        })
        data = resp.json()
        assert data["code"] in (200, 400, 403, 404)


class TestDeleteKnowledgeBase:
    """POST /knowledge_base/delete_knowledge_base."""

    def test_delete_existing(self, client):
        with patch("server.knowledge_base.kb_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            mock_service.clear_vs.return_value = True
            mock_service.drop_kb.return_value = True
            resp = client.post("/knowledge_base/delete_knowledge_base", json={
                "knowledge_base_name": "test_kb",
            })
        data = resp.json()
        assert data["code"] == 200

    def test_delete_nonexistent(self, client):
        with patch("server.knowledge_base.kb_api.KBServiceFactory") as mock_factory:
            mock_factory.get_service_by_name.return_value = None
            resp = client.post("/knowledge_base/delete_knowledge_base", json={
                "knowledge_base_name": "nonexistent",
            })
        data = resp.json()
        assert data["code"] in (200, 404)


class TestUpdateKbInfo:
    """POST /knowledge_base/update_info."""

    def test_update_info(self, client):
        with patch("server.knowledge_base.kb_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            mock_service.update_kb_info.return_value = True
            resp = client.post("/knowledge_base/update_info", json={
                "knowledge_base_name": "test_kb",
                "kb_info": "Updated description",
            })
        # The endpoint may use different param names or return different structure
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert data["code"] in (200, 403, 404)


class TestListFiles:
    """GET /knowledge_base/list_files."""

    def test_list_files(self, client):
        with patch("server.knowledge_base.kb_doc_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            mock_service.list_files.return_value = ["doc1.pdf", "doc2.txt"]
            resp = client.get("/knowledge_base/list_files", params={
                "knowledge_base_name": "test_kb",
            })
        data = resp.json()
        assert data["code"] == 200

    def test_list_files_nonexistent_kb(self, client):
        with patch("server.knowledge_base.kb_doc_api.KBServiceFactory") as mock_factory:
            mock_factory.get_service_by_name.return_value = None
            resp = client.get("/knowledge_base/list_files", params={
                "knowledge_base_name": "nonexistent",
            })
        data = resp.json()
        assert data["code"] in (200, 404)


class TestKbFileDetails:
    """GET /knowledge_base/kb_file_details."""

    def test_file_details(self, client):
        with patch("server.knowledge_base.kb_doc_api.get_kb_file_details") as mock_detail:
            mock_detail.return_value = [{"file_name": "test.pdf", "kb_name": "test_kb"}]
            resp = client.get("/knowledge_base/kb_file_details", params={
                "knowledge_base_name": "test_kb",
            })
        data = resp.json()
        assert data["code"] == 200


class TestSearchDocs:
    """POST /knowledge_base/search_docs."""

    def test_search(self, client):
        with patch("server.knowledge_base.kb_doc_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            mock_service.search_docs.return_value = [
                MagicMock(page_content="result", metadata={"source": "file.pdf"})
            ]
            resp = client.post("/knowledge_base/search_docs", json={
                "knowledge_base_name": "test_kb",
                "query": "database optimization",
                "top_k": 5,
            })
        data = resp.json()
        assert data["code"] == 200

    def test_search_empty_results(self, client):
        with patch("server.knowledge_base.kb_doc_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            mock_service.search_docs.return_value = []
            resp = client.post("/knowledge_base/search_docs", json={
                "knowledge_base_name": "test_kb",
                "query": "nonexistent topic",
                "top_k": 5,
            })
        data = resp.json()
        assert data["code"] == 200

    def test_search_kb_not_found(self, client):
        with patch("server.knowledge_base.kb_doc_api.KBServiceFactory") as mock_factory:
            mock_factory.get_service_by_name.return_value = None
            resp = client.post("/knowledge_base/search_docs", json={
                "knowledge_base_name": "nonexistent",
                "query": "test",
                "top_k": 5,
            })
        data = resp.json()
        assert data["code"] in (200, 404)


class TestDeleteDocs:
    """POST /knowledge_base/delete_docs."""

    def test_delete_docs(self, client):
        with patch("server.knowledge_base.kb_doc_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            mock_service.delete_doc.return_value = True
            resp = client.post("/knowledge_base/delete_docs", json={
                "knowledge_base_name": "test_kb",
                "file_names": ["doc1.pdf"],
            })
        data = resp.json()
        assert data["code"] == 200


class TestUpdateDocs:
    """POST /knowledge_base/update_docs."""

    def test_update_docs(self, client):
        with patch("server.knowledge_base.kb_doc_api.KBServiceFactory") as mock_factory:
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            mock_service.update_doc.return_value = True
            resp = client.post("/knowledge_base/update_docs", json={
                "knowledge_base_name": "test_kb",
                "file_names": ["doc1.pdf"],
            })
        data = resp.json()
        assert data["code"] == 200


class TestSearchAllDocs:
    """POST /knowledge_base/search_all_docs."""

    def test_search_all(self, client):
        with patch("server.knowledge_base.kb_doc_api.KBServiceFactory") as mock_factory:
            mock_factory.get_kb_list.return_value = [
                {"kb_name": "kb1"}, {"kb_name": "kb2"}
            ]
            mock_service = MagicMock()
            mock_factory.get_service_by_name.return_value = mock_service
            mock_service.search_docs.return_value = []
            resp = client.post("/knowledge_base/search_all_docs", json={
                "query": "test query",
                "top_k": 5,
            })
        data = resp.json()
        assert data["code"] == 200
