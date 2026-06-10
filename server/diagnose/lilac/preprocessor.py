"""LILAC 预处理器：日志头剥离、正则掩码、Token化"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

PLACEHOLDER = "<*>"
LEVEL_WORD = r"DEBUG|INFO|INFORMATION|NOTICE|WARN(?:ING)?|ERROR|ERR|FATAL|CRITICAL|TRACE|SEVERE"
LEVEL_TOKEN_RE = re.compile(rf'(?<![A-Za-z0-9_])({LEVEL_WORD})(?![A-Za-z0-9_])')

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
    # OpenStack: nova-api.log... 2017-05-16 00:00:00.008 25746 INFO nova.component [req-...] message
    (
        "openstack",
        re.compile(
            rf'^(\S+)\s+'
            rf'(\d{{4}}-\d{{2}}-\d{{2}}\s+\d{{2}}:\d{{2}}:\d{{2}}(?:[\.,]\d+)?)\s+'
            rf'(\d+)\s+({LEVEL_WORD})\s+(\S+)'
            rf'(?:\s+(\[[^\]]+\]))?\s*'
        ),
        ["logrecord", "timestamp", "pid", "level", "component", "context"],
    ),
    # Hadoop/log4j: 2015-10-18 18:01:47,978 INFO [main] org.xxx.Class: message
    (
        "log4j_component",
        re.compile(
            rf'^(\d{{4}}-\d{{2}}-\d{{2}}\s+\d{{2}}:\d{{2}}:\d{{2}}(?:[\.,]\d+)?)\s+'
            rf'({LEVEL_WORD})\s+'
            rf'(?:\[([^\]]+)\]\s+)?'
            rf'(\S+?):\s*'
        ),
        ["timestamp", "level", "process", "component"],
    ),
    # HDFS legacy: 081109 203615 148 INFO dfs.DataNode$PacketResponder: message
    (
        "hdfs_legacy",
        re.compile(
            rf'^(\d{{6}})\s+(\d{{6}})\s+(\d+)\s+({LEVEL_WORD})\s+(\S+?):\s*'
        ),
        ["date", "time", "pid", "level", "component"],
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
            rf'^(\d{{4}}-\d{{2}}-\d{{2}}[\sT]\d{{2}}:\d{{2}}:\d{{2}}(?:[\.,]\d+)?)'
            rf'\s+({LEVEL_WORD})\s+'
        ),
        ["timestamp", "level"],
    ),
    # ISO8601 timestamp only: 2024-03-15 10:23:01.123 message
    (
        "iso_only",
        re.compile(
            r'^(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:[\.,]\d+)?)\s+'
        ),
        ["timestamp"],
    ),
]

TIMESTAMP_PATTERNS = [
    (
        "iso_timestamp",
        re.compile(r'\b\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:[\.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b'),
    ),
    (
        "compact_hdfs_timestamp",
        re.compile(r'\b\d{6}\s+\d{6}\b'),
    ),
    (
        "syslog_timestamp",
        re.compile(r'\b[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\b'),
    ),
    (
        "epoch_timestamp",
        re.compile(r'\b\d{10}(?:\.\d+)?\b'),
    ),
]


@dataclass
class _HeaderMatch:
    value: str
    start_pos: int
    end_pos: int

    def group(self, idx: int = 0) -> str:
        return self.value

    def start(self) -> int:
        return self.start_pos

    def end(self) -> int:
        return self.end_pos

# ============================================================
# 正则掩码规则（按顺序应用）
# ============================================================

MASK_PATTERNS = [
    # UUID
    (re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'), PLACEHOLDER),
    # IPv4
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), PLACEHOLDER),
    # Common Hadoop/HDFS runtime identifiers
    (re.compile(r'\bblk_-?\d+\b'), PLACEHOLDER),
    (re.compile(r'\bappattempt_\d+_\d+_\d+\b'), PLACEHOLDER),
    (re.compile(r'\bapplication_\d+_\d+\b'), PLACEHOLDER),
    (re.compile(r'\bcontainer_\d+_\d+_\d+_\d+\b'), PLACEHOLDER),
    (re.compile(r'\battempt_\d+(?:_\d+)*[A-Za-z0-9_]*\b'), PLACEHOLDER),
    # HTTP request line inside quotes, keep method as static structure.
    (re.compile(r'"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+[^"]+\s+HTTP/\d(?:\.\d+)?"'), r'"\1 <*>"'),
    # Numeric values in key-value positions are runtime variables.
    (re.compile(r'\b(status|len|size|time|duration|elapsed|latency|cost|port|id|attemptId|keyId|startIndex|maxEvents)\s*([:=])\s*-?\d+(?:\.\d+)?', re.IGNORECASE), r'\1\2 <*>'),
    # Context-specific short numbers.
    (re.compile(r'\b(PacketResponder)\s+\d+\b'), r'\1 <*>'),
    # Hex values (0x...)
    (re.compile(r'\b0x[0-9a-fA-F]+\b'), PLACEHOLDER),
    # Floating point values must be masked before generic long-number masking.
    (re.compile(r'(?<![\w.])-?\d+\.\d+(?![\w.])'), PLACEHOLDER),
    # File paths
    (re.compile(r'(?:/[\w.\-]+){2,}'), PLACEHOLDER),
    # Signed long numbers
    (re.compile(r'(?<![\w])-?\d{4,}\b'), PLACEHOLDER),
    # Long numbers (4+ digits)
    (re.compile(r'\b\d{4,}\b'), PLACEHOLDER),
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
                fields = self._normalize_header_fields(fields, fmt_name, "1.0")
                body = self._clean_body(line[m.end():])
                return fields, fmt_name, body
        return self._infer_header(line)

    def _infer_header(self, line: str) -> Tuple[Dict[str, str], str, str]:
        """Field-level fallback for unseen log formats.

        It intentionally extracts only high-confidence header fields near the
        beginning of the line, so arbitrary message words are not mistaken for
        log levels.
        """
        fields: Dict[str, str] = {}
        ts_match, ts_kind = self._find_timestamp(line)
        cursor = 0

        if ts_match:
            fields["timestamp"] = ts_match.group(0)
            cursor = ts_match.end()
            prefix = line[:ts_match.start()].strip()
            if prefix and len(prefix.split()) == 1:
                fields["logrecord"] = prefix

        level_match = self._find_level(line, cursor, bool(ts_match))
        if level_match:
            fields["level"] = level_match.group(1).upper()
            self._infer_pre_level_fields(line[cursor:level_match.start()], fields)
            cursor = level_match.end()

        if not fields:
            return {}, "unknown", line

        body = self._infer_post_level_fields(line[cursor:], fields)
        if not body and cursor:
            body = self._clean_body(line[cursor:])
        if not body:
            body = line

        fmt_name = "generic_header"
        if ts_kind:
            fmt_name = f"generic_{ts_kind}"
        fields = self._normalize_header_fields(
            fields,
            fmt_name,
            "0.85" if fields.get("timestamp") and fields.get("level") else "0.65",
        )
        return fields, fmt_name, body

    def _find_timestamp(self, line: str):
        best = None
        best_kind = ""
        for kind, pattern in TIMESTAMP_PATTERNS:
            m = pattern.search(line[:160])
            if not m:
                continue
            prefix_tokens = line[:m.start()].strip().split()
            if m.start() > 80 or len(prefix_tokens) > 1:
                continue
            if best is None or m.start() < best.start():
                best = m
                best_kind = kind
        return best, best_kind

    @staticmethod
    def _find_level(line: str, start: int, has_timestamp: bool):
        window_start = start if has_timestamp else 0
        window = line[window_start: window_start + 120]
        for m in LEVEL_TOKEN_RE.finditer(window):
            absolute_start = window_start + m.start()
            if not has_timestamp and len(line[:absolute_start].strip().split()) > 3:
                continue
            return _HeaderMatch(m.group(1), absolute_start, window_start + m.end())
        return None

    @staticmethod
    def _infer_pre_level_fields(text: str, fields: Dict[str, str]) -> None:
        tokens = text.strip().split()
        if not tokens:
            return
        if tokens[-1].isdigit() and "pid" not in fields:
            fields["pid"] = tokens[-1]

    def _infer_post_level_fields(self, text: str, fields: Dict[str, str]) -> str:
        tail = text.lstrip()
        if not tail:
            return ""

        bracket = re.match(r'^\[([^\]]+)\]\s*', tail)
        if bracket:
            value = bracket.group(1)
            key = "context" if value.startswith("req-") or " " in value else "process"
            fields.setdefault(key, value)
            tail = tail[bracket.end():].lstrip()

        pid = re.match(r'^(\d+)\s+', tail)
        if pid and "pid" not in fields:
            fields["pid"] = pid.group(1)
            tail = tail[pid.end():].lstrip()

        component = re.match(r'^([A-Za-z0-9_.$/@-]+):\s*', tail)
        if component:
            fields.setdefault("component", component.group(1))
            return self._clean_body(tail[component.end():])

        token = re.match(r'^([A-Za-z0-9_.$/@-]+)\s+', tail)
        if token:
            candidate = token.group(1)
            if any(ch in candidate for ch in (".", "$", "/", "@")):
                fields.setdefault("component", candidate)
                return self._clean_body(tail[token.end():])

        return self._clean_body(tail)

    @staticmethod
    def _normalize_header_fields(
        fields: Dict[str, str],
        fmt_name: str,
        confidence: str,
    ) -> Dict[str, str]:
        normalized = {k: v for k, v in fields.items() if v not in (None, "")}
        if "timestamp" not in normalized and normalized.get("date") and normalized.get("time"):
            normalized["timestamp"] = f"{normalized['date']} {normalized['time']}"
        if "level" in normalized:
            normalized["level"] = normalized["level"].upper()
        if "context" in normalized:
            normalized["context"] = normalized["context"].strip("[]")
        normalized.setdefault("header_parse_source", fmt_name)
        normalized.setdefault("header_parse_confidence", confidence)
        return normalized

    @staticmethod
    def _clean_body(text: str) -> str:
        return text.lstrip(" \t:-").strip()

    def _apply_masks(self, text: str) -> str:
        for pattern, replacement in self._mask_patterns:
            text = pattern.sub(replacement, text)
        return text

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        if not text:
            return []
        return text.split()
