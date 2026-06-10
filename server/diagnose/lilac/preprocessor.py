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
    # SunDB system.trc
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
    # SunDB simple (listener/CDC/gmon)
    (
        "sundb_simple",
        re.compile(
            r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)'
            r'\s+THREAD\((\d+),(\d+)\)\]'
        ),
        ["timestamp", "thread_pid", "thread_tid"],
    ),
    # OpenStack: 2017-05-16 00:00:00.008 25746 INFO nova.component [req-...] message
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
    # ISO8601 with level
    (
        "iso_level",
        re.compile(
            rf'^(\d{{4}}-\d{{2}}-\d{{2}}[\sT]\d{{2}}:\d{{2}}:\d{{2}}(?:[\.,]\d+)?)'
            rf'\s+({LEVEL_WORD})\s+'
        ),
        ["timestamp", "level"],
    ),
    # ISO8601 timestamp only
    (
        "iso_only",
        re.compile(
            r'^(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:[\.,]\d+)?)\s+'
        ),
        ["timestamp"],
    ),
]

TIMESTAMP_PATTERNS = [
    ("iso_timestamp", re.compile(r'\b\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:[\.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b')),
    ("compact_hdfs_timestamp", re.compile(r'\b\d{6}\s+\d{6}\b')),
    ("syslog_timestamp", re.compile(r'\b[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\b')),
    ("epoch_timestamp", re.compile(r'\b\d{10}(?:\.\d+)?\b')),
]

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
    # HTTP request line
    (re.compile(r'"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+[^"]+\s+HTTP/\d(?:\.\d+)?"'), r'"\1 <*>"'),
    # Key-value numeric patterns
    (re.compile(r'\b(status|len|size|time|duration|elapsed|latency|cost|port|id|attemptId|keyId|startIndex|maxEvents)\s*([:=])\s*-?\d+(?:\.\d+)?', re.IGNORECASE), r'\1\2 <*>'),
    # Context-specific short numbers
    (re.compile(r'\b(PacketResponder)\s+\d+\b'), r'\1 <*>'),
    # Hex values (0x...)
    (re.compile(r'\b0x[0-9a-fA-F]+\b'), PLACEHOLDER),
    # Floating point values
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
                fields = self._normalize_header_fields(fields, fmt_name)
                body = self._clean_body(line[m.end():])
                return fields, fmt_name, body
        return self._infer_header(line)

    def _infer_header(self, line: str) -> Tuple[Dict[str, str], str, str]:
        """Field-level fallback for unseen log formats."""
        fields: Dict[str, str] = {}
        ts_match, ts_kind = self._find_timestamp(line)
        cursor = 0

        if ts_match:
            fields["timestamp"] = ts_match.group(0)
            cursor = ts_match.end()

        level_match = self._find_level(line, cursor, bool(ts_match))
        if level_match:
            fields["level"] = level_match.group(1).upper()
            cursor = level_match.end()

        if not fields:
            return {}, "unknown", line

        body = self._clean_body(line[cursor:])
        if not body:
            body = line

        fmt_name = f"generic_{ts_kind}" if ts_kind else "generic_header"
        fields = self._normalize_header_fields(fields, fmt_name)
        return fields, fmt_name, body

    def _find_timestamp(self, line: str):
        best = None
        best_kind = ""
        for kind, pattern in TIMESTAMP_PATTERNS:
            m = pattern.search(line[:160])
            if m and (best is None or m.start() < best.start()):
                best = m
                best_kind = kind
        return best, best_kind

    def _find_level(self, line: str, cursor: int, has_timestamp: bool):
        """Find log level near the beginning of the line after cursor."""
        search_region = line[cursor:cursor + 80]
        m = LEVEL_TOKEN_RE.search(search_region)
        if m and m.start() < 40:
            # Adjust match positions to full line
            class _Match:
                def __init__(self, val, s, e):
                    self._val = val
                    self._s = s
                    self._e = e
                def group(self, i=0):
                    return self._val if i <= 1 else None
                def start(self):
                    return self._s
                def end(self):
                    return self._e
            return _Match(m.group(1), cursor + m.start(), cursor + m.end())
        return None

    @staticmethod
    def _normalize_header_fields(fields: Dict[str, str], fmt_name: str) -> Dict[str, str]:
        """Normalize extracted header fields.

        Note: SunDB formats preserve original level names (e.g. INFORMATION)
        since they are meaningful in that context.
        """
        if "level" in fields and not fmt_name.startswith("sundb"):
            fields["level"] = fields["level"].upper()
            if fields["level"] == "INFORMATION":
                fields["level"] = "INFO"
        return fields

    @staticmethod
    def _clean_body(text: str) -> str:
        """Strip leading/trailing whitespace and common separators from body."""
        text = text.strip()
        if text.startswith(": "):
            text = text[2:]
        elif text.startswith(":"):
            text = text[1:].lstrip()
        return text

    def _apply_masks(self, text: str) -> str:
        for pattern, replacement in self._mask_patterns:
            text = pattern.sub(replacement, text)
        return text

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        if not text:
            return []
        return text.split()
