#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SunDB .trc 日志解析器 — 单元测试

测试覆盖:
  1. SunDBLogEntry 数据结构
  2. SunDBFileHeader 解析
  3. system.trc INFORMATION 级别
  4. system.trc WARNING 级别
  5. system.trc FATAL 级别
  6. 错误码提取
  8. listener.trc 解析
  9. CDC (cyrmte_*.trc) 解析
  10. gmon.trc 解析
  11. 文件级解析
  12. 批量解析
  13. 时间线构建
  14. 故障事件提取
  15. FaultEvent 数据结构
  16. AEU 转换
  17. AEU 数据结构
  18. 真实文件集成测试
  19. 边界情况和健壮性
  20. 统计功能

所有测试数据均来自真实 SunDB 集群日志（4 节点: G1N1, G1N2, G2N1, G2N2）。
"""

import sys
import os
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# 项目根目录
ROOT_PATH = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_PATH))

from server.diagnose.sundb_trc_parser import (
    SunDBLogEntry,
    SunDBFileHeader,
    SunDBSystemTrcParser,
    SunDBListenerTrcParser,
    SunDBCdcTrcParser,
    SunDBGmonTrcParser,
)
from server.diagnose.sundb_batch_parser import (
    SunDBBatchParser,
    FaultEvent,
    AEU,
)


# ============================================================
# 真实日志片段常量（从 测试文件/trc/extracted 中提取）
# ============================================================

# ------ system.trc 文件头 (有 INSTANCE NAME) ------
SYSTEM_TRC_HEADER = """\
=================================================
 INSTANCE NAME : G1N1
 TIME          : 2024-03-12 15:49:05.624850
 VERSION       : Release 5.0 22.1.3 revision(7f23c84d0b)
=================================================
"""

# ------ listener.trc / CDC 文件头 (无 INSTANCE NAME) ------
SIMPLE_TRC_HEADER = """\
=================================================
 TIME    : 2024-02-05 16:18:28.406205
 VERSION : Release 5.0 22.1.3 revision(7f23c84d0b)
=================================================
"""

# ------ gmon.trc 文件头 (有 gmon start 标记) ------
GMON_TRC_HEADER = """\
=================================================
 gmon start
 TIME    : 2024-02-05 15:18:13.604523
 VERSION : Release 5.0 22.1.3 revision(7f23c84d0b)
=================================================
"""

# ------ INFORMATION 级别: REBALANCE 条目 ------
SYSTEM_ENTRY_INFORMATION = """\
[2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] [INFORMATION]
    [REBALANCE] replay journal data to table 'ECIF.ECUSRCERT' shard (36) done - global transaction id(1.6905593860), total replayed journal data count(0)
"""

# ------ WARNING 级别: sniped remote session ------
SYSTEM_ENTRY_WARNING_SNIPE = """\
[2024-02-19 16:59:25.151911 INSTANCE(G2N2) THREAD(238560,281470583917984)] [WARNING]
sniped remote session - global session(0.61.4.0), driver session(0.61.4), local session(58.4)
"""

# ------ WARNING 级别: CLEANUP ------
SYSTEM_ENTRY_WARNING_CLEANUP = """\
[2024-02-19 16:59:25.172336 INSTANCE(G2N2) THREAD(238393,281465030373856)] [WARNING]
[CLEANUP] cleaning cluster session - env(-1), local session(58.5), driver session(0.61.4), driver transaction(-1), local transaction(-1), program(cluster peer), pid(-1), thread(-1)
"""

# ------ WARNING 级别: DDL failure + 错误码 (多行) ------
SYSTEM_ENTRY_WARNING_DDL_FAILURE = """\
[2024-03-12 15:52:39.542011 INSTANCE(G1N1) THREAD(2586367,281471206772128)] [WARNING]
[SESSION:498][DDL failure] TRANS ID(5517607410), DRIVER MEMBER ID(-1), DRIVER TRANS ID(6781468751) - ( truncate table OEPP_BATCH_RECORD_INFO )
(G1N1) ERR-42000(15017): DDL not allowed for supplemental log table
"""

# ------ WARNING 级别: ERR-RD000 远程会话查找失败 ------
SYSTEM_ENTRY_WARNING_ERR_RD000 = """\
[2024-03-12 16:33:36.285185 INSTANCE(G1N1) THREAD(2586391,281456713420192)] [WARNING]
failed to cancell remote query - driver session( 1, 63, 49 ), local session( -1, 0 ), exeuctor(3, 1)
(G1N1) ERR-RD000(13041): User session ID does not exist
"""

# ------ FATAL 级别: Undo Semaphore 异常终止 (多行) ------
SYSTEM_ENTRY_FATAL = """\
[2024-03-12 15:22:21.061484 INSTANCE(G2N2) THREAD(3196761,281464999703008)] [FATAL]
[CLEANUP] abnormally terminated
(G2N2) ERR-HY000(11000): Invalid argument: stpGetUndoSemaphoreState() returned errno(22)
"""

# ------ INFORMATION 级别: DEADLOCK 条目 (多行，消息体内含结构化字段) ------
SYSTEM_ENTRY_DEADLOCK = """\
[2024-03-08 10:59:04.744588 INSTANCE(G2N1) THREAD(3539687,281469270707616)] [INFORMATION]
[DEADLOCK] SESSION_ID     : 137
           TRANSACTION_ID : 5783158921
           SQL            :    update CSII_SEC_ATTACTER set S_TIME=sysdate where  S_KEY=? and S_TYPE=? and S_TRANSACTIONID=?
