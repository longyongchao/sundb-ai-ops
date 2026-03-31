"""
Tests for GET / → redirect to /docs
Source: server/api.py → document()
"""
import pytest


class TestApiRoot:
    """Test the root endpoint."""

    def test_root_redirects_to_docs(self, client):
        """GET / should redirect (307) to /docs."""
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (307, 302)
        assert "/docs" in resp.headers.get("location", "")

    def test_root_follow_redirect(self, client):
        """GET / following redirect should reach /docs (200)."""
        resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
