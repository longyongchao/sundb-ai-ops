"""LILAC 预处理器：日志头剥离、正则掩码、Token化"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

PLACEHOLDER = "<*>"

# ============================================================
# 日志头格式定义（按优先级排列）
# ============================================================

HEADER_PATTERNS = [
    # SunDB system.trc: [2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] [INFORMATION]
    (
        "sundb_system",
        re.compile(
            r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)'
            r'\s+INSTANCE\((\w+)\)'
            r'\s+THREAD\((\d+),(\d+)\)\]'
            r'\s+\[(\w+)\]'
        ),
        ["timestamp", "instance", "thread_pid", "thread_tid", "level"],
    ),
    # SunDB simple (listener/CDC/gmon): [2024-02-05 16:18:28.406162 THREAD(1347044,281465167431120)]
    (
        "sundb_simple",
        re.compile(
            r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)'
            r'\s+THREAD\((\d+),(\d+)\)\]'
        ),
        ["timestamp", "thread_pid", "thread_tid"],
    ),
    # Syslog: Mar 15 10:23:01 hostname prog[pid]: message
    (
        "syslog",
        re.compile(
            r'^([A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2})'
            r'\s+(\S+)\s+(\S+?)(?:\[(\d+)\])?:\s*'
        ),
        ["timestamp", "hostname", "program", "pid"],
    ),
    # ISO8601 with level: 2024-03-15 10:23:01 INFO message
    (
        "iso_level",
        re.compile(
            r'^(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?)'
            r'\s+(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL|TRACE)\s+'
        ),
        ["timestamp", "level"],
    ),
    # ISO8601 timestamp only: 2024-03-15 10:23:01.123 message
    (
        "iso_only",
        re.compile(
            r'^(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+'
        ),
        ["timestamp"],
    ),
]

# ============================================================
# 正则掩码规则（按顺序应用）
# ============================================================

MASK_PATTERNS = [
    # UUID
    (re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'), PLACEHOLDER),
    # IPv4
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), PLACEHOLDER),
    # Hex values (0x...)
    (re.compile(r'\b0x[0-9a-fA-F]+\b'), PLACEHOLDER),
    # File paths
    (re.compile(r'(?:/[\w.\-]+){2,}'), PLACEHOLDER),
    # Long numbers (4+ digits)
    (re.compile(r'\b\d{4,}\b'), PLACEHOLDER),
    # Numeric values in key=value pairs (e.g. exec_time_seconds=32, num_lora=0)
    # This catches small numbers that the 4+-digit rule misses, preventing the
    # static shortcut from firing when the log body actually contains variables.
    (re.compile(r'(?<==)\d+(?:\.\d+)?(?=[\s,\]\)\};]|$)', re.MULTILINE), PLACEHOLDER),
]


@dataclass
class PreprocessedLine:
    """预处理后的日志行"""
    raw_text: str
    header_fields: Dict[str, str] = field(default_factory=dict)
    header_format: str = ""
    body: str = ""
    masked_body: str = ""
    tokens: List[str] = field(default_factory=list)
    token_count: int = 0
    first_token: str = ""


class LogPreprocessor:
    """日志预处理器：头部剥离 → 正则掩码 → Token化"""

    def __init__(
        self,
        header_patterns: Optional[List] = None,
        mask_patterns: Optional[List] = None,
    ):
        self._header_patterns = header_patterns or HEADER_PATTERNS
        self._mask_patterns = mask_patterns or MASK_PATTERNS

    def preprocess(self, raw_line: str) -> PreprocessedLine:
        raw_line = raw_line.rstrip("\n\r")
        if not raw_line.strip():
            return PreprocessedLine(raw_text=raw_line)

        header_fields, header_format, body = self._strip_header(raw_line)
        masked_body = self._apply_masks(body)
        tokens = self._tokenize(masked_body)

        return PreprocessedLine(
            raw_text=raw_line,
            header_fields=header_fields,
            header_format=header_format,
            body=body,
            masked_body=masked_body,
            tokens=tokens,
            token_count=len(tokens),
            first_token=tokens[0] if tokens else "",
        )

    def _strip_header(self, line: str) -> Tuple[Dict[str, str], str, str]:
        for fmt_name, pattern, field_names in self._header_patterns:
            m = pattern.match(line)
            if m:
                fields = {}
                for i, name in enumerate(field_names):
                    val = m.group(i + 1)
                    if val is not None:
                        fields[name] = val
                body = line[m.end():].strip()
                return fields, fmt_name, body
        return {}, "unknown", line

    def _apply_masks(self, text: str) -> str:
        for pattern, replacement in self._mask_patterns:
            text = pattern.sub(replacement, text)
        return text

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        if not text:
            return []
        return text.split()
