#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SunDB .trc 日志解析器

支持 4 种 SunDB trace 文件格式:
  - system.trc      : 数据库系统日志 (INFORMATION / WARNING / FATAL)
  - listener.trc     : 监听器日志
  - cyrmte_*.trc     : CDC 变更数据捕获日志
  - gmon.trc         : 集群监控日志
"""

import re
from dataclasses import dataclass
from typing import List, Optional


# ============================================================
# 数据结构
# ============================================================

@dataclass
class SunDBLogEntry:
    """单条日志条目"""
    timestamp: str
    instance: str
    thread_pid: int
    thread_tid: int
    level: str
    message: str
    category: str
    error_code: str
    error_message: str
    source_file: str
    raw_text: str


@dataclass
class SunDBFileHeader:
    """trc 文件头信息"""
    instance_name: str
    timestamp: str
    version: str


# ============================================================
# 正则表达式
# ============================================================

# 文件头块
_RE_HEADER_BLOCK = re.compile(
    r'={10,}\s*\n(.*?)={10,}',
    re.DOTALL,
)


# ============================================================
# 基础解析器
# ============================================================

class _BaseTrcParser:
    """所有 trc 解析器的基类"""

    def parse_header(self, content: str) -> Optional[SunDBFileHeader]:
        """解析文件头"""
        m = _RE_HEADER_BLOCK.search(content)
        if not m:
            return None
        block = m.group(1)

        instance_name = ""
        inst_m = re.search(r'INSTANCE\s+NAME\s*:\s*(\S+)', block)
        if inst_m:
            instance_name = inst_m.group(1)

        ts_m = re.search(r'TIME\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)', block)
        timestamp = ts_m.group(1) if ts_m else ""

        ver_m = re.search(r'VERSION\s*:\s*(.+)', block)
        version = ver_m.group(1).strip() if ver_m else ""

        return SunDBFileHeader(
            instance_name=instance_name,
            timestamp=timestamp,
            version=version,
        )

    def parse(self, content: str) -> List[SunDBLogEntry]:
        raise NotImplementedError

    def parse_file(self, path: str) -> List[SunDBLogEntry]:
        """从文件路径解析"""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        entries = self.parse(content)
        for e in entries:
            e.source_file = path
        return entries


# ============================================================
# 解析器占位（后续实现）
# ============================================================

class SunDBSystemTrcParser(_BaseTrcParser):
    """解析 system.trc 文件"""

    def parse(self, content: str) -> List[SunDBLogEntry]:
        # TODO: 实现 system.trc 解析
        return []


class SunDBListenerTrcParser(_BaseTrcParser):
    """解析 listener.trc 文件"""

    def parse(self, content: str) -> List[SunDBLogEntry]:
        # TODO: 实现 listener.trc 解析
        return []


class SunDBCdcTrcParser(_BaseTrcParser):
    """解析 CDC (cyrmte_*.trc) 文件"""

    def parse(self, content: str) -> List[SunDBLogEntry]:
        # TODO: 实现 CDC 解析
        return []


class SunDBGmonTrcParser(_BaseTrcParser):
    """解析 gmon.trc 文件"""

    def parse(self, content: str) -> List[SunDBLogEntry]:
        # TODO: 实现 gmon.trc 解析
        return []
