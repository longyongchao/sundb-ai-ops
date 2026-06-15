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

DYNAMIC_BODY_PATTERNS = [
    re.compile(r'\bblk_-?\d+\b'),
    re.compile(r'\b(?:appattempt|application|container|attempt)_\d+(?:_\d+)+\b'),
    re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'),
    re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b'),
    re.compile(r'(?<![\w.])-?\d+\.\d+(?![\w.])'),
    re.compile(r'(?<![\w])-?\d{4,}\b'),
    re.compile(r'\b(?:status|len|size|time|duration|elapsed|latency|cost|id|attemptId|keyId)\s*[:=]\s*-?\d+', re.IGNORECASE),
    re.compile(r'"(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+[^"]+\s+HTTP/\d(?:\.\d+)?"'),
]


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
        """解析模板核心逻辑：缓存 → 静态快捷 → LLM → Drain3"""
        if not preprocessed.tokens:
            return None, ""

        # (1) 缓存查找
        template = self._cache.lookup(preprocessed.tokens)
        if template:
            return template, "cache"

        # (2) 静态行快捷路径：预处理后无任何变量，直接作为模板
        template_src = preprocessed.template_body or preprocessed.body
        if (preprocessed.masked_body == template_src
                and "<*>" not in preprocessed.masked_body
                and not self._looks_dynamic_body(template_src)):
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
                template = self._normalize_template(template)
                self._cache.insert(
                    template, preprocessed.masked_body,
                    lookup_tokens=preprocessed.tokens,
                )
                return template, "llm"

        # (4) Drain3 兜底 / 指定 Drain3 模式
        if parse_mode in ("auto", "drain3") and self._drain3 and self._drain3.available:
            template = self._drain3.parse(preprocessed.masked_body)
            if template:
                template = self._normalize_template(template)
                self._cache.insert(
                    template, preprocessed.masked_body,
                    lookup_tokens=preprocessed.tokens,
                )
                return template, "drain3"

        return None, ""

    @staticmethod
    def _looks_dynamic_body(body: str) -> bool:
        """Return True when an unmasked body still contains obvious runtime values."""
        return any(pattern.search(body or "") for pattern in DYNAMIC_BODY_PATTERNS)

    @staticmethod
    def _normalize_template(template: LogTemplate) -> LogTemplate:
        """Repair common partial-variable templates produced by LLM/Drain3."""
        template_str = template.template_str
        replacements = [
            (r'\bblk_-?\d+\b', '<*>'),
            (r'\bblk_<\*>\b', '<*>'),
            (r'\bappattempt_\d+_\d+_\d+\b', '<*>'),
            (r'\bapplication_\d+_\d+\b', '<*>'),
            (r'\bcontainer_\d+_\d+_\d+_\d+\b', '<*>'),
            (r'\battempt_\d+(?:_\d+)*[A-Za-z0-9_]*\b', '<*>'),
            (r'"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+<\*>\s+HTTP/\d(?:\.\d+)?"', r'"\1 <*>"'),
            (r'\b(status|len|size|time|duration|elapsed|latency|cost|port|id|attemptId|keyId|startIndex|maxEvents)\s*([:=])\s*-?\d+(?:\.\d+)?', r'\1\2 <*>'),
            (r'(?<![\w.])-?\d+\.\d+(?![\w.])', '<*>'),
            (r'(?<![\w])-?\d{4,}\b', '<*>'),
            (r'\b(PacketResponder)\s+\d+\b', r'\1 <*>'),
        ]
        for pattern, replacement in replacements:
            template_str = re.sub(pattern, replacement, template_str, flags=re.IGNORECASE)
        template_str = re.sub(r'(?:<\*>\s*){2,}', '<*> ', template_str)
        template_str = re.sub(r'\s+', ' ', template_str).strip()
        if template_str == template.template_str:
            return template
        return LogTemplate.from_template_str(template_str, source=template.source)

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
        pass2_cache = 0
        pass2_llm = 0
        pass2_static = 0
        pass2_drain3 = 0

        for key, rep_idx in groups.items():
            _, _, preprocessed = preprocessed_lines[rep_idx]
            template, source_str = self._resolve_template(
                preprocessed, parse_mode=parse_mode
            )
            resolved[key] = (template, source_str)

            if source_str == "cache":
                pass2_cache += 1
            elif source_str == "llm":
                pass2_llm += 1
            elif source_str == "static":
                pass2_static += 1
            elif source_str == "drain3":
                pass2_drain3 += 1

        # === Pass 3: 按原始顺序构建结果 ===
        entries: List[GenericLogEntry] = []
        cache_hits = 0
        llm_calls = 0
        drain3_fallbacks = 0
        static_shortcuts = 0

        for line_num, line, preprocessed in preprocessed_lines:
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
            template, source_str = resolved.get(key, (None, ""))

            raw_body_tokens = preprocessed.body.split() if preprocessed.body else preprocessed.raw_text.split()
            parameters = self._extract_parameters(raw_body_tokens, template)

            metadata = dict(preprocessed.header_fields)
            if source_str:
                metadata["_parse_source"] = source_str

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

            if source_str == "cache":
                cache_hits += 1
            elif source_str == "llm":
                llm_calls += 1
            elif source_str == "drain3":
                drain3_fallbacks += 1
            elif source_str == "static":
                static_shortcuts += 1

        elapsed_ms = (time.time() - start) * 1000.0

        return ParseResult(
            entries=entries,
            cache_hits=pass2_cache,
            llm_calls=pass2_llm,
            drain3_fallbacks=pass2_drain3,
            static_shortcuts=pass2_static,
            batch_dedup=total - unique_groups,
            parse_time_ms=elapsed_ms,
        )

    def _assemble_multiline(self, raw_lines: List[str]) -> List[tuple]:
        """组装多行日志"""
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
        """从日志 tokens 和模板 tokens 中提取参数"""
        if template is None or not template.tokens:
            return []
        params = []
        for lt, tt in zip(log_tokens, template.tokens):
            if tt == "<*>" and lt != "<*>":
                params.append(lt)
        return params
