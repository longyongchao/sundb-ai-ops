"""LILAC 日志解析 — REST API

提供 8 个接口:
  POST   /diagnose/lilac/parse         上传任意日志文件解析（支持 .csv 自动转换）
  POST   /diagnose/lilac/parse_csv     上传 CSV 日志文件，返回列推断结果 + 解析结果
  POST   /diagnose/lilac/parse_text    直接提交日志文本解析
  GET    /diagnose/lilac/cache/stats   缓存命中率统计
  GET    /diagnose/lilac/cache/templates 查看已缓存模板
  DELETE /diagnose/lilac/cache         清空缓存
  POST   /diagnose/lilac/seed          触发种子模板生成
"""

import logging
import os
import re
import tempfile
import shutil
from typing import Any, Dict, List, Optional

from fastapi import Body, File, Query, UploadFile

from server.utils import BaseResponse

logger = logging.getLogger(__name__)

_parser = None
_PARSE_MODES = {"auto", "llm", "drain3"}


def _get_parser():
    """延迟初始化 LilacParser 单例"""
    global _parser
    if _parser is None:
        from server.diagnose.lilac.parser import LilacParser
        from server.diagnose.lilac.config import LilacConfig
        _parser = LilacParser(LilacConfig())
    return _parser


def _normalize_parse_mode(parse_mode: Optional[str]) -> str:
    """规范化前端传入的解析模式，未知值回退到 auto 保持兼容。"""
    mode = (parse_mode or "auto").strip().lower()
    return mode if mode in _PARSE_MODES else "auto"


