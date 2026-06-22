"""
Unit tests for CsvLogConverter (server/diagnose/csv_log_converter.py)

覆盖：
  - 列角色推断（timestamp / level / message / extra）
  - 多种时间戳格式规范化
  - 级别映射（标准级别 + 业务状态伪级别）
  - 转换后的行格式与 LILAC 预处理器兼容性
  - 边界情况：空文件、单列、无时间戳、无级别、全数字
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.diagnose.csv_log_converter import CsvLogConverter, ColumnSchema


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def conv():
    return CsvLogConverter(sample_rows=20)


@pytest.fixture
def preprocessor():
    from server.diagnose.lilac.preprocessor import LogPreprocessor
    return LogPreprocessor()


# ============================================================
# 1. 标准日志 CSV（timestamp + level + message）
# ============================================================

class TestStandardLogCsv:
    CSV = (
        "timestamp,level,message,host\n"
        "2024-03-12 15:49:05,ERROR,Connection refused,srv-01\n"
        "2024-03-12 15:49:06,INFO,Retry attempt 1,srv-01\n"
        "2024-03-12 15:49:07,WARNING,Threshold exceeded,srv-02\n"
    )

    def test_schema_detection(self, conv):
        r = conv.convert_text(self.CSV)
        assert r.schema.timestamp_col == "timestamp"
        assert r.schema.level_col == "level"
        assert r.schema.message_col == "message"
        assert "host" in r.schema.extra_cols

    def test_level_preserved(self, conv):
        r = conv.convert_text(self.CSV)
        lines = r.log_text.splitlines()
        assert " ERROR " in lines[0]
        assert " INFO " in lines[1]
        assert " WARNING " in lines[2]

    def test_lilac_format(self, conv, preprocessor):
        r = conv.convert_text(self.CSV)
        for line in r.log_text.splitlines():
            result = preprocessor.preprocess(line)
            assert result.header_format == "iso_level", f"Expected iso_level, got {result.header_format!r} for: {line}"

    def test_extra_appended(self, conv):
        r = conv.convert_text(self.CSV)
        lines = r.log_text.splitlines()
        assert "[host=srv-01]" in lines[0]

    def test_converted_rows_count(self, conv):
        r = conv.convert_text(self.CSV)
        assert r.total_rows == 3
        assert r.converted_rows == 3
        assert r.warnings == []


# ============================================================
# 2. 浮点 epoch 时间戳（timestamp_anon 格式）
# ============================================================

class TestFloatEpochTimestamp:
    CSV = (
        "timestamp_anon,value,container_ip\n"
        "1662859290.0,2639.0,086b31f81b1cf0f15e43fe568e3fb8e4\n"
        "1662859404.0,2766.0,47d94ec84e80267e738db2caca3d9184\n"
    )

    def test_epoch_detected_as_timestamp(self, conv):
        r = conv.convert_text(self.CSV)
        assert r.schema.timestamp_col == "timestamp_anon"

    def test_epoch_converted_to_datetime(self, conv):
        r = conv.convert_text(self.CSV)
        lines = r.log_text.splitlines()
        # 1662859290 UTC → 2022-09-11
        assert lines[0].startswith("2022-09-11")

    def test_lilac_format(self, conv, preprocessor):
        r = conv.convert_text(self.CSV)
        for line in r.log_text.splitlines():
            result = preprocessor.preprocess(line)
            assert result.header_format == "iso_level"


# ============================================================
# 3. 业务状态伪级别（SUCCEED / FAILED）
# ============================================================

class TestBusinessStatusLevel:
    CSV = (
        "gmt_create,predict_type,predict_status,exec_time\n"
        "2024/11/15 16:57,TXT_2_IMG,SUCCEED,32\n"
        "2024/11/17 4:44,TXT_2_IMG,FAILED,3\n"
    )

    def test_status_col_as_level(self, conv):
        r = conv.convert_text(self.CSV)
        assert r.schema.level_col == "predict_status"

    def test_succeed_maps_to_info(self, conv):
        r = conv.convert_text(self.CSV)
        lines = r.log_text.splitlines()
        assert " INFO " in lines[0]

    def test_failed_maps_to_error(self, conv):
        r = conv.convert_text(self.CSV)
        lines = r.log_text.splitlines()
        assert " ERROR " in lines[1]

    def test_slash_date_normalized(self, conv):
        r = conv.convert_text(self.CSV)
        assert "2024-11-15" in r.log_text

    def test_single_digit_hour_padded(self, conv):
        r = conv.convert_text(self.CSV)
        # 4:44 → 04:44:00
        assert "04:44:00" in r.log_text


# ============================================================
# 4. 时间戳格式边界
# ============================================================

class TestTimestampNormalization:

    @pytest.mark.parametrize("ts_in,ts_out_contains", [
        ("2024-03-12 15:49:05",     "2024-03-12 15:49:05"),    # 已完整
        ("2024-03-12T15:49:05",     "2024-03-12 15:49:05"),    # T 分隔符
        ("2024/3/5 9:05",           "2024-03-05 09:05:00"),    # 单位数月日时
        ("2024-03-12 15:49",        "2024-03-12 15:49:00"),    # 缺秒
        ("1700000000",              "2023-11-14"),              # 整数 epoch
        ("1700000000.0",            "2023-11-14"),              # 浮点 epoch
        ("1700000000000",           "2023-11-14"),              # 毫秒 epoch
    ])
    def test_normalize(self, ts_in, ts_out_contains, conv):
        from server.diagnose.csv_log_converter import CsvLogConverter
        result = CsvLogConverter._normalize_timestamp(ts_in)
        assert ts_out_contains in result, f"Input {ts_in!r} → {result!r}, expected to contain {ts_out_contains!r}"


# ============================================================
# 5. 假级别列不被误判
# ============================================================

class TestNoFalsePositiveLevel:

    def test_gpu_model_not_level(self, conv):
        csv = "gpu_model,gpu_num,cpu_num\nA10,4,192\nV100,8,64\n"
        r = conv.convert_text(csv)
        assert r.schema.level_col is None

    def test_job_type_not_level(self, conv):
        csv = "job_id,job_type,duration\n001,HP,3600\n002,SP,1800\n"
        r = conv.convert_text(csv)
        assert r.schema.level_col is None

    def test_role_not_level(self, conv):
        csv = "instance,role,cpu\ninstance_0,HN,12\ninstance_1,HN,12\n"
        r = conv.convert_text(csv)
        assert r.schema.level_col is None

    def test_exec_time_not_timestamp(self, conv):
        """exec_time_seconds 不应被识别为时间戳"""
        csv = "exec_time_seconds,predict_type,status\n32,TXT,SUCCEED\n43,IMG,SUCCEED\n"
        r = conv.convert_text(csv)
        assert r.schema.timestamp_col is None


# ============================================================
# 6. 空列 / 无时间戳 / 无级别 的处理
# ============================================================

class TestMissingColumns:

    def test_no_timestamp_warns(self, conv):
        csv = "module,message\nauth,User login\ndb,Query ok\n"
        r = conv.convert_text(csv)
        assert r.schema.timestamp_col is None
        assert any("时间戳" in w for w in r.warnings)

    def test_no_level_defaults_to_info(self, conv):
        csv = "timestamp,module,message\n2024-01-01 10:00:00,auth,Login ok\n"
        r = conv.convert_text(csv)
        assert " INFO " in r.log_text

    def test_empty_time_column_not_selected(self, conv):
        """time 列全为空时不应被选为时间戳"""
        csv = "name,creation_time,role\nfoo,,admin\nbar,,user\n"
        r = conv.convert_text(csv)
        assert r.schema.timestamp_col is None

    def test_single_column_csv(self, conv):
        """单列 CSV 不崩溃"""
        csv = "runtime\n0.0\n1.0\n2.5\n"
        r = conv.convert_text(csv)
        assert r.total_rows == 3
        assert r.converted_rows == 3
        # 无重复（无 message_col 时不追加 extra）
        for line in r.log_text.splitlines():
            assert line.count("runtime=") == 1

    def test_empty_csv(self, conv):
        """空 CSV 不崩溃"""
        r = conv.convert_text("")
        assert r.total_rows == 0
        assert r.log_text == ""
        assert r.warnings


# ============================================================
# 7. 分隔符自动探测
# ============================================================

class TestDelimiterDetection:

    def test_semicolon_delimiter(self, conv):
        csv = "timestamp;level;message\n2024-01-01 10:00:00;ERROR;Disk full\n"
        r = conv.convert_text(csv)
        assert r.schema.timestamp_col == "timestamp"
        assert r.schema.level_col == "level"
        assert r.converted_rows == 1

    def test_tab_delimiter(self, conv):
        csv = "timestamp\tlevel\tmessage\n2024-01-01 10:00:00\tINFO\tAll good\n"
        r = conv.convert_text(csv)
        assert r.schema.timestamp_col == "timestamp"
        assert r.converted_rows == 1


# ============================================================
# 8. 无 message 列时不出现重复 extra
# ============================================================

class TestNoMessageColNoDuplicate:

    def test_no_duplicate_in_output(self, conv):
        """message_col=None 时，extra 不再重复追加"""
        csv = "runtime\n0.0\n1.0\n"
        r = conv.convert_text(csv)
        for line in r.log_text.splitlines():
            # 不应出现 "runtime=0.0 [runtime=0.0]"
            assert line.count("runtime=") == 1
