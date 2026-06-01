"""LILAC 种子模板生成器

从现有 SunDB 正则解析器提取模板，预填充到 LILAC 缓存中，
确保已知 SunDB 格式零 LLM 调用即可命中。
"""

import logging
import os
from typing import List

from server.diagnose.lilac.cache import AdaptiveParsingCache
from server.diagnose.lilac.models import LogTemplate
from server.diagnose.lilac.preprocessor import LogPreprocessor

logger = logging.getLogger(__name__)


def seed_from_sundb_samples(
    sample_dir: str, cache: AdaptiveParsingCache
) -> int:
    """从 SunDB 样本日志目录提取模板种子

    Args:
        sample_dir: 包含 .trc 文件的目录路径
        cache: LILAC 缓存实例

    Returns:
        新增模板数量
    """
    from server.diagnose.sundb_trc_parser import (
        SunDBCdcTrcParser,
        SunDBGmonTrcParser,
        SunDBListenerTrcParser,
        SunDBSystemTrcParser,
    )

    if not os.path.isdir(sample_dir):
        logger.warning(f"Seed directory not found: {sample_dir}")
        return 0

    parsers = {
        "system": SunDBSystemTrcParser(),
        "listener": SunDBListenerTrcParser(),
        "cdc": SunDBCdcTrcParser(),
        "gmon": SunDBGmonTrcParser(),
    }

    preprocessor = LogPreprocessor()
    seeded = 0
    seen_templates = set()

    for filename in sorted(os.listdir(sample_dir)):
        filepath = os.path.join(sample_dir, filename)
        if not os.path.isfile(filepath):
            continue

        parser = _detect_parser(filename, parsers)
        if parser is None:
            continue

        try:
            entries = parser.parse_file(filepath)
        except Exception as e:
            logger.debug(f"Failed to parse {filename}: {e}")
            continue

        for entry in entries:
            if not entry.message:
                continue

            preprocessed = preprocessor.preprocess(entry.message)
            if not preprocessed.tokens:
                continue

            template_str = preprocessed.masked_body
            if template_str in seen_templates:
                continue
            seen_templates.add(template_str)

            template = LogTemplate.from_template_str(template_str, source="seed")
            cache.insert(template, preprocessed.masked_body)
            seeded += 1

    logger.info(f"Seeded {seeded} templates from {sample_dir}")
    return seeded


def _detect_parser(filename: str, parsers: dict):
    """根据文件名选择解析器"""
    basename = filename.lower()
    if basename.startswith("system.trc"):
        return parsers["system"]
    if basename == "listener.trc":
        return parsers["listener"]
    if basename.startswith("cyrmte_") and basename.endswith(".trc"):
        return parsers["cdc"]
    if basename == "gmon.trc":
        return parsers["gmon"]
    return None
