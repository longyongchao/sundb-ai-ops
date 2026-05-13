"""LILAC 主编排器：统一日志解析入口"""

import logging
import os
import re
import time
from typing import List, Optional

from server.diagnose.lilac.cache import AdaptiveParsingCache
from server.diagnose.lilac.config import LilacConfig
from server.diagnose.lilac.demonstration_pool import DemonstrationPool
from server.diagnose.lilac.drain3_fallback import Drain3Fallback
from server.diagnose.lilac.llm_template_extractor import LLMTemplateExtractor
from server.diagnose.lilac.models import GenericLogEntry, LogTemplate, ParseResult
from server.diagnose.lilac.preprocessor import LogPreprocessor

logger = logging.getLogger(__name__)


class LilacParser:
    """LILAC 统一日志解析器

    流程：预处理 → 缓存查找 → LLM 提取 → Drain3 兜底
    """

    def __init__(self, config: Optional[LilacConfig] = None):
        self._config = config or LilacConfig()

        self._preprocessor = LogPreprocessor()
        self._cache = AdaptiveParsingCache(
            db_path=self._config.cache_db_path,
            similarity_threshold=self._config.cache_similarity_threshold,
        )
        self._demo_pool = DemonstrationPool(
            conn=self._cache._conn,
            max_size=self._config.demo_pool_max,
        )
        self._llm_extractor = LLMTemplateExtractor(
            temperature=self._config.llm_temperature,
            timeout=self._config.llm_timeout,
        ) if self._config.enable_llm else None

        self._drain3 = Drain3Fallback() if self._config.enable_drain3 else None

    def parse_line(
        self, raw_line: str, source_file: str = "", line_number: int = 0
    ) -> GenericLogEntry:
        """解析单行日志"""
        preprocessed = self._preprocessor.preprocess(raw_line)

        if not preprocessed.tokens:
            return GenericLogEntry(
                raw_text=raw_line,
                message=preprocessed.body or raw_line,
                source_file=source_file,
                line_number=line_number,
                metadata=preprocessed.header_fields,
                timestamp=preprocessed.header_fields.get("timestamp", ""),
                level=preprocessed.header_fields.get("level", ""),
            )

        template: Optional[LogTemplate] = None
        source = ""

        # (1) 缓存查找
        template = self._cache.lookup(preprocessed.tokens)
        if template:
            source = "cache"
        else:
            # (2) LLM 提取
            if self._llm_extractor:
                demos = self._demo_pool.sample(
                    preprocessed.tokens, k=self._config.demo_sample_k
                )
                template = self._llm_extractor.extract(
                    preprocessed.masked_body, demos
                )
                if template:
                    source = "llm"
                    self._cache.insert(template, preprocessed.masked_body)

            # (3) Drain3 兜底
            if template is None and self._drain3 and self._drain3.available:
                template = self._drain3.parse(preprocessed.masked_body)
                if template:
                    source = "drain3"
                    self._cache.insert(template, preprocessed.masked_body)

        raw_body_tokens = preprocessed.body.split() if preprocessed.body else preprocessed.raw_text.split()
        parameters = self._extract_parameters(raw_body_tokens, template)

        metadata = dict(preprocessed.header_fields)
        if source:
            metadata["_parse_source"] = source

        return GenericLogEntry(
            timestamp=preprocessed.header_fields.get("timestamp", ""),
            level=preprocessed.header_fields.get("level", ""),
            message=preprocessed.body,
            template=template,
            parameters=parameters,
            source_file=source_file,
            line_number=line_number,
            raw_text=raw_line,
            metadata=metadata,
        )

    def parse_content(self, content: str, source_file: str = "") -> ParseResult:
        """解析日志文本内容"""
        start = time.time()
        raw_lines = content.splitlines()
        assembled = self._assemble_multiline(raw_lines)
        total = len(assembled)

        logger.info(f"[LILAC] 开始解析: {total} 条日志 (source={source_file or 'text'})")

        entries: List[GenericLogEntry] = []
        cache_hits = 0
        llm_calls = 0
        drain3_fallbacks = 0

        for idx, (line_num, line) in enumerate(assembled, 1):
            entry = self.parse_line(line, source_file=source_file, line_number=line_num)
            entries.append(entry)

            parse_source = entry.metadata.get("_parse_source", "")
            if parse_source == "cache":
                cache_hits += 1
            elif parse_source == "llm":
                llm_calls += 1
                logger.info(
                    f"[LILAC] [{idx}/{total}] LLM调用 #{llm_calls} | "
                    f"缓存命中: {cache_hits} | line={line_num}"
                )
            elif parse_source == "drain3":
                drain3_fallbacks += 1

            if idx % 50 == 0 or idx == total:
                elapsed = (time.time() - start) * 1000.0
                logger.info(
                    f"[LILAC] 进度 {idx}/{total} | "
                    f"缓存命中: {cache_hits}, LLM: {llm_calls}, Drain3: {drain3_fallbacks} | "
                    f"耗时: {elapsed:.0f}ms"
                )

        elapsed_ms = (time.time() - start) * 1000.0
        logger.info(
            f"[LILAC] 解析完成: {total} 条 | "
            f"缓存命中: {cache_hits}, LLM: {llm_calls}, Drain3: {drain3_fallbacks} | "
            f"总耗时: {elapsed_ms:.0f}ms"
        )

        return ParseResult(
            entries=entries,
            cache_hits=cache_hits,
            llm_calls=llm_calls,
            drain3_fallbacks=drain3_fallbacks,
            parse_time_ms=elapsed_ms,
        )

    def _assemble_multiline(self, raw_lines: List[str]) -> List[tuple]:
        """组装多行日志（处理 SunDB 等 header/body 分行格式）

        返回 [(line_number, assembled_line), ...]
        """
        result = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            if not line.strip():
                i += 1
                continue

            preprocessed = self._preprocessor.preprocess(line)

            # Header-only line: matched a header pattern but body is empty
            if (preprocessed.header_format != "unknown"
                    and not preprocessed.body
                    and i + 1 < len(raw_lines)
                    and raw_lines[i + 1].strip()):
                merged = line + " " + raw_lines[i + 1].strip()
                result.append((i + 1, merged))
                i += 2
            else:
                result.append((i + 1, line))
                i += 1

        return result

    def parse_file(self, file_path: str) -> ParseResult:
        """解析日志文件"""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return self.parse_content(content, source_file=file_path)

    def get_cache(self) -> AdaptiveParsingCache:
        return self._cache

    @staticmethod
    def _extract_parameters(
        log_tokens: List[str], template: Optional[LogTemplate]
    ) -> List[str]:
        """从原始日志文本和模板中提取参数（正则匹配方式）"""
        if template is None or not template.template_str:
            return []

        try:
            raw_text = " ".join(log_tokens)
            # Convert template to regex: escape literal parts, replace <*> with capture group
            parts = template.template_str.split("<*>")
            regex_parts = [re.escape(p) for p in parts]
            pattern = "(.*?)".join(regex_parts)
            # Allow flexible whitespace matching
            pattern = re.sub(r'\\ ', r'\\s+', pattern)

            m = re.fullmatch(pattern, raw_text, re.DOTALL)
            if m:
                return [g for g in m.groups() if g]

            # fallback: non-greedy from start
            m = re.match(pattern, raw_text, re.DOTALL)
            if m:
                return [g for g in m.groups() if g]
        except re.error:
            pass

        return []