"""

# ------ INFORMATION 级别: BUILD GSI 条目 ------
SYSTEM_ENTRY_BUILD_INDEX = """\
[2024-03-07 16:05:44.794122 INSTANCE(G1N1) THREAD(1751036,281461259914656)] [INFORMATION]
[BUILD GSI] GSI build begin - transaction id (-65535), physical id (95983929131008), parallel (8), online (FALSE)
"""

# ------ listener.trc 正常启动 ------
LISTENER_ENTRY_STARTED = """\
[2024-02-05 16:18:28.406162 THREAD(1347044,281465167431120)]
[LISTENER] Configuration file: /home/sundb/product/sundb_data/conf/sundb.listener.conf,
TCP port: 22581, C/S mode: Dedicated, Connection timeout: 100, Back log: 1024, Tcp filter type: no, Tcp invited file: sundb.invited.conf, Tcp excluded file: sundb.excluded.conf
"""

# ------ listener.trc 创建失败 ------
LISTENER_ENTRY_FAILED = """\
[2024-02-05 16:18:32.832826 THREAD(1347046,281472767116752)]
[LISTENER] failed to create listener
"""

# ------ CDC: 连接字符串 ------
CDC_ENTRY_CONNECTION = """\
[2024-03-07 11:52:24.095602 THREAD(1645819,281460251578304)]
connection string [PROTOCOL=DA;DSN=SUNDB;PROTOCOL=TCP;HOST=172.31.220.92;PORT=22581;UID=EIP;PWD=SUNDB]
"""

# ------ CDC: 登录失败 ------
CDC_ENTRY_AUTH_FAILURE = """\
[2024-03-07 11:52:24.112335 THREAD(1645819,281460251578304)]
ERR-28000(16004) : invalid username/password; logon denied
"""

# ------ CDC: 启动 LSN (多行) ------
CDC_ENTRY_START_LSN = """\
[2024-03-07 11:52:35.944364 THREAD(1645826,281472377573312)]
START LSN [995448965]
- CLUSTER GROUP  : G1(1)
- CLUSTER MEMBER : G1N1(1)
"""

# ------ CDC: 添加表成功 ------
CDC_ENTRY_ADD_TABLE = """\
[2024-03-07 11:52:36.017545 THREAD(1645826,281472377573312)]
Add EIP.JACLOST Table success[StartLSN = 995448965]
"""

# ------ CDC: CAPTURE 配置信息 (多行) ------
CDC_ENTRY_CAPTURE_CONFIG = """\
[2024-03-07 11:59:06.244469 THREAD(1646786,281459172134848)]
Configure
    Protocol                     : TCP
    Host Ip                      : 127.0.0.1
    Host Port                    : 22581
    DSN                          : SUNDB
    Group Count                  : 1
    Capture Chunk Count(16M * N) : 6
    Transaction File Path        : NULL
    Read Log Block Count         : 40960
    Transaction Sort Area Size   : 314572800
