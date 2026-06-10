"""LILAC 主编排器：统一日志解析入口"""

import logging
import os
import re
import time
from typing import List, Literal, Optional, Tuple

from server.diagnose.lilac.cache import AdaptiveParsingCache
from server.diagnose.lilac.config import LilacConfig
from server.diagnose.lilac.demonstration_pool import DemonstrationPool
from server.diagnose.lilac.drain3_fallback import Drain3Fallback
from server.diagnose.lilac.llm_template_extractor import LLMTemplateExtractor
from server.diagnose.lilac.models import GenericLogEntry, LogTemplate, ParseResult
from server.diagnose.lilac.preprocessor import LogPreprocessor, PreprocessedLine

logger = logging.getLogger(__name__)

ParseMode = Literal["auto", "llm", "drain3"]


class LilacParser:
    """LILAC 统一日志解析器

    流程：预处理 → 静态快捷 → 缓存查找 → LLM 提取 → Drain3 兜底
    """

    def __init__(self, config: Optional[LilacConfig] = None):
        self._config = config or LilacConfig()

        self._preprocessor = LogPreprocessor()
        self._cache = AdaptiveParsingCache(
            db_path=self._config.cache_db_path,
            similarity_threshold=self._config.cache_similarity_threshold,
            merge_enabled=self._config.template_merge_enabled,
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

    def _resolve_template(
        self, preprocessed: PreprocessedLine, parse_mode: ParseMode = "auto"
    ) -> Tuple[Optional[LogTemplate], str]:
        """解析模板核心逻辑：缓存 → 静态快捷 → LLM → Drain3

        返回 (template, source_str)
        """
        if not preprocessed.tokens:
            return None, ""

        # (1) 缓存查找
        template = self._cache.lookup(preprocessed.tokens)
        if template:
            return template, "cache"

        # (2) 静态行快捷路径：预处理后无任何变量，直接作为模板
        template_src = preprocessed.template_body or preprocessed.body
        if (preprocessed.masked_body == template_src
                and "<*>" not in preprocessed.masked_body):
            template = LogTemplate.from_template_str(template_src, source="static")
            self._cache.insert(template, preprocessed.masked_body)
            return template, "static"

        # (3) LLM 提取
        if parse_mode in ("auto", "llm") and self._llm_extractor:
            demos = self._demo_pool.sample(
                preprocessed.tokens, k=self._config.demo_sample_k
            )
            template = self._llm_extractor.extract(
                preprocessed.masked_body, demos
            )
            if template:
                self._cache.insert(
                    template, preprocessed.masked_body,
                    lookup_tokens=preprocessed.tokens,
                )
                return template, "llm"

        # (4) Drain3 兜底 / 指定 Drain3 模式
        if parse_mode in ("auto", "drain3") and self._drain3 and self._drain3.available:
            template = self._drain3.parse(preprocessed.masked_body)
            if template:
                self._cache.insert(
                    template, preprocessed.masked_body,
                    lookup_tokens=preprocessed.tokens,
                )
                return template, "drain3"

        return None, ""

    def parse_line(
        self,
        raw_line: str,
        source_file: str = "",
        line_number: int = 0,
        parse_mode: ParseMode = "auto",
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

        template, source = self._resolve_template(preprocessed, parse_mode=parse_mode)

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

    def parse_content(
        self,
        content: str,
        source_file: str = "",
        parse_mode: ParseMode = "auto",
    ) -> ParseResult:
        """解析日志文本内容（批量去重优化）"""
        start = time.time()
        raw_lines = content.splitlines()
        assembled = self._assemble_multiline(raw_lines)
        total = len(assembled)

        logger.info(
            f"[LILAC] 开始解析: {total} 条日志 "
            f"(source={source_file or 'text'}, mode={parse_mode})"
        )

        # === Pass 1: 预处理所有行 + 按 token 签名分组 ===
        preprocessed_lines: List[Tuple[int, str, PreprocessedLine]] = []
        groups = {}  # tuple(tokens) -> 组内第一个索引

        for line_num, line in assembled:
            preprocessed = self._preprocessor.preprocess(line)
            preprocessed_lines.append((line_num, line, preprocessed))

            if preprocessed.tokens:
                key = tuple(preprocessed.tokens)
                if key not in groups:
                    groups[key] = len(preprocessed_lines) - 1

        unique_groups = len(groups)
        logger.info(f"[LILAC] 批量去重: {total} 行 → {unique_groups} 个唯一模式")

        # === Pass 2: 每组解析一个代表 ===
        resolved = {}  # tuple(tokens) -> (template, source_str)

        resolved_count = 0
        pass2_cache = 0
        pass2_llm = 0
        pass2_static = 0
        pass2_drain3 = 0
        pass2_none = 0

        for key, rep_idx in groups.items():
            _, _, preprocessed = preprocessed_lines[rep_idx]
            template, source_str = self._resolve_template(
                preprocessed, parse_mode=parse_mode
            )
            resolved[key] = (template, source_str)
            resolved_count += 1

            if source_str == "cache":
                pass2_cache += 1
            elif source_str == "llm":
                pass2_llm += 1
            elif source_str == "static":
                pass2_static += 1
            elif source_str == "drain3":
                pass2_drain3 += 1
            else:
                pass2_none += 1

            if source_str == "llm":
                logger.info(
                    f"[LILAC] [{resolved_count}/{unique_groups}] LLM调用 | "
                    f"唯一模式 #{resolved_count}"
                )

            if resolved_count % 500 == 0:
                logger.info(
                    f"[LILAC] 进度 [{resolved_count}/{unique_groups}] | "
                    f"缓存:{pass2_cache} 静态:{pass2_static} LLM:{pass2_llm} "
                    f"Drain3:{pass2_drain3} 未匹配:{pass2_none}"
                )

        # === Pass 3: 按原始顺序构建结果 ===
        entries: List[GenericLogEntry] = []
        cache_hits = 0
        llm_calls = 0
        drain3_fallbacks = 0
        static_shortcuts = 0
        batch_dedup = 0

        for idx, (line_num, line, preprocessed) in enumerate(preprocessed_lines):
            if not preprocessed.tokens:
                entries.append(GenericLogEntry(
                    raw_text=line,
                    message=preprocessed.body or line,
                    source_file=source_file,
                    line_number=line_num,
                    metadata=preprocessed.header_fields,
                    timestamp=preprocessed.header_fields.get("timestamp", ""),
                    level=preprocessed.header_fields.get("level", ""),
                ))
                continue

            key = tuple(preprocessed.tokens)
            template, source = resolved.get(key, (None, ""))

            # 统计
            rep_idx = groups.get(key)
            is_representative = (rep_idx == idx)
            if is_representative:
                if source == "cache":
                    cache_hits += 1
                elif source == "llm":
                    llm_calls += 1
                elif source == "drain3":
                    drain3_fallbacks += 1
                elif source == "static":
                    static_shortcuts += 1
            else:
                batch_dedup += 1

            raw_body_tokens = preprocessed.body.split() if preprocessed.body else line.split()
            parameters = self._extract_parameters(raw_body_tokens, template)

            metadata = dict(preprocessed.header_fields)
            if source:
                metadata["_parse_source"] = source

            entries.append(GenericLogEntry(
                timestamp=preprocessed.header_fields.get("timestamp", ""),
                level=preprocessed.header_fields.get("level", ""),
                message=preprocessed.body,
                template=template,
                parameters=parameters,
                source_file=source_file,
                line_number=line_num,
                raw_text=line,
                metadata=metadata,
            ))

        elapsed_ms = (time.time() - start) * 1000.0
        logger.info(
            f"[LILAC] 解析完成: {total} 条 | "
            f"缓存: {cache_hits}, LLM: {llm_calls}, 静态: {static_shortcuts}, "
            f"去重: {batch_dedup}, Drain3: {drain3_fallbacks} | "
            f"总耗时: {elapsed_ms:.0f}ms"
        )

        return ParseResult(
            entries=entries,
            cache_hits=cache_hits,
            llm_calls=llm_calls,
            drain3_fallbacks=drain3_fallbacks,
            static_shortcuts=static_shortcuts,
            batch_dedup=batch_dedup,
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

            if (preprocessed.header_format != "unknown"
                    and not preprocessed.body
                    and preprocessed.header_format != "json_log"
                    and i + 1 < len(raw_lines)
                    and raw_lines[i + 1].strip()):
                merged = line + " " + raw_lines[i + 1].strip()
                result.append((i + 1, merged))
                i += 2
            else:
                result.append((i + 1, line))
                i += 1

        return result

    def parse_file(self, file_path: str, parse_mode: ParseMode = "auto") -> ParseResult:
        """解析日志文件"""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return self.parse_content(content, source_file=file_path, parse_mode=parse_mode)

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
            parts = template.template_str.split("<*>")
            regex_parts = [re.escape(p) for p in parts]
            pattern = "(.*?)".join(regex_parts)
            pattern = re.sub(r'\\ ', r'\\s+', pattern)

            m = re.fullmatch(pattern, raw_text, re.DOTALL)
            if m:
                return [g for g in m.groups() if g]

            m = re.match(pattern, raw_text, re.DOTALL)
            if m:
                return [g for g in m.groups() if g]
        except re.error:
            pass

        return []
