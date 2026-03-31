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

# system.trc 条目头:
#   [2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] [INFORMATION]
_RE_SYSTEM_ENTRY = re.compile(
    r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)'   # timestamp
    r'\s+INSTANCE\((\w+)\)'                                  # instance
    r'\s+THREAD\((\d+),(\d+)\)\]'                            # thread_pid, thread_tid
    r'\s+\[(\w+)\]',                                         # level
    re.MULTILINE,
)

# 错误码: (INSTANCE) ERR-XXXXX(NNNNN): message
_RE_ERROR_CODE = re.compile(
    r'\((\w+)\)\s+(ERR-[\w]+\(\d+\))\s*[:\s]\s*(.*)',
)

# 独立错误码: ERR-28000(16004) : message
_RE_ERROR_CODE_STANDALONE = re.compile(
    r'(ERR-[\w]+\(\d+\))\s*[:\s]\s*(.*)',
)

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
        entries: List[SunDBLogEntry] = []
        matches = list(_RE_SYSTEM_ENTRY.finditer(content))
        if not matches:
            return entries

        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            raw_block = content[start:end].strip()

            timestamp = m.group(1)
            instance = m.group(2)
            thread_pid = int(m.group(3))
            thread_tid = int(m.group(4))
            level = m.group(5)

            header_end = m.end()
            body = content[header_end:end].strip()

            category = self._extract_category(body)
            error_code, error_message = self._extract_error(body)

            message = "\n".join(
                line for line in body.splitlines() if line.strip()
            )

            entries.append(SunDBLogEntry(
                timestamp=timestamp,
                instance=instance,
                thread_pid=thread_pid,
                thread_tid=thread_tid,
                level=level,
                message=message,
                category=category,
                error_code=error_code,
                error_message=error_message,
                source_file="",
                raw_text=raw_block,
            ))

        return entries

    @staticmethod
    def _extract_category(body: str) -> str:
        """从消息体提取类别标签"""
        first_line = body.split("\n")[0].strip() if body else ""
        cat_m = re.match(r'\[([A-Z][A-Z_ ]*[A-Z])\]', first_line)
        if cat_m:
            return cat_m.group(1)
        cat_m2 = re.search(r'\[([A-Z][A-Z_ ]*[A-Z])\]', first_line)
        if cat_m2:
            return cat_m2.group(1)
        return ""

    @staticmethod
    def _extract_error(body: str) -> tuple:
        """从消息体提取错误码和错误消息"""
        for line in body.splitlines():
            line = line.strip()
            m = _RE_ERROR_CODE.match(line)
            if m:
                return m.group(2), m.group(3).strip()
            m2 = _RE_ERROR_CODE_STANDALONE.match(line)
            if m2:
                return m2.group(1), m2.group(2).strip()
        return "", ""


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
