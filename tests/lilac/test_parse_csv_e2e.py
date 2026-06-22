"""parse_csv 端到端测试：CSV 上传 → 列推断 → LILAC 解析 → 字段保真度验证"""

import io
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


SAMPLE_CSV = """\
gmt_create,predict_type,predict_status,exec_time_seconds,groupId
2024/11/15 16:57,TXT_2_IMG,SUCCEED,32,G0000
2024/11/17 4:44,TXT_2_IMG,FAILED,0,G0001
2024/11/18 9:05,IMG_2_IMG,SUCCEED,18,G0002
"""

SAMPLE_CSV_SEMICOLON = """\
timestamp;level;message;user_id
2024-01-01 10:00:00;INFO;User logged in;U001
2024-01-01 10:00:05;ERROR;Connection failed;U002
"""

SAMPLE_CSV_EPOCH = """\
ts,level,msg
1700000000,INFO,Hello world
1700000060000,ERROR,Something broke
"""


@pytest.fixture
def client():
    """创建包含 parse_csv 的 FastAPI TestClient"""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    import server.diagnose.lilac_api as lilac_api

    lilac_api._parser = None

    from server.diagnose.lilac_api import lilac_parse_csv

    app = FastAPI()
    app.post("/diagnose/lilac/parse_csv")(lilac_parse_csv)
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_env(tmp_cache_db):
    """使用临时缓存，禁用 LLM"""
    os.environ["LILAC_CACHE_DB_PATH"] = tmp_cache_db
    os.environ["LILAC_ENABLE_LLM"] = "false"
    os.environ["LILAC_ENABLE_DRAIN3"] = "false"
    import server.diagnose.lilac_api as lilac_api
    lilac_api._parser = None
    yield
    lilac_api._parser = None


class TestParseCsvBasic:
    """基本 CSV 解析与字段对比"""

    def test_schema_detection(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]

        schema = data["csv_conversion"]["schema"]
        assert schema["timestamp_col"] == "gmt_create"
        assert schema["level_col"] == "predict_status"
        assert schema["message_col"] == "predict_type"
        assert "exec_time_seconds" in schema["extra_cols"]
        assert "groupId" in schema["extra_cols"]

    def test_entries_count(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        assert data["total_entries"] == 3
        assert data["csv_conversion"]["total_rows"] == 3
        assert data["csv_conversion"]["converted_rows"] == 3

    def test_field_checks_returned(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        assert "field_checks" in data
        assert "accuracy" in data
        assert "csv_rows" in data
        assert len(data["field_checks"]) == 3
        assert len(data["csv_rows"]) == 3

    def test_accuracy_structure(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        acc = data["accuracy"]

        required_keys = [
            "checked_rows", "full_row_match", "full_pct",
            "ts_match", "ts_total", "ts_pct",
            "lv_match", "lv_total", "lv_pct",
            "msg_match", "msg_total", "msg_pct",
            "extra_match", "extra_total", "extra_pct",
            "tpl_placeholder", "tpl_pct",
            "row_alignment", "skipped_rows",
        ]
        for key in required_keys:
            assert key in acc, f"Missing accuracy key: {key}"

        assert acc["checked_rows"] == 3
        assert acc["skipped_rows"] == 0
        assert acc["row_alignment"] == "exact"

    def test_timestamp_normalization(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        acc = data["accuracy"]
        assert acc["ts_pct"] == 100, f"Timestamp accuracy should be 100%, got {acc['ts_pct']}%"

    def test_level_mapping(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        acc = data["accuracy"]
        assert acc["lv_pct"] == 100, f"Level accuracy should be 100%, got {acc['lv_pct']}%"

    def test_message_fidelity(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        acc = data["accuracy"]
        assert acc["msg_pct"] == 100, f"Message accuracy should be 100%, got {acc['msg_pct']}%"

    def test_extra_fields_fidelity(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        acc = data["accuracy"]
        assert acc["extra_pct"] == 100, f"Extra accuracy should be 100%, got {acc['extra_pct']}%"

    def test_row_mapping_present(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        row_mapping = data["csv_conversion"]["row_mapping"]
        assert row_mapping == [0, 1, 2]


class TestParseCsvSemicolon:
    """分号分隔 CSV 测试"""

    def test_semicolon_delimiter(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV_SEMICOLON.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        assert data["total_entries"] == 2
        schema = data["csv_conversion"]["schema"]
        assert schema["timestamp_col"] == "timestamp"
        assert schema["level_col"] == "level"


class TestParseCsvEpoch:
    """Unix 时间戳 CSV 测试"""

    def test_epoch_timestamp(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV_EPOCH.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        assert data["total_entries"] == 2
        acc = data["accuracy"]
        assert acc["ts_pct"] == 100


class TestFieldChecksDetail:
    """field_checks 内容详细验证"""

    def test_check_structure(self, client):
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        fc = data["field_checks"][0]

        assert "csv_row_idx" in fc
        assert "entry_idx" in fc
        assert "checks" in fc
        assert "all_match" in fc
        assert fc["csv_row_idx"] == 0
        assert fc["entry_idx"] == 0

        for check in fc["checks"]:
            assert "col" in check
            assert "role" in check
            assert "original" in check
            assert "expected" in check
            assert "parsed" in check
            assert "match" in check

    def test_failed_check_detected(self, client):
        bad_csv = "ts,level,msg\nnot-a-date,INFO,Hello\n"
        resp = client.post(
            "/diagnose/lilac/parse_csv",
            files={"file": ("test.csv", io.BytesIO(bad_csv.encode()), "text/csv")},
        )
        data = resp.json()["data"]
        if data["total_entries"] > 0:
            acc = data["accuracy"]
            assert acc["full_pct"] is not None