async def lilac_parse(
    file: UploadFile = File(..., description="任意日志文件（支持 .log/.txt/.csv 等格式）"),
    parse_mode: str = Query("auto", description="解析模式: auto / llm / drain3"),
) -> BaseResponse:
    """上传任意日志文件，通过 LILAC 解析。

    若上传 .csv 文件，会先通过 CsvLogConverter 自动识别列角色并转换为标准 .log 文本，
    再交给 LILAC 进行模板提取与结构化解析。
    """
    filename = file.filename or "unknown.log"
    mode = _normalize_parse_mode(parse_mode)
    tmp_dir = tempfile.mkdtemp(prefix="lilac_")
    tmp_path = os.path.join(tmp_dir, filename)

    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        parser = _get_parser()
        csv_meta = None

        if filename.lower().endswith(".csv"):
            from server.diagnose.csv_log_converter import CsvLogConverter
            converter = CsvLogConverter()
            conv_result = converter.convert_file(tmp_path, encoding="utf-8")
            result = parser.parse_content(
                conv_result.log_text, source_file=filename, parse_mode=mode
            )
            csv_meta = {
                "total_rows": conv_result.total_rows,
                "converted_rows": conv_result.converted_rows,
                "schema": {
                    "timestamp_col": conv_result.schema.timestamp_col,
                    "level_col": conv_result.schema.level_col,
                    "message_col": conv_result.schema.message_col,
                    "extra_cols": conv_result.schema.extra_cols,
                },
                "warnings": conv_result.warnings,
            }
            logger.info(
                f"[LILAC] CSV 转换完成: {filename}, "
                f"rows={conv_result.total_rows}, converted={conv_result.converted_rows}"
            )
        else:
            result = parser.parse_file(tmp_path, parse_mode=mode)

        entries_data = []
        for e in result.entries:
            metadata = {k: v for k, v in e.metadata.items() if not k.startswith("_")}
            entry_dict = {
                "timestamp": e.timestamp,
                "level": e.level,
                "message": e.message,
                "raw_text": e.raw_text,
                "template": e.template.template_str if e.template else None,
                "template_source": e.template.source if e.template else None,
                "parameters": e.parameters,
                "metadata": metadata if metadata else None,
            }
            entries_data.append(entry_dict)

        data = {
            "filename": filename,
            "parse_mode": mode,
            "total_entries": len(result.entries),
            "cache_hits": result.cache_hits,
            "llm_calls": result.llm_calls,
            "drain3_fallbacks": result.drain3_fallbacks,
            "parse_time_ms": result.parse_time_ms,
            "entries": entries_data,
        }
        if csv_meta is not None:
            data["csv_conversion"] = csv_meta
        return BaseResponse(code=200, msg="Success", data=data)

    except Exception as e:
        logger.exception("lilac_parse failed")
        return BaseResponse(code=500, msg=f"解析失败: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def lilac_parse_csv(
    file: UploadFile = File(..., description="CSV 格式日志文件"),
    parse_mode: str = Query("auto", description="解析模式: auto / llm / drain3"),
) -> BaseResponse:
    """上传 CSV 日志文件，返回列角色推断 + LILAC 解析 + 服务端准确率验证。

    响应中包含：
    - csv_conversion: 列角色推断结果与转换统计
    - entries: LILAC 结构化解析结果
    - field_checks: 逐行字段对比结果
    - accuracy: 聚合准确率指标
    """
    filename = file.filename or "unknown.csv"
    mode = _normalize_parse_mode(parse_mode)
    tmp_dir = tempfile.mkdtemp(prefix="lilac_csv_")
    tmp_path = os.path.join(tmp_dir, filename)

    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        from server.diagnose.csv_log_converter import CsvLogConverter
        converter = CsvLogConverter()
        conv_result = converter.convert_file(tmp_path, encoding="utf-8")

        parser = _get_parser()
        result = parser.parse_content(
            conv_result.log_text, source_file=filename, parse_mode=mode
        )

        entries_data = []
        for e in result.entries:
            metadata = {k: v for k, v in e.metadata.items() if not k.startswith("_")}
            entries_data.append({
                "timestamp": e.timestamp,
                "level": e.level,
                "message": e.message,
                "raw_text": e.raw_text,
                "template": e.template.template_str if e.template else None,
                "template_source": e.template.source if e.template else None,
                "parameters": e.parameters,
                "metadata": metadata if metadata else None,
            })

        schema = conv_result.schema
        csv_rows = conv_result.csv_rows
        row_mapping = conv_result.row_mapping

        field_checks, accuracy = _compute_field_checks(
            csv_rows, row_mapping, entries_data, schema, converter
        )

        data = {
            "filename": filename,
            "parse_mode": mode,
            "csv_conversion": {
                "total_rows": conv_result.total_rows,
                "converted_rows": conv_result.converted_rows,
                "schema": {
                    "timestamp_col": schema.timestamp_col,
                    "level_col": schema.level_col,
                    "message_col": schema.message_col,
                    "extra_cols": schema.extra_cols,
                },
                "warnings": conv_result.warnings,
                "converted_preview": conv_result.log_text.splitlines()[:5],
                "row_mapping": row_mapping,
            },
            "total_entries": len(result.entries),
            "cache_hits": result.cache_hits,
            "llm_calls": result.llm_calls,
            "drain3_fallbacks": result.drain3_fallbacks,
            "parse_time_ms": result.parse_time_ms,
            "entries": entries_data,
            "csv_rows": csv_rows,
            "field_checks": field_checks,
            "accuracy": accuracy,
        }
        return BaseResponse(code=200, msg="Success", data=data)

    except Exception as e:
        logger.exception("lilac_parse_csv failed")
        return BaseResponse(code=500, msg=f"CSV 解析失败: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ------------------------------------------------------------------
# 服务端字段对比与准确率计算
# ------------------------------------------------------------------

_LEVEL_NORMALIZE_MAP = {
    "info": "INFO", "information": "INFO", "notice": "INFO",
    "normal": "INFO", "healthy": "INFO",
    "debug": "DEBUG", "trace": "TRACE",
    "warn": "WARNING", "warning": "WARNING",
    "timeout": "WARNING", "cancelled": "WARNING",
    "canceled": "WARNING", "rejected": "WARNING",
    "abnormal": "WARNING", "unhealthy": "WARNING",
    "error": "ERROR", "err": "ERROR",
    "fail": "ERROR", "failed": "ERROR", "failure": "ERROR",
    "exception": "ERROR",
    "fatal": "FATAL", "critical": "FATAL",
    "severe": "FATAL", "alert": "FATAL", "emerg": "FATAL",
    "succeed": "INFO", "success": "INFO", "ok": "INFO",
    "pass": "INFO", "passed": "INFO", "done": "INFO",
    "running": "INFO", "pending": "INFO", "skipped": "INFO",
}


def _normalize_level(raw: str) -> Optional[str]:
    """与 CsvLogConverter._LEVEL_NORMALIZE 一致的级别映射"""
    if not raw or not raw.strip():
        return None
    return _LEVEL_NORMALIZE_MAP.get(raw.strip().lower(), raw.strip().upper())


def _compute_field_checks(csv_rows, row_mapping, entries_data, schema, converter):
    """逐行对比 CSV 原始值与 LILAC 解析结果，返回 field_checks 和聚合 accuracy"""
    field_checks = []
    ts_match = ts_total = 0
    lv_match = lv_total = 0
    msg_match = msg_total = 0
    extra_match = extra_total = 0
    tpl_placeholder = 0
    full_row_match = 0
    checked_rows = 0

    for entry_idx, entry in enumerate(entries_data):
        if entry_idx >= len(row_mapping):
            break
        csv_row_idx = row_mapping[entry_idx]
        if csv_row_idx >= len(csv_rows):
            break
        csv_row = csv_rows[csv_row_idx]

        row_checks = []
        row_all_match = True
        has_non_na = False

        msg = entry.get("message") or ""

        # 时间戳
        if schema.timestamp_col:
            orig = (csv_row.get(schema.timestamp_col) or "").strip()
            if orig:
                expected = converter._normalize_timestamp(orig)
                parsed = (entry.get("timestamp") or "").strip()
                matched = (expected == parsed)
                row_checks.append({
                    "col": schema.timestamp_col, "role": "timestamp",
                    "original": orig, "expected": expected, "parsed": parsed,
                    "match": matched,
                })
                ts_total += 1
                if matched:
                    ts_match += 1
                else:
                    row_all_match = False
                has_non_na = True
            else:
                row_checks.append({
                    "col": schema.timestamp_col, "role": "timestamp",
                    "original": "", "expected": "", "parsed": entry.get("timestamp", ""),
                    "match": None,
                })

        # 级别
        if schema.level_col:
            orig = (csv_row.get(schema.level_col) or "").strip()
            if orig:
                expected = _normalize_level(orig)
                parsed = (entry.get("level") or "").upper()
                matched = (expected == parsed) if expected else False
                row_checks.append({
                    "col": schema.level_col, "role": "level",
                    "original": orig, "expected": expected, "parsed": parsed,
                    "match": matched,
                })
                lv_total += 1
                if matched:
                    lv_match += 1
                else:
                    row_all_match = False
                has_non_na = True
            else:
                row_checks.append({
                    "col": schema.level_col, "role": "level",
                    "original": "", "expected": "", "parsed": entry.get("level", ""),
                    "match": None,
                })

        # 消息列
        if schema.message_col:
            orig = (csv_row.get(schema.message_col) or "").strip()
            if orig:
                matched = msg.startswith(orig)
                row_checks.append({
                    "col": schema.message_col, "role": "message",
                    "original": orig, "expected": orig,
                    "parsed": msg[:len(orig) + 30],
                    "match": matched,
                })
                msg_total += 1
                if matched:
                    msg_match += 1
                else:
                    row_all_match = False
                has_non_na = True
            else:
                row_checks.append({
                    "col": schema.message_col, "role": "message",
                    "original": "", "expected": "", "parsed": msg[:50],
                    "match": None,
                })

        # 附加列
        for col in (schema.extra_cols or []):
            orig = (csv_row.get(col) or "").strip()
            if orig:
                expected_kv = f"{col}={orig}"
                matched = expected_kv in msg
                row_checks.append({
                    "col": col, "role": "extra",
                    "original": orig, "expected": expected_kv,
                    "parsed": expected_kv if matched else "",
                    "match": matched,
                })
                extra_total += 1
                if matched:
                    extra_match += 1
                else:
                    row_all_match = False
                has_non_na = True
            else:
                row_checks.append({
                    "col": col, "role": "extra",
                    "original": "", "expected": "", "parsed": "",
                    "match": None,
                })

        # 模板变量
        tpl = entry.get("template") or ""
        if "<*>" in tpl:
            tpl_placeholder += 1

        if has_non_na and row_all_match:
            full_row_match += 1
        checked_rows += 1

        field_checks.append({
            "csv_row_idx": csv_row_idx,
            "entry_idx": entry_idx,
            "checks": row_checks,
            "all_match": row_all_match if has_non_na else None,
        })

    def pct(a, b):
        return round(a / b * 100) if b > 0 else None

    accuracy = {
        "checked_rows": checked_rows,
        "full_row_match": full_row_match,
        "full_pct": pct(full_row_match, checked_rows),
        "ts_match": ts_match, "ts_total": ts_total, "ts_pct": pct(ts_match, ts_total),
        "lv_match": lv_match, "lv_total": lv_total, "lv_pct": pct(lv_match, lv_total),
        "msg_match": msg_match, "msg_total": msg_total, "msg_pct": pct(msg_match, msg_total),
        "extra_match": extra_match, "extra_total": extra_total, "extra_pct": pct(extra_match, extra_total),
        "tpl_placeholder": tpl_placeholder, "tpl_pct": pct(tpl_placeholder, checked_rows),
        "row_alignment": "exact" if len(entries_data) == len(csv_rows) else "partial",
        "skipped_rows": len(csv_rows) - len(row_mapping),
    }

    return field_checks, accuracy


async def lilac_parse_text(
    text: str = Body(..., embed=True, description="日志文本内容"),
    source_file: Optional[str] = Body(None, embed=True, description="来源文件名(可选)"),
    parse_mode: str = Body("auto", embed=True, description="解析模式: auto / llm / drain3"),
    regex: Optional[List[Dict]] = Body(None, embed=True, description="自定义正则预处理规则列表，每项含 pattern 和可选 replacement(默认<*>)"),
) -> BaseResponse:
    """直接提交日志文本解析

    regex 参数示例:
      [{"pattern": "(\\d+\\.){3}\\d+", "replacement": "<*>"},
       {"pattern": "blk_-?\\d+"}]

    处理顺序: 调用方 regex → 内置 MASK_PATTERNS → cache/Drain3/LLM
    """
    try:
        mode = _normalize_parse_mode(parse_mode)
        if regex:
            compiled = []
            for r in regex:
                pat = re.compile(r["pattern"])
                rep = r.get("replacement", "<*>")
                compiled.append((pat, rep))
            lines = text.splitlines()
            processed = []
            for line in lines:
                for pat, rep in compiled:
                    line = pat.sub(rep, line)
                processed.append(line)
            text = "\n".join(processed)

        parser = _get_parser()
        result = parser.parse_content(text, source_file=source_file, parse_mode=mode)

        entries_data = []
        for e in result.entries:
            metadata = {k: v for k, v in e.metadata.items() if not k.startswith("_")}
            entry_dict = {
                "timestamp": e.timestamp,
                "level": e.level,
                "message": e.message,
                "template": e.template.template_str if e.template else None,
                "template_source": e.template.source if e.template else None,
                "parameters": e.parameters,
                "metadata": metadata if metadata else None,
            }
            entries_data.append(entry_dict)

        data = {
            "parse_mode": mode,
            "total_entries": len(result.entries),
            "cache_hits": result.cache_hits,
            "llm_calls": result.llm_calls,
            "drain3_fallbacks": result.drain3_fallbacks,
            "parse_time_ms": result.parse_time_ms,
            "entries": entries_data,
        }
        return BaseResponse(code=200, msg="Success", data=data)

    except Exception as e:
        logger.exception("lilac_parse_text failed")
        return BaseResponse(code=500, msg=f"解析失败: {e}")


async def lilac_cache_stats() -> BaseResponse:
    """获取 LILAC 缓存统计信息"""
    try:
        parser = _get_parser()
        stats = parser.get_cache().get_statistics()
        return BaseResponse(code=200, msg="Success", data=stats)
    except Exception as e:
        logger.exception("lilac_cache_stats failed")
        return BaseResponse(code=500, msg=f"获取统计失败: {e}")


async def lilac_cache_templates(
    limit: int = Query(100, description="返回模板数上限"),
    offset: int = Query(0, description="偏移量"),
) -> BaseResponse:
    """查看已缓存的模板列表"""
    try:
        parser = _get_parser()
        cache = parser.get_cache()

        with cache._lock:
            cursor = cache._conn.execute(
                "SELECT template_id, template_str, hit_count, source, created_at "
                "FROM templates ORDER BY hit_count DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()

        templates = [
            {
                "template_id": row[0],
                "template_str": row[1],
                "hit_count": row[2],
                "source": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]

        total_cursor = cache._conn.execute("SELECT COUNT(*) FROM templates")
        total = total_cursor.fetchone()[0]

        return BaseResponse(code=200, msg="Success", data={
            "total": total,
            "returned": len(templates),
            "templates": templates,
        })
    except Exception as e:
        logger.exception("lilac_cache_templates failed")
        return BaseResponse(code=500, msg=f"获取模板失败: {e}")


async def lilac_cache_clear() -> BaseResponse:
    """清空 LILAC 缓存"""
    try:
        parser = _get_parser()
        parser.get_cache().clear()
        return BaseResponse(code=200, msg="缓存已清空", data=None)
    except Exception as e:
        logger.exception("lilac_cache_clear failed")
        return BaseResponse(code=500, msg=f"清空缓存失败: {e}")


async def lilac_seed(
    sample_dir: str = Body(..., embed=True, description="SunDB 样本日志目录路径"),
) -> BaseResponse:
    """触发种子模板生成（从 SunDB 样本）"""
    try:
        from server.diagnose.lilac.seed import seed_from_sundb_samples

        parser = _get_parser()
        cache = parser.get_cache()
        count = seed_from_sundb_samples(sample_dir, cache)

        return BaseResponse(code=200, msg="Success", data={
            "templates_added": count,
            "sample_dir": sample_dir,
        })
    except Exception as e:
        logger.exception("lilac_seed failed")
        return BaseResponse(code=500, msg=f"种子生成失败: {e}")
