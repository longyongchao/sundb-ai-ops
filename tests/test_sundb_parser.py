#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SunDB .trc 日志解析器 — 单元测试（Day 1: 数据结构 + 文件头解析）

测试覆盖:
  1. SunDBLogEntry 数据结构
  2. SunDBFileHeader 解析

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
# 运行入口
# ############################################################

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
