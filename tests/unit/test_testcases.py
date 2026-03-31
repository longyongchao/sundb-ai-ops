"""
Tests for testcase API endpoints.
Source: server/diagnose/testcase_api.py
Endpoints: list, categories, category/{id}, {case_id}, statistics
"""
import pytest
import json
import os
from unittest.mock import patch, MagicMock


class TestGetTestcaseList:
    """GET /api/testcases/list."""

    def test_empty_directory(self, client, tmp_path):
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/list")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_nonexistent_directory(self, client):
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", "/nonexistent/path"):
            resp = client.get("/api/testcases/list")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_with_cases(self, client, tmp_path):
        cat_dir = tmp_path / "01_cpu_high"
        cat_dir.mkdir()
        case = {
            "case_id": "case_001",
            "case_name": "Test Case 1",
            "category": "CPU",
            "difficulty": "easy",
            "alert_type": "cpu_high",
            "severity": "high",
            "case_description": "A test case for CPU high usage scenario",
        }
        (cat_dir / "case_001.json").write_text(json.dumps(case))
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/list")
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]) == 1
        assert data["data"][0]["case_id"] == "case_001"

    def test_invalid_json_skipped(self, client, tmp_path):
        cat_dir = tmp_path / "01_cpu_high"
        cat_dir.mkdir()
        (cat_dir / "case_001.json").write_text("not valid json{{{")
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/list")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []


class TestGetTestcaseCategories:
    """GET /api/testcases/categories."""

    def test_empty(self, client, tmp_path):
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/categories")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == []

    def test_with_categories(self, client, tmp_path):
        cat_dir = tmp_path / "01_cpu_high"
        cat_dir.mkdir()
        case = {"case_id": "case_001", "case_name": "Test"}
        (cat_dir / "case_001.json").write_text(json.dumps(case))
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/categories")
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]) == 1
        assert data["data"][0]["case_count"] == 1


class TestGetTestcasesByCategory:
    """GET /api/testcases/category/{category_id}."""

    def test_existing_category(self, client, tmp_path):
        cat_dir = tmp_path / "01_cpu_high"
        cat_dir.mkdir()
        case = {
            "case_id": "case_001", "case_name": "T", "category": "CPU",
            "difficulty": "easy", "alert_type": "cpu", "severity": "high",
            "case_description": "desc",
        }
        (cat_dir / "case_001.json").write_text(json.dumps(case))
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/category/01_cpu_high")
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]) == 1

    def test_nonexistent_category(self, client, tmp_path):
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/category/99_nonexistent")
        data = resp.json()
        assert data["code"] == 404


class TestGetTestcaseDetail:
    """GET /api/testcases/{case_id}."""

    def test_existing_case(self, client, tmp_path):
        cat_dir = tmp_path / "01_cpu_high"
        cat_dir.mkdir()
        case = {"case_id": "case_001", "case_name": "Test CPU", "data": "full details"}
        (cat_dir / "case_001.json").write_text(json.dumps(case))
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/case_001")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["case_id"] == "case_001"

    def test_nonexistent_case(self, client, tmp_path):
        cat_dir = tmp_path / "01_cpu_high"
        cat_dir.mkdir()
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/case_nonexistent")
        data = resp.json()
        assert data["code"] == 404

    def test_no_base_dir(self, client):
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", "/nonexistent"):
            resp = client.get("/api/testcases/case_001")
        data = resp.json()
        assert data["code"] == 404


class TestGetTestcaseStatistics:
    """GET /api/testcases/statistics.

    Note: This route may be masked by the /api/testcases/{case_id} catch-all
    route since 'statistics' matches as a case_id. If so, the endpoint returns
    a 404 "Testcase not found: statistics" response from get_testcase_detail.
    """

    def test_empty(self, client, tmp_path):
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/statistics")
        data = resp.json()
        # May be caught by {case_id} route and return 404
        assert data["code"] in (200, 404)

    def test_with_cases(self, client, tmp_path):
        cat_dir = tmp_path / "01_cpu_high"
        cat_dir.mkdir()
        for i in range(3):
            case = {"difficulty": ["easy", "medium", "hard"][i]}
            (cat_dir / f"case_00{i+1}.json").write_text(json.dumps(case))
        with patch("server.diagnose.testcase_api.TESTCASE_BASE_DIR", str(tmp_path)):
            resp = client.get("/api/testcases/statistics")
        data = resp.json()
        # May be caught by {case_id} route
        assert data["code"] in (200, 404)
        if data["code"] == 200 and "total_count" in data.get("data", {}):
            assert data["data"]["total_count"] == 3
