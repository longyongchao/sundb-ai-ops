#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SunDB .trc 日志解析 — REST API

提供 5 个接口:
  POST /diagnose/upload_trc           上传单个 trc 文件
  POST /diagnose/upload_trc_directory 上传 tar.gz 压缩包批量解析
  GET  /diagnose/trc/fault_events     获取故障事件列表
  GET  /diagnose/trc/timeline         获取跨文件时间线
  GET  /diagnose/trc/aeu_list         获取 AEU 列表
"""

import os
import tarfile
import tempfile
import shutil
import logging
from collections import Counter
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import File, Query, UploadFile

from server.utils import BaseResponse
from server.diagnose.sundb_trc_parser import (
    SunDBSystemTrcParser,
    SunDBListenerTrcParser,
    SunDBCdcTrcParser,
    SunDBGmonTrcParser,
)
from server.diagnose.sundb_batch_parser import SunDBBatchParser

logger = logging.getLogger(__name__)

# 全局缓存: 最近一次解析结果 (供 GET 接口查询)
_last_entries: List = []
_last_faults: List = []
_last_aeu_list: List = []

_batch_parser = SunDBBatchParser()


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _detect_parser_for_file(filename: str):
    """根据文件名选择解析器, 返回 (parser, parser_type_str)"""
    basename = filename.lower()
    if basename.startswith("system.trc"):
        return SunDBSystemTrcParser(), "system"
    if basename == "listener.trc":
        return SunDBListenerTrcParser(), "listener"
    if basename.startswith("cyrmte_") and basename.endswith(".trc"):
        return SunDBCdcTrcParser(), "cdc"
    if basename == "gmon.trc":
        return SunDBGmonTrcParser(), "gmon"
    return None, "unknown"


def _entry_to_dict(entry) -> Dict[str, Any]:
    """SunDBLogEntry → 可序列化字典 (排除 raw_text 减少体积)"""
    return {
        "timestamp": entry.timestamp,
        "instance": entry.instance,
        "level": entry.level,
        "message": entry.message or "",
        "category": entry.category,
        "error_code": entry.error_code,
        "error_message": entry.error_message,
        "source_file": os.path.basename(entry.source_file) if entry.source_file else "",
    }


def _fault_to_dict(fault) -> Dict[str, Any]:
    return {
        "event_type": fault.event_type,
        "timestamp": fault.timestamp,
        "instance": fault.instance,
        "description": fault.description or "",
        "error_code": fault.error_code,
        "severity": fault.severity,
    }


def _aeu_to_dict(aeu) -> Dict[str, Any]:
    return {
        "event_id": aeu.event_id,
        "timestamp": aeu.timestamp,
        "event_type": aeu.event_type,
        "key_fields": aeu.key_fields,
        "raw_log_snippet": aeu.raw_log_snippet or "",
    }


# ------------------------------------------------------------------
# POST /diagnose/upload_trc
# ------------------------------------------------------------------

async def upload_trc(
    file: UploadFile = File(..., description="单个 .trc 文件"),
    offset: int = Query(0, description="条目偏移量 (分页起始位置)"),
    limit: int = Query(0, description="返回条目数上限, 0 表示全部返回"),
) -> BaseResponse:
    """上传单个 .trc 文件并解析"""
    global _last_entries, _last_faults, _last_aeu_list

    filename = file.filename or "unknown.trc"
    parser, parser_type = _detect_parser_for_file(filename)

    if parser is None:
        return BaseResponse(code=400, msg=f"无法识别的文件类型: {filename}")

    # 写入临时文件
    tmp_dir = tempfile.mkdtemp(prefix="sundb_trc_")
    tmp_path = os.path.join(tmp_dir, filename)
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        entries = parser.parse_file(tmp_path)
        header = parser.parse_header(content.decode("utf-8", errors="replace"))

        faults = _batch_parser.extract_fault_events(entries)
        aeu_list = _batch_parser.to_aeu_list(faults)

        # 缓存
        _last_entries = entries
        _last_faults = faults
        _last_aeu_list = aeu_list

        # 统计
        level_counter = Counter(e.level for e in entries if e.level)

        data = {
            "filename": filename,
            "parser_type": parser_type,
            "header": asdict(header) if header else None,
            "total_entries": len(entries),
            "entries_by_level": dict(level_counter),
            "fault_count": len(faults),
            "entries": [_entry_to_dict(e) for e in
                        (entries[offset:offset + limit] if limit > 0 else entries[offset:])],
        }
        return BaseResponse(code=200, msg="Success", data=data)

    except Exception as e:
        logger.exception("upload_trc failed")
        return BaseResponse(code=500, msg=f"解析失败: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ------------------------------------------------------------------
# POST /diagnose/upload_trc_directory
# ------------------------------------------------------------------

async def upload_trc_directory(
    file: UploadFile = File(..., description=".tar.gz 压缩包"),
    offset: int = Query(0, description="条目偏移量 (分页起始位置)"),
    limit: int = Query(0, description="返回条目数上限, 0 表示全部返回"),
) -> BaseResponse:
    """上传 tar.gz 压缩包并批量解析"""
    global _last_entries, _last_faults, _last_aeu_list

    filename = file.filename or "unknown.tar.gz"
    tmp_dir = tempfile.mkdtemp(prefix="sundb_trc_batch_")

    try:
        # 保存上传文件
        archive_path = os.path.join(tmp_dir, filename)
        content = await file.read()
        with open(archive_path, "wb") as f:
            f.write(content)

        # 解压
        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=extract_dir)

        # 找到包含 trc 文件的目录 (可能嵌套一层)
        trc_dir = extract_dir
        for root, dirs, files in os.walk(extract_dir):
            if any(f.endswith(".trc") for f in files):
                trc_dir = root
                break

        # 批量解析
        entries = _batch_parser.parse_directory(trc_dir)
        timeline = _batch_parser.build_timeline(entries)
        faults = _batch_parser.extract_fault_events(timeline)
        aeu_list = _batch_parser.to_aeu_list(faults)

        # 缓存
        _last_entries = timeline
        _last_faults = faults
        _last_aeu_list = aeu_list

        # 统计
        files_parsed = sorted(set(
            os.path.basename(e.source_file) for e in entries if e.source_file
        ))
        type_counter = Counter(f.event_type for f in faults)
        severity_counter = Counter(f.severity for f in faults)

        data = {
            "filename": filename,
            "files_parsed": files_parsed,
            "total_entries": len(entries),
            "timeline_range": {
                "earliest": timeline[0].timestamp if timeline else "",
                "latest": timeline[-1].timestamp if timeline else "",
            },
            "fault_summary": {
                "total": len(faults),
                "by_type": dict(type_counter),
                "by_severity": dict(severity_counter),
            },
            "entries": [_entry_to_dict(e) for e in
                        (timeline[offset:offset + limit] if limit > 0 else timeline[offset:])],
            "aeu_list": [_aeu_to_dict(a) for a in aeu_list],
        }
        return BaseResponse(code=200, msg="Success", data=data)

    except Exception as e:
        logger.exception("upload_trc_directory failed")
        return BaseResponse(code=500, msg=f"批量解析失败: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ------------------------------------------------------------------
# GET /diagnose/trc/fault_events
# ------------------------------------------------------------------

async def get_trc_fault_events(
    severity: Optional[str] = Query(None, description="按严重程度过滤: critical/high/medium"),
    event_type: Optional[str] = Query(None, description="按事件类型过滤: FATAL/DEADLOCK/DDL_FAILURE/AUTH_FAILURE/LISTENER_FAILURE"),
    limit: int = Query(100, description="返回条数上限"),
) -> BaseResponse:
    """获取最近一次解析的故障事件列表"""
    faults = _last_faults

    if severity:
        faults = [f for f in faults if f.severity == severity]
    if event_type:
        faults = [f for f in faults if f.event_type == event_type]

    return BaseResponse(code=200, msg="Success", data={
        "total": len(faults),
        "faults": [_fault_to_dict(f) for f in faults[:limit]],
    })


# ------------------------------------------------------------------
# GET /diagnose/trc/timeline
# ------------------------------------------------------------------

async def get_trc_timeline(
    start_time: Optional[str] = Query(None, description="起始时间 (ISO 格式)"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    level: Optional[str] = Query(None, description="INFORMATION/WARNING/FATAL"),
    instance: Optional[str] = Query(None, description="节点过滤: G1N1/G1N2/G2N1/G2N2"),
    limit: int = Query(200, description="返回条数上限"),
) -> BaseResponse:
    """获取跨文件统一时间线"""
    entries = _last_entries

    if start_time:
        entries = [e for e in entries if e.timestamp >= start_time]
    if end_time:
        entries = [e for e in entries if e.timestamp <= end_time]
    if level:
        entries = [e for e in entries if e.level == level]
    if instance:
        entries = [e for e in entries if e.instance == instance]

    return BaseResponse(code=200, msg="Success", data={
        "total": len(entries),
        "returned": min(len(entries), limit),
        "entries": [_entry_to_dict(e) for e in entries[:limit]],
    })


# ------------------------------------------------------------------
# GET /diagnose/trc/aeu_list
# ------------------------------------------------------------------

async def get_trc_aeu_list(
    event_type: Optional[str] = Query(None, description="按事件类型过滤"),
) -> BaseResponse:
    """获取 AEU 列表"""
    aeu_list = _last_aeu_list

    if event_type:
        aeu_list = [a for a in aeu_list if a.event_type == event_type]

    return BaseResponse(code=200, msg="Success", data={
        "total": len(aeu_list),
        "aeu_list": [_aeu_to_dict(a) for a in aeu_list],
    })