"""

# ------ gmon.trc 条目 ------
GMON_ENTRY_WARMUP = """\
[2024-02-05 15:18:13.606445 THREAD(1339332,281471121116576)]
Successfully warmed up.
"""

GMON_ENTRY_INIT = """\
[2024-02-05 15:18:13.606486 THREAD(1339332,281471121116576)]
Successfully initialized - gmon(1339332), gmaster(1339265)
"""

# ============================================================
# 组合多条目用于测试连续解析
# ============================================================

SYSTEM_TRC_MULTI_ENTRIES = (
    SYSTEM_TRC_HEADER + "\n"
    + SYSTEM_ENTRY_INFORMATION + "\n"
    + SYSTEM_ENTRY_WARNING_DDL_FAILURE + "\n"
    + SYSTEM_ENTRY_FATAL + "\n"
    + SYSTEM_ENTRY_DEADLOCK + "\n"
)

LISTENER_TRC_MULTI_ENTRIES = (
    SIMPLE_TRC_HEADER + "\n"
    + LISTENER_ENTRY_STARTED + "\n"
    + LISTENER_ENTRY_FAILED + "\n"
)

CDC_TRC_MULTI_ENTRIES = (
    SIMPLE_TRC_HEADER + "\n"
    + CDC_ENTRY_CONNECTION + "\n"
    + CDC_ENTRY_AUTH_FAILURE + "\n"
    + CDC_ENTRY_START_LSN + "\n"
    + CDC_ENTRY_ADD_TABLE + "\n"
)


# ============================================================
# 辅助函数
# ============================================================

def create_temp_trc_dir():
    """创建临时目录结构，模拟一个节点的 trc 目录"""
    tmpdir = tempfile.mkdtemp(prefix="sundb_test_")
    trc_dir = os.path.join(tmpdir, "g1n1", "trc")
    os.makedirs(trc_dir)
    return tmpdir, trc_dir


def write_trc_file(directory, filename, content):
    """写入 .trc 文件"""
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ############################################################
# 测试类 1: SunDBLogEntry 数据结构
# ############################################################

class TestSunDBLogEntry:
    """测试 SunDBLogEntry 数据类的创建和属性"""

    def test_create_basic_entry(self):
        entry = SunDBLogEntry(
            timestamp="2024-03-12 15:49:05.591941",
            instance="G1N1",
            thread_pid=2586375,
            thread_tid=281464209690016,
            level="INFORMATION",
            message="[REBALANCE] replay journal data to table 'ECIF.ECUSRCERT' shard (36) done",
            category="REBALANCE",
            error_code="",
            error_message="",
            source_file="system.trc",
            raw_text="",
        )
        assert entry.timestamp == "2024-03-12 15:49:05.591941"
        assert entry.instance == "G1N1"
        assert entry.thread_pid == 2586375
        assert entry.thread_tid == 281464209690016
        assert entry.level == "INFORMATION"
        assert entry.category == "REBALANCE"
        assert entry.error_code == ""

    def test_create_entry_with_error(self):
        entry = SunDBLogEntry(
            timestamp="2024-03-12 15:22:21.061484",
            instance="G2N2",
            thread_pid=3196761,
            thread_tid=281464999703008,
            level="FATAL",
            message="[CLEANUP] abnormally terminated",
            category="CLEANUP",
            error_code="ERR-HY000(11000)",
            error_message="Invalid argument: stpGetUndoSemaphoreState() returned errno(22)",
            source_file="system.trc",
            raw_text="",
        )
        assert entry.level == "FATAL"
        assert entry.error_code == "ERR-HY000(11000)"
        assert "stpGetUndoSemaphoreState" in entry.error_message

    def test_entry_without_instance(self):
        """listener/CDC 日志没有 INSTANCE 字段"""
        entry = SunDBLogEntry(
            timestamp="2024-02-05 16:18:28.406162",
            instance="",
            thread_pid=1347044,
            thread_tid=281465167431120,
            level="",
            message="[LISTENER] started.",
            category="LISTENER",
            error_code="",
            error_message="",
            source_file="listener.trc",
            raw_text="",
        )
        assert entry.instance == ""
        assert entry.level == ""


# ############################################################
# 测试类 2: SunDBFileHeader 解析
# ############################################################

class TestSunDBFileHeader:
    """测试文件头解析"""

    def setup_method(self):
        self.parser = SunDBSystemTrcParser()

    def test_parse_system_header(self):
        """system.trc 文件头包含 INSTANCE NAME"""
        header = self.parser.parse_header(SYSTEM_TRC_HEADER)
        assert header is not None
        assert header.instance_name == "G1N1"
        assert header.timestamp == "2024-03-12 15:49:05.624850"
        assert "5.0" in header.version
        assert "7f23c84d0b" in header.version

    def test_parse_simple_header(self):
        """listener/CDC 文件头没有 INSTANCE NAME"""
        listener_parser = SunDBListenerTrcParser()
        header = listener_parser.parse_header(SIMPLE_TRC_HEADER)
        assert header is not None
        assert header.instance_name == ""
        assert header.timestamp == "2024-02-05 16:18:28.406205"

    def test_parse_gmon_header(self):
        """gmon.trc 文件头有 gmon start 标记"""
        gmon_parser = SunDBGmonTrcParser()
        header = gmon_parser.parse_header(GMON_TRC_HEADER)
        assert header is not None
        assert header.timestamp == "2024-02-05 15:18:13.604523"

    def test_parse_header_from_full_content(self):
        """从包含条目的完整内容中提取文件头"""
        full = SYSTEM_TRC_HEADER + "\n" + SYSTEM_ENTRY_INFORMATION
        header = self.parser.parse_header(full)
        assert header is not None
        assert header.instance_name == "G1N1"

    def test_no_header(self):
        """没有文件头的内容返回 None"""
        header = self.parser.parse_header("just some random text\n")
        assert header is None


# ############################################################
# 测试类 3: system.trc INFORMATION 级别
# ############################################################

class TestSystemTrcInformation:
    """测试 system.trc INFORMATION 级别日志解析"""

    def setup_method(self):
        self.parser = SunDBSystemTrcParser()

    def test_parse_rebalance_entry(self):
        entries = self.parser.parse(SYSTEM_ENTRY_INFORMATION)
        assert len(entries) == 1
        e = entries[0]
        assert e.timestamp == "2024-03-12 15:49:05.591941"
        assert e.instance == "G1N1"
        assert e.thread_pid == 2586375
        assert e.thread_tid == 281464209690016
        assert e.level == "INFORMATION"
        assert e.category == "REBALANCE"
        assert "ECIF.ECUSRCERT" in e.message
        assert "shard (36)" in e.message
        assert e.error_code == ""

    def test_parse_build_gsi_entry(self):
        entries = self.parser.parse(SYSTEM_ENTRY_BUILD_INDEX)
        assert len(entries) == 1
        e = entries[0]
        assert e.level == "INFORMATION"
        assert e.category == "BUILD GSI"
        assert "parallel (8)" in e.message

    def test_parse_deadlock_entry(self):
        """DEADLOCK 在 INFORMATION 级别记录，但 category 应为 DEADLOCK"""
        entries = self.parser.parse(SYSTEM_ENTRY_DEADLOCK)
        assert len(entries) == 1
        e = entries[0]
        assert e.timestamp == "2024-03-08 10:59:04.744588"
        assert e.instance == "G2N1"
        assert e.level == "INFORMATION"
        assert e.category == "DEADLOCK"
        assert "SESSION_ID" in e.message
        assert "137" in e.message
        assert "CSII_SEC_ATTACTER" in e.message

    def test_deadlock_extracts_sql(self):
        """确保 DEADLOCK 条目包含完整的 SQL 语句"""
        entries = self.parser.parse(SYSTEM_ENTRY_DEADLOCK)
        e = entries[0]
        assert "update CSII_SEC_ATTACTER" in e.message
        assert "S_TIME=sysdate" in e.message


# ############################################################
# 测试类 4: system.trc WARNING 级别
# ############################################################

class TestSystemTrcWarning:
    """测试 system.trc WARNING 级别日志解析"""

    def setup_method(self):
        self.parser = SunDBSystemTrcParser()

    def test_parse_sniped_session(self):
        entries = self.parser.parse(SYSTEM_ENTRY_WARNING_SNIPE)
        assert len(entries) == 1
        e = entries[0]
        assert e.level == "WARNING"
        assert e.instance == "G2N2"
        assert "sniped remote session" in e.message
        assert "global session(0.61.4.0)" in e.message

    def test_parse_cleanup_warning(self):
        entries = self.parser.parse(SYSTEM_ENTRY_WARNING_CLEANUP)
        assert len(entries) == 1
        e = entries[0]
        assert e.level == "WARNING"
        assert e.category == "CLEANUP"
        assert "cleaning cluster session" in e.message

    def test_parse_ddl_failure(self):
        """DDL failure: 多行 WARNING，包含错误码"""
        entries = self.parser.parse(SYSTEM_ENTRY_WARNING_DDL_FAILURE)
        assert len(entries) == 1
        e = entries[0]
        assert e.level == "WARNING"
        assert e.error_code == "ERR-42000(15017)"
        assert e.error_message == "DDL not allowed for supplemental log table"
        assert "truncate table OEPP_BATCH_RECORD_INFO" in e.message
        assert "SESSION:498" in e.message

    def test_parse_err_rd000(self):
        """ERR-RD000: 远程会话不存在"""
        entries = self.parser.parse(SYSTEM_ENTRY_WARNING_ERR_RD000)
        assert len(entries) == 1
        e = entries[0]
        assert e.level == "WARNING"
        assert e.error_code == "ERR-RD000(13041)"
        assert e.error_message == "User session ID does not exist"
        assert "failed to cancell remote query" in e.message


# ############################################################
# 测试类 5: system.trc FATAL 级别
# ############################################################

class TestSystemTrcFatal:
    """测试 system.trc FATAL 级别日志解析"""

    def setup_method(self):
        self.parser = SunDBSystemTrcParser()

    def test_parse_fatal_entry(self):
        entries = self.parser.parse(SYSTEM_ENTRY_FATAL)
        assert len(entries) == 1
        e = entries[0]
        assert e.timestamp == "2024-03-12 15:22:21.061484"
        assert e.instance == "G2N2"
        assert e.thread_pid == 3196761
        assert e.level == "FATAL"
        assert e.category == "CLEANUP"
        assert "abnormally terminated" in e.message

    def test_fatal_has_error_code(self):
        entries = self.parser.parse(SYSTEM_ENTRY_FATAL)
        e = entries[0]
        assert e.error_code == "ERR-HY000(11000)"
        assert "stpGetUndoSemaphoreState" in e.error_message
        assert "errno(22)" in e.error_message


# ############################################################
# 测试类 6: 错误码提取
# ############################################################

class TestErrorCodeExtraction:
    """测试各种错误码格式的提取"""

    def setup_method(self):
        self.parser = SunDBSystemTrcParser()

    def test_err_hy000_11000(self):
        entries = self.parser.parse(SYSTEM_ENTRY_FATAL)
        assert entries[0].error_code == "ERR-HY000(11000)"

    def test_err_42000_15017(self):
        entries = self.parser.parse(SYSTEM_ENTRY_WARNING_DDL_FAILURE)
        assert entries[0].error_code == "ERR-42000(15017)"

    def test_err_rd000_13041(self):
        entries = self.parser.parse(SYSTEM_ENTRY_WARNING_ERR_RD000)
        assert entries[0].error_code == "ERR-RD000(13041)"

    def test_err_28000_16004_in_cdc(self):
        """ERR-28000(16004) — 登录拒绝（CDC 日志）"""
        cdc_parser = SunDBCdcTrcParser()
        entries = cdc_parser.parse(CDC_ENTRY_AUTH_FAILURE)
        assert len(entries) == 1
        assert entries[0].error_code == "ERR-28000(16004)"
        assert "invalid username/password" in entries[0].error_message

    def test_no_error_code(self):
        entries = self.parser.parse(SYSTEM_ENTRY_INFORMATION)
        assert entries[0].error_code == ""
        assert entries[0].error_message == ""


# ############################################################
# 测试类 7: 多条目连续解析
# ############################################################

class TestSystemTrcMultiEntries:
    """测试一个文件中多个条目的连续解析"""

    def setup_method(self):
        self.parser = SunDBSystemTrcParser()

    def test_parse_multiple_entries(self):
        entries = self.parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        assert len(entries) == 4

    def test_entries_order_preserved(self):
        entries = self.parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        assert entries[0].level == "INFORMATION"
        assert entries[0].category == "REBALANCE"
        assert entries[1].level == "WARNING"
        assert entries[1].error_code == "ERR-42000(15017)"
        assert entries[2].level == "FATAL"
        assert entries[2].error_code == "ERR-HY000(11000)"
        assert entries[3].level == "INFORMATION"
        assert entries[3].category == "DEADLOCK"

    def test_all_entries_have_timestamps(self):
        entries = self.parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        for e in entries:
            assert e.timestamp != ""
            dt = datetime.strptime(e.timestamp, "%Y-%m-%d %H:%M:%S.%f")
            assert dt.year == 2024

    def test_all_entries_have_instance(self):
        entries = self.parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        for e in entries:
            assert e.instance in ("G1N1", "G2N1", "G2N2")


# ############################################################
# 测试类 8: listener.trc 解析
# ############################################################

class TestListenerTrcParser:
    """测试 listener.trc 日志解析"""

    def setup_method(self):
        self.parser = SunDBListenerTrcParser()

    def test_parse_listener_started(self):
        entries = self.parser.parse(LISTENER_ENTRY_STARTED)
        assert len(entries) == 1
        e = entries[0]
        assert e.timestamp == "2024-02-05 16:18:28.406162"
        assert e.instance == ""
        assert e.thread_pid == 1347044
        assert e.thread_tid == 281465167431120
        assert e.level == ""
        assert e.category == "LISTENER"
        assert "Configuration file" in e.message
        assert "TCP port: 22581" in e.message

    def test_parse_listener_failed(self):
        entries = self.parser.parse(LISTENER_ENTRY_FAILED)
        assert len(entries) == 1
        e = entries[0]
        assert "failed to create listener" in e.message
        assert e.category == "LISTENER"

    def test_parse_multi_listener_entries(self):
        entries = self.parser.parse(LISTENER_TRC_MULTI_ENTRIES)
        assert len(entries) == 2

    def test_listener_multiline_config(self):
        entries = self.parser.parse(LISTENER_ENTRY_STARTED)
        e = entries[0]
        assert "C/S mode: Dedicated" in e.message
        assert "Back log: 1024" in e.message


# ############################################################
# 测试类 9: CDC (cyrmte_*.trc) 解析
# ############################################################

class TestCdcTrcParser:
    """测试 CDC (cyrmte_*.trc) 日志解析"""

    def setup_method(self):
        self.parser = SunDBCdcTrcParser()

    def test_parse_connection_string(self):
        entries = self.parser.parse(CDC_ENTRY_CONNECTION)
        assert len(entries) == 1
        e = entries[0]
        assert e.timestamp == "2024-03-07 11:52:24.095602"
        assert e.instance == ""
        assert e.thread_pid == 1645819
        assert "PROTOCOL=DA" in e.message
        assert "HOST=172.31.220.92" in e.message

    def test_parse_auth_failure(self):
        entries = self.parser.parse(CDC_ENTRY_AUTH_FAILURE)
        assert len(entries) == 1
        e = entries[0]
        assert e.error_code == "ERR-28000(16004)"
        assert "invalid username/password" in e.error_message

    def test_parse_start_lsn_multiline(self):
        entries = self.parser.parse(CDC_ENTRY_START_LSN)
        assert len(entries) == 1
        e = entries[0]
        assert "START LSN [995448965]" in e.message
        assert "CLUSTER GROUP" in e.message
        assert "G1(1)" in e.message

    def test_parse_add_table(self):
        entries = self.parser.parse(CDC_ENTRY_ADD_TABLE)
        assert len(entries) == 1
        e = entries[0]
        assert "EIP.JACLOST" in e.message
        assert "StartLSN = 995448965" in e.message

    def test_parse_capture_config_multiline(self):
        entries = self.parser.parse(CDC_ENTRY_CAPTURE_CONFIG)
        assert len(entries) == 1
        e = entries[0]
        assert "Protocol" in e.message
        assert "TCP" in e.message
        assert "Host Port" in e.message
        assert "22581" in e.message
        assert "Read Log Block Count" in e.message
        assert "40960" in e.message

    def test_parse_multi_cdc_entries(self):
        entries = self.parser.parse(CDC_TRC_MULTI_ENTRIES)
        assert len(entries) == 4


# ############################################################
# 测试类 10: gmon.trc 解析
# ############################################################

class TestGmonTrcParser:
    """测试 gmon.trc 日志解析"""

    def setup_method(self):
        self.parser = SunDBGmonTrcParser()

    def test_parse_warmup(self):
        entries = self.parser.parse(GMON_ENTRY_WARMUP)
        assert len(entries) == 1
        e = entries[0]
        assert e.timestamp == "2024-02-05 15:18:13.606445"
        assert e.thread_pid == 1339332
        assert "Successfully warmed up" in e.message

    def test_parse_init(self):
        entries = self.parser.parse(GMON_ENTRY_INIT)
        assert len(entries) == 1
        e = entries[0]
        assert "gmon(1339332)" in e.message
        assert "gmaster(1339265)" in e.message

    def test_parse_gmon_full(self):
        full = GMON_TRC_HEADER + "\n" + GMON_ENTRY_WARMUP + "\n" + GMON_ENTRY_INIT
        entries = self.parser.parse(full)
        assert len(entries) == 2


# ############################################################
# 测试类 11: 文件级解析 (parse_file)
# ############################################################

class TestFileLevel:
    """测试从文件路径读取和解析"""

    def setup_method(self):
        self.tmpdir, self.trc_dir = create_temp_trc_dir()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_parse_system_trc_file(self):
        path = write_trc_file(self.trc_dir, "system.trc", SYSTEM_TRC_MULTI_ENTRIES)
        parser = SunDBSystemTrcParser()
        entries = parser.parse_file(path)
        assert len(entries) == 4
        for e in entries:
            assert e.source_file == path

    def test_parse_listener_trc_file(self):
        path = write_trc_file(self.trc_dir, "listener.trc", LISTENER_TRC_MULTI_ENTRIES)
        parser = SunDBListenerTrcParser()
        entries = parser.parse_file(path)
        assert len(entries) == 2
        for e in entries:
            assert e.source_file == path

    def test_parse_cdc_trc_file(self):
        path = write_trc_file(self.trc_dir, "cyrmte_TEST_13.trc", CDC_TRC_MULTI_ENTRIES)
        parser = SunDBCdcTrcParser()
        entries = parser.parse_file(path)
        assert len(entries) == 4

    def test_parse_nonexistent_file(self):
        parser = SunDBSystemTrcParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/path/system.trc")

    def test_parse_empty_file(self):
        path = write_trc_file(self.trc_dir, "empty.trc", "")
        parser = SunDBSystemTrcParser()
        entries = parser.parse_file(path)
        assert entries == []

    def test_parse_header_only_file(self):
        path = write_trc_file(self.trc_dir, "system.trc", SYSTEM_TRC_HEADER)
        parser = SunDBSystemTrcParser()
        entries = parser.parse_file(path)
        assert entries == []

    def test_parse_rotated_file(self):
        content = SYSTEM_TRC_HEADER + "\n" + SYSTEM_ENTRY_INFORMATION
        path = write_trc_file(self.trc_dir, "system.trc_20240312_154855_0", content)
        parser = SunDBSystemTrcParser()
        entries = parser.parse_file(path)
        assert len(entries) == 1


# ############################################################
# 测试类 12: SunDBBatchParser — 批量解析
# ############################################################

class TestBatchParser:
    """测试跨多个文件的批量解析"""

    def setup_method(self):
        self.tmpdir, self.trc_dir = create_temp_trc_dir()
        write_trc_file(self.trc_dir, "system.trc", SYSTEM_TRC_MULTI_ENTRIES)
        write_trc_file(self.trc_dir, "listener.trc", LISTENER_TRC_MULTI_ENTRIES)
        write_trc_file(self.trc_dir, "cyrmte_TEST_13.trc", CDC_TRC_MULTI_ENTRIES)
        gmon_content = GMON_TRC_HEADER + "\n" + GMON_ENTRY_WARMUP + "\n" + GMON_ENTRY_INIT
        write_trc_file(self.trc_dir, "gmon.trc", gmon_content)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_parse_directory(self):
        parser = SunDBBatchParser()
        entries = parser.parse_directory(self.trc_dir)
        assert len(entries) == 12

    def test_auto_detect_file_type(self):
        parser = SunDBBatchParser()
        entries = parser.parse_directory(self.trc_dir)
        sources = set(os.path.basename(e.source_file) for e in entries)
        assert "system.trc" in sources
        assert "listener.trc" in sources
        assert "cyrmte_TEST_13.trc" in sources
        assert "gmon.trc" in sources

    def test_ignores_non_trc_files(self):
        write_trc_file(self.trc_dir, "README", "This is not a trc file")
        write_trc_file(self.trc_dir, "sundb.properties.conf", "some config")
        parser = SunDBBatchParser()
        entries = parser.parse_directory(self.trc_dir)
        for e in entries:
            assert not e.source_file.endswith(".conf")
            assert not os.path.basename(e.source_file) == "README"

    def test_parse_rotated_system_trc(self):
        rotated = SYSTEM_TRC_HEADER + "\n" + SYSTEM_ENTRY_INFORMATION
        write_trc_file(self.trc_dir, "system.trc_20240312_154855_0", rotated)
        parser = SunDBBatchParser()
        entries = parser.parse_directory(self.trc_dir)
        assert len(entries) == 13

    def test_parse_nonexistent_directory(self):
        parser = SunDBBatchParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_directory("/nonexistent/path")


# ############################################################
# 测试类 13: 时间线构建
# ############################################################

class TestTimeline:
    """测试时间线排序"""

    def setup_method(self):
        self.parser = SunDBBatchParser()

    def test_build_timeline_sorted(self):
        system_parser = SunDBSystemTrcParser()
        entries = system_parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        timeline = self.parser.build_timeline(entries)
        for i in range(len(timeline) - 1):
            assert timeline[i].timestamp <= timeline[i + 1].timestamp

    def test_build_timeline_cross_file(self):
        tmpdir, trc_dir = create_temp_trc_dir()
        try:
            write_trc_file(trc_dir, "system.trc", SYSTEM_TRC_MULTI_ENTRIES)
            write_trc_file(trc_dir, "listener.trc", LISTENER_TRC_MULTI_ENTRIES)
            all_entries = self.parser.parse_directory(trc_dir)
            timeline = self.parser.build_timeline(all_entries)
            for i in range(len(timeline) - 1):
                assert timeline[i].timestamp <= timeline[i + 1].timestamp
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_empty_timeline(self):
        timeline = self.parser.build_timeline([])
        assert timeline == []


# ############################################################
# 测试类 14: 故障事件提取
# ############################################################

class TestFaultEventExtraction:
    """测试从解析结果中提取故障事件"""

    def setup_method(self):
        self.batch_parser = SunDBBatchParser()
        self.system_parser = SunDBSystemTrcParser()
        self.cdc_parser = SunDBCdcTrcParser()

    def test_extract_fatal_event(self):
        entries = self.system_parser.parse(SYSTEM_ENTRY_FATAL)
        faults = self.batch_parser.extract_fault_events(entries)
        assert len(faults) >= 1
        fatal = [f for f in faults if f.event_type == "FATAL"]
        assert len(fatal) == 1
        assert fatal[0].severity == "critical"
        assert fatal[0].instance == "G2N2"
        assert fatal[0].error_code == "ERR-HY000(11000)"

    def test_extract_deadlock_event(self):
        entries = self.system_parser.parse(SYSTEM_ENTRY_DEADLOCK)
        faults = self.batch_parser.extract_fault_events(entries)
        deadlocks = [f for f in faults if f.event_type == "DEADLOCK"]
        assert len(deadlocks) == 1
        assert deadlocks[0].severity == "high"
        assert "CSII_SEC_ATTACTER" in deadlocks[0].description

    def test_extract_ddl_failure_event(self):
        entries = self.system_parser.parse(SYSTEM_ENTRY_WARNING_DDL_FAILURE)
        faults = self.batch_parser.extract_fault_events(entries)
        ddl_failures = [f for f in faults if f.event_type == "DDL_FAILURE"]
        assert len(ddl_failures) == 1
        assert ddl_failures[0].error_code == "ERR-42000(15017)"
        assert ddl_failures[0].severity == "medium"

    def test_extract_auth_failure_from_cdc(self):
        entries = self.cdc_parser.parse(CDC_ENTRY_AUTH_FAILURE)
        faults = self.batch_parser.extract_fault_events(entries)
        auth = [f for f in faults if f.event_type == "AUTH_FAILURE"]
        assert len(auth) == 1
        assert auth[0].error_code == "ERR-28000(16004)"
        assert auth[0].severity == "high"

    def test_extract_listener_failure(self):
        listener_parser = SunDBListenerTrcParser()
        entries = listener_parser.parse(LISTENER_ENTRY_FAILED)
        faults = self.batch_parser.extract_fault_events(entries)
        listener_fail = [f for f in faults if f.event_type == "LISTENER_FAILURE"]
        assert len(listener_fail) == 1
        assert listener_fail[0].severity == "high"

    def test_no_fault_from_normal_entries(self):
        entries = self.system_parser.parse(SYSTEM_ENTRY_INFORMATION)
        faults = self.batch_parser.extract_fault_events(entries)
        assert len(faults) == 0

    def test_extract_multiple_faults(self):
        entries = self.system_parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        faults = self.batch_parser.extract_fault_events(entries)
        event_types = [f.event_type for f in faults]
        assert "FATAL" in event_types
        assert "DDL_FAILURE" in event_types
        assert "DEADLOCK" in event_types
        assert "REBALANCE" not in event_types

    def test_fault_event_has_related_entries(self):
        entries = self.system_parser.parse(SYSTEM_ENTRY_FATAL)
        faults = self.batch_parser.extract_fault_events(entries)
        assert len(faults[0].related_entries) >= 1
        assert faults[0].related_entries[0].level == "FATAL"


# ############################################################
# 测试类 15: FaultEvent 数据结构
# ############################################################

class TestFaultEvent:
    """测试 FaultEvent 数据类"""

    def test_create_fault_event(self):
        entry = SunDBLogEntry(
            timestamp="2024-03-12 15:22:21.061484",
            instance="G2N2",
            thread_pid=3196761,
            thread_tid=281464999703008,
            level="FATAL",
            message="[CLEANUP] abnormally terminated",
            category="CLEANUP",
            error_code="ERR-HY000(11000)",
            error_message="Invalid argument",
            source_file="system.trc",
            raw_text="",
        )
        fault = FaultEvent(
            event_type="FATAL",
            timestamp="2024-03-12 15:22:21.061484",
            instance="G2N2",
            description="[CLEANUP] abnormally terminated",
            error_code="ERR-HY000(11000)",
            related_entries=[entry],
            severity="critical",
        )
        assert fault.event_type == "FATAL"
        assert fault.severity == "critical"
        assert len(fault.related_entries) == 1


# ############################################################
# 测试类 16: AEU（原子依据单元）转换
# ############################################################

class TestAEUConversion:
    """测试 FaultEvent -> AEU 转换"""

    def setup_method(self):
        self.batch_parser = SunDBBatchParser()
        self.system_parser = SunDBSystemTrcParser()

    def _get_fatal_fault(self):
        entries = self.system_parser.parse(SYSTEM_ENTRY_FATAL)
        faults = self.batch_parser.extract_fault_events(entries)
        return faults

    def test_aeu_from_fatal(self):
        faults = self._get_fatal_fault()
        aeu_list = self.batch_parser.to_aeu_list(faults)
        assert len(aeu_list) == 1
        aeu = aeu_list[0]
        assert aeu.event_id != ""
        assert aeu.timestamp == "2024-03-12 15:22:21.061484"
        assert aeu.event_type == "FATAL"
        assert "instance" in aeu.key_fields
        assert aeu.key_fields["instance"] == "G2N2"
        assert "error_code" in aeu.key_fields
        assert aeu.key_fields["error_code"] == "ERR-HY000(11000)"
        assert aeu.raw_log_snippet != ""

    def test_aeu_unique_ids(self):
        entries = self.system_parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        faults = self.batch_parser.extract_fault_events(entries)
        aeu_list = self.batch_parser.to_aeu_list(faults)
        ids = [a.event_id for a in aeu_list]
        assert len(ids) == len(set(ids))

    def test_aeu_has_raw_snippet(self):
        faults = self._get_fatal_fault()
        aeu_list = self.batch_parser.to_aeu_list(faults)
        aeu = aeu_list[0]
        assert "abnormally terminated" in aeu.raw_log_snippet
        assert "ERR-HY000(11000)" in aeu.raw_log_snippet

    def test_aeu_deadlock_key_fields(self):
        entries = self.system_parser.parse(SYSTEM_ENTRY_DEADLOCK)
        faults = self.batch_parser.extract_fault_events(entries)
        aeu_list = self.batch_parser.to_aeu_list(faults)
        assert len(aeu_list) == 1
        aeu = aeu_list[0]
        assert aeu.event_type == "DEADLOCK"
        assert "session_id" in aeu.key_fields
        assert aeu.key_fields["session_id"] == "137"
        assert "sql" in aeu.key_fields
        assert "CSII_SEC_ATTACTER" in aeu.key_fields["sql"]

    def test_aeu_from_empty_faults(self):
        aeu_list = self.batch_parser.to_aeu_list([])
        assert aeu_list == []


# ############################################################
# 测试类 17: AEU 数据结构
# ############################################################

class TestAEUDataClass:
    """测试 AEU 数据类"""

    def test_create_aeu(self):
        aeu = AEU(
            event_id="FATAL-G2N2-20240312152221",
            timestamp="2024-03-12 15:22:21.061484",
            event_type="FATAL",
            key_fields={
                "instance": "G2N2",
                "error_code": "ERR-HY000(11000)",
            },
            raw_log_snippet="[CLEANUP] abnormally terminated\nERR-HY000(11000): ...",
        )
        assert aeu.event_id.startswith("FATAL")
        assert aeu.event_type == "FATAL"
        assert aeu.key_fields["instance"] == "G2N2"


# ############################################################
# 测试类 18: 使用真实测试文件（集成测试）
# ############################################################

# 真实日志路径
REAL_TRC_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "测试文件", "trc", "extracted",
)

REAL_G1N1_TRC = os.path.join(REAL_TRC_BASE, "g1n1", "trc")
REAL_G2N1_TRC = os.path.join(REAL_TRC_BASE, "g2n1", "trc")
REAL_G2N2_TRC = os.path.join(REAL_TRC_BASE, "g2n2", "trc")

real_files_exist = os.path.isdir(REAL_G1N1_TRC)


@pytest.mark.skipif(not real_files_exist, reason="真实测试文件不存在")
class TestRealFiles:
    """使用真实 SunDB 集群日志的集成测试"""

    def test_parse_g1n1_system_trc(self):
        parser = SunDBSystemTrcParser()
        path = os.path.join(REAL_G1N1_TRC, "system.trc")
        entries = parser.parse_file(path)
        assert len(entries) > 100
        for e in entries[:10]:
            assert e.timestamp != ""
            assert e.instance == "G1N1"

    def test_real_file_has_warning_entries(self):
        parser = SunDBSystemTrcParser()
        path = os.path.join(REAL_G1N1_TRC, "system.trc")
        entries = parser.parse_file(path)
        warnings = [e for e in entries if e.level == "WARNING"]
        assert len(warnings) > 0

    def test_real_file_has_ddl_failures(self):
        parser = SunDBSystemTrcParser()
        path = os.path.join(REAL_G1N1_TRC, "system.trc")
        entries = parser.parse_file(path)
        ddl_fail = [e for e in entries if "DDL failure" in e.message]
        assert len(ddl_fail) > 0
        # DDL failures should all have error codes
        for e in ddl_fail:
            assert e.error_code.startswith("ERR-")

    @pytest.mark.skipif(
        not os.path.isdir(REAL_G2N2_TRC),
        reason="G2N2 测试文件不存在",
    )
    def test_real_g2n2_has_fatal(self):
        parser = SunDBSystemTrcParser()
        path = os.path.join(REAL_G2N2_TRC, "system.trc")
        entries = parser.parse_file(path)
        fatals = [e for e in entries if e.level == "FATAL"]
        assert len(fatals) >= 1
        assert fatals[0].error_code == "ERR-HY000(11000)"

    @pytest.mark.skipif(
        not os.path.isdir(REAL_G2N1_TRC),
        reason="G2N1 测试文件不存在",
    )
    def test_real_g2n1_has_deadlock(self):
        parser = SunDBSystemTrcParser()
        rotated = os.path.join(REAL_G2N1_TRC, "system.trc_20240312_154855_0")
        if not os.path.exists(rotated):
            pytest.skip("旋转文件不存在")
        entries = parser.parse_file(rotated)
        deadlocks = [e for e in entries if e.category == "DEADLOCK"]
        assert len(deadlocks) >= 2

    def test_real_listener_trc(self):
        parser = SunDBListenerTrcParser()
        path = os.path.join(REAL_G1N1_TRC, "listener.trc")
        entries = parser.parse_file(path)
        assert len(entries) > 0
        messages = " ".join(e.message for e in entries)
        assert "LISTENER" in messages

    def test_real_cdc_trc(self):
        parser = SunDBCdcTrcParser()
        path = os.path.join(REAL_G1N1_TRC, "cyrmte_TEST_13.trc")
        if not os.path.exists(path):
            pytest.skip("CDC 文件不存在")
        entries = parser.parse_file(path)
        assert len(entries) > 0
        messages = " ".join(e.message for e in entries)
        assert "LSN" in messages

    def test_real_batch_parse_g1n1(self):
        batch = SunDBBatchParser()
        entries = batch.parse_directory(REAL_G1N1_TRC)
        assert len(entries) > 1000

    def test_real_fault_extraction(self):
        batch = SunDBBatchParser()
        parser = SunDBSystemTrcParser()
        if not os.path.isdir(REAL_G2N2_TRC):
            pytest.skip("G2N2 不存在")
        entries = parser.parse_file(os.path.join(REAL_G2N2_TRC, "system.trc"))
        faults = batch.extract_fault_events(entries)
        assert len(faults) >= 1
        event_types = [f.event_type for f in faults]
        assert "FATAL" in event_types

    def test_real_aeu_conversion(self):
        if not os.path.isdir(REAL_G2N2_TRC):
            pytest.skip("G2N2 不存在")
        batch = SunDBBatchParser()
        parser = SunDBSystemTrcParser()
        entries = parser.parse_file(os.path.join(REAL_G2N2_TRC, "system.trc"))
        faults = batch.extract_fault_events(entries)
        aeu_list = batch.to_aeu_list(faults)
        assert len(aeu_list) >= 1
        for aeu in aeu_list:
            assert aeu.event_id != ""
            assert aeu.timestamp != ""
            assert aeu.event_type != ""
            assert aeu.raw_log_snippet != ""


# ############################################################
# 测试类 19: 边界情况和健壮性
# ############################################################

class TestEdgeCases:
    """边界情况测试"""

    def test_malformed_timestamp(self):
        bad = "[NOT-A-TIMESTAMP INSTANCE(G1N1) THREAD(123,456)] [INFORMATION]\nsome message\n"
        parser = SunDBSystemTrcParser()
        entries = parser.parse(bad)
        assert isinstance(entries, list)

    def test_truncated_entry(self):
        truncated = "[2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] [INFORMATION]\n"
        parser = SunDBSystemTrcParser()
        entries = parser.parse(truncated)
        assert isinstance(entries, list)

    def test_mixed_encoding(self):
        content = SYSTEM_TRC_HEADER + "\n" + SYSTEM_ENTRY_INFORMATION
        tmpdir, trc_dir = create_temp_trc_dir()
        try:
            path = os.path.join(trc_dir, "system.trc")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            parser = SunDBSystemTrcParser()
            entries = parser.parse_file(path)
            assert len(entries) == 1
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_extra_blank_lines(self):
        content = (
            SYSTEM_ENTRY_INFORMATION
            + "\n\n\n"
            + SYSTEM_ENTRY_FATAL
        )
        parser = SunDBSystemTrcParser()
        entries = parser.parse(content)
        assert len(entries) == 2

    def test_very_long_message(self):
        long_msg = "[2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(1,2)] [INFORMATION]\n"
        long_msg += "    " + "A" * 10000 + "\n"
        parser = SunDBSystemTrcParser()
        entries = parser.parse(long_msg)
        assert len(entries) == 1
        assert len(entries[0].message) >= 10000

    def test_consecutive_headers(self):
        content = SYSTEM_TRC_HEADER + "\n" + SYSTEM_TRC_HEADER + "\n" + SYSTEM_ENTRY_INFORMATION
        parser = SunDBSystemTrcParser()
        entries = parser.parse(content)
        assert len(entries) >= 1


# ############################################################
# 测试类 20: 统计功能
# ############################################################

class TestStatistics:
    """测试日志统计功能"""

    def test_count_by_level(self):
        parser = SunDBSystemTrcParser()
        entries = parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        levels = {}
        for e in entries:
            levels[e.level] = levels.get(e.level, 0) + 1
        assert levels["INFORMATION"] == 2
        assert levels["WARNING"] == 1
        assert levels["FATAL"] == 1

    def test_count_by_category(self):
        parser = SunDBSystemTrcParser()
        entries = parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        categories = set(e.category for e in entries)
        assert "REBALANCE" in categories
        assert "CLEANUP" in categories
        assert "DEADLOCK" in categories

    def test_count_error_codes(self):
        parser = SunDBSystemTrcParser()
        entries = parser.parse(SYSTEM_TRC_MULTI_ENTRIES)
        error_codes = [e.error_code for e in entries if e.error_code]
        assert len(error_codes) == 2
        assert "ERR-42000(15017)" in error_codes
        assert "ERR-HY000(11000)" in error_codes


# ############################################################
# 运行入口
# ############################################################

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
