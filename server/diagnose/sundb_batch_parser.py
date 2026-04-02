#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SunDB 批量日志解析器

功能:
  - 自动识别并批量解析目录内所有 .trc 文件
  - 构建跨文件时间线
  - 提取故障事件 (FaultEvent)
  - 转换为 AEU (原子依据单元)
"""

import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from server.diagnose.sundb_trc_parser import (
    SunDBLogEntry,
    SunDBSystemTrcParser,
    SunDBListenerTrcParser,
    SunDBCdcTrcParser,
    SunDBGmonTrcParser,
)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class FaultEvent:
    """故障事件"""
    event_type: str
    timestamp: str
    instance: str
    description: str
    error_code: str
    related_entries: List[SunDBLogEntry]
    severity: str  # critical / high / medium / low


@dataclass
class AEU:
    """原子依据单元 (Atomic Evidence Unit)"""
    event_id: str
    timestamp: str
    event_type: str
    key_fields: Dict[str, str]
    raw_log_snippet: str


# ============================================================
# 批量解析器
# ============================================================

class SunDBBatchParser:
    """批量解析 + 故障提取 + AEU 转换"""

    def __init__(self):
        self._system_parser = SunDBSystemTrcParser()
        self._listener_parser = SunDBListenerTrcParser()
        self._cdc_parser = SunDBCdcTrcParser()
        self._gmon_parser = SunDBGmonTrcParser()

    # ----------------------------------------------------------
    # 批量解析
    # ----------------------------------------------------------

    def parse_directory(self, directory: str) -> List[SunDBLogEntry]:
        """解析目录内所有 trc 文件"""
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"目录不存在: {directory}")

        entries: List[SunDBLogEntry] = []
        for filename in sorted(os.listdir(directory)):
            filepath = os.path.join(directory, filename)
            if not os.path.isfile(filepath):
                continue
            parser = self._detect_parser(filename)
            if parser is None:
                continue
            try:
                file_entries = parser.parse_file(filepath)
                entries.extend(file_entries)
            except Exception:
                continue

        return entries

    def _detect_parser(self, filename: str):
        """根据文件名自动选择解析器"""
        basename = filename.lower()

        if basename.startswith("system.trc"):
            return self._system_parser

        if basename == "listener.trc":
            return self._listener_parser

        if basename.startswith("cyrmte_") and basename.endswith(".trc"):
            return self._cdc_parser

        if basename == "gmon.trc":
            return self._gmon_parser

        return None

    # ----------------------------------------------------------
    # 时间线
    # ----------------------------------------------------------

    def build_timeline(self, entries: List[SunDBLogEntry]) -> List[SunDBLogEntry]:
        """按时间戳排序构建时间线"""
        return sorted(entries, key=lambda e: e.timestamp)

    # ----------------------------------------------------------
    # 故障事件提取
    # ----------------------------------------------------------

    def extract_fault_events(self, entries: List[SunDBLogEntry]) -> List[FaultEvent]:
        """从日志条目中提取故障事件"""
        faults: List[FaultEvent] = []

        for entry in entries:
            fault = self._classify_fault(entry)
            if fault:
                faults.append(fault)

        return faults

    def _classify_fault(self, entry: SunDBLogEntry) -> Optional[FaultEvent]:
        """判断一条日志是否构成故障事件"""
        if entry.level == "FATAL":
            return FaultEvent(
                event_type="FATAL",
                timestamp=entry.timestamp,
                instance=entry.instance,
                description=entry.message,
                error_code=entry.error_code,
                related_entries=[entry],
                severity="critical",
            )

        if entry.category == "DEADLOCK":
            return FaultEvent(
                event_type="DEADLOCK",
                timestamp=entry.timestamp,
                instance=entry.instance,
                description=entry.message,
                error_code=entry.error_code,
                related_entries=[entry],
                severity="high",
            )

        if "DDL failure" in entry.message:
            return FaultEvent(
                event_type="DDL_FAILURE",
                timestamp=entry.timestamp,
                instance=entry.instance,
                description=entry.message,
                error_code=entry.error_code,
                related_entries=[entry],
                severity="medium",
            )

        if entry.error_code and entry.error_code.startswith("ERR-28000"):
            return FaultEvent(
                event_type="AUTH_FAILURE",
                timestamp=entry.timestamp,
                instance=entry.instance,
                description=entry.message,
                error_code=entry.error_code,
                related_entries=[entry],
                severity="high",
            )

        if "failed to create listener" in entry.message.lower():
            return FaultEvent(
                event_type="LISTENER_FAILURE",
                timestamp=entry.timestamp,
                instance=entry.instance,
                description=entry.message,
                error_code=entry.error_code,
                related_entries=[entry],
                severity="high",
            )

        return None

    # ----------------------------------------------------------
    # AEU 转换
    # ----------------------------------------------------------

    def to_aeu_list(self, faults: List[FaultEvent]) -> List[AEU]:
        """将故障事件转换为 AEU 列表"""
        aeu_list: List[AEU] = []
        for fault in faults:
            aeu = self._fault_to_aeu(fault)
            aeu_list.append(aeu)
        return aeu_list

    def _fault_to_aeu(self, fault: FaultEvent) -> AEU:
        """单个 FaultEvent -> AEU"""
        ts_compact = fault.timestamp.replace("-", "").replace(":", "").replace(" ", "").split(".")[0]
        event_id = f"{fault.event_type}-{fault.instance or 'UNKNOWN'}-{ts_compact}-{uuid.uuid4().hex[:6]}"

        key_fields: Dict[str, str] = {
            "instance": fault.instance,
            "error_code": fault.error_code,
        }

        if fault.event_type == "DEADLOCK":
            key_fields.update(self._extract_deadlock_fields(fault))

        raw_snippets = []
        for entry in fault.related_entries:
            raw_snippets.append(entry.message)
            if entry.error_code:
                raw_snippets.append(f"{entry.error_code}: {entry.error_message}")
        raw_log_snippet = "\n".join(raw_snippets)

        return AEU(
            event_id=event_id,
            timestamp=fault.timestamp,
            event_type=fault.event_type,
            key_fields=key_fields,
            raw_log_snippet=raw_log_snippet,
        )

    @staticmethod
    def _extract_deadlock_fields(fault: FaultEvent) -> Dict[str, str]:
        """从 DEADLOCK 故障中提取 session_id 和 sql"""
        fields: Dict[str, str] = {}
        text = fault.description

        m = re.search(r'SESSION_ID\s*:\s*(\d+)', text)
        if m:
            fields["session_id"] = m.group(1)

        m = re.search(r'SQL\s*:\s*(.*)', text)
        if m:
            fields["sql"] = m.group(1).strip()

        return fields
