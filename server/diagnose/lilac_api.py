"""LILAC 日志解析 — REST API

提供 6 个接口:
  POST   /diagnose/lilac/parse         上传任意日志文件解析
  POST   /diagnose/lilac/parse_text    直接提交日志文本解析
  GET    /diagnose/lilac/cache/stats   缓存命中率统计
  GET    /diagnose/lilac/cache/templates 查看已缓存模板
  DELETE /diagnose/lilac/cache         清空缓存
  POST   /diagnose/lilac/seed          触发种子模板生成
"""

import logging
import os
import tempfile
import shutil
from typing import Any, Dict, Optional

from fastapi import Body, File, Query, UploadFile

from server.utils import BaseResponse

logger = logging.getLogger(__name__)

_parser = None


def _get_parser():
    """延迟初始化 LilacParser 单例"""
    global _parser
    if _parser is None:
        from server.diagnose.lilac.parser import LilacParser
        from server.diagnose.lilac.config import LilacConfig
        _parser = LilacParser(LilacConfig())
    return _parser


async def lilac_parse(
    file: UploadFile = File(..., description="任意日志文件"),
) -> BaseResponse:
    """上传任意日志文件，通过 LILAC 解析"""
    filename = file.filename or "unknown.log"
    tmp_dir = tempfile.mkdtemp(prefix="lilac_")
    tmp_path = os.path.join(tmp_dir, filename)

    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        parser = _get_parser()
        result = parser.parse_file(tmp_path)

        entries_data = []
        for e in result.entries:
            entry_dict = {
                "timestamp": e.timestamp,
                "level": e.level,
                "message": e.message,
                "raw_text": e.raw_text,
                "template": e.template.template_str if e.template else None,
                "template_source": e.template.source if e.template else None,
                "parameters": e.parameters,
            }
            entries_data.append(entry_dict)

        data = {
            "filename": filename,
            "total_entries": len(result.entries),
            "cache_hits": result.cache_hits,
            "llm_calls": result.llm_calls,
            "drain3_fallbacks": result.drain3_fallbacks,
            "parse_time_ms": result.parse_time_ms,
            "entries": entries_data,
        }
        return BaseResponse(code=200, msg="Success", data=data)

    except Exception as e:
        logger.exception("lilac_parse failed")
        return BaseResponse(code=500, msg=f"解析失败: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def lilac_parse_text(
    text: str = Body(..., embed=True, description="日志文本内容"),
    source_file: Optional[str] = Body(None, embed=True, description="来源文件名(可选)"),
) -> BaseResponse:
    """直接提交日志文本解析"""
    try:
        parser = _get_parser()
        result = parser.parse_content(text, source_file=source_file)

        entries_data = []
        for e in result.entries:
            entry_dict = {
                "timestamp": e.timestamp,
                "level": e.level,
                "message": e.message,
                "template": e.template.template_str if e.template else None,
                "template_source": e.template.source if e.template else None,
                "parameters": e.parameters,
            }
            entries_data.append(entry_dict)

        data = {
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
