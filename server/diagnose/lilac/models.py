"""LILAC 数据模型"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from server.diagnose.sundb_trc_parser import SunDBLogEntry


@dataclass
class LogTemplate:
    """日志模板"""
    template_id: str
    template_str: str
    tokens: List[str]
    token_count: int
    first_token: str
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_hit_at: float = field(default_factory=time.time)
    source: Literal["llm", "drain3", "seed", "manual", "static"] = "llm"

    @staticmethod
    def generate_id(template_str: str) -> str:
        return hashlib.sha256(template_str.encode()).hexdigest()[:16]

    @classmethod
    def from_template_str(
        cls, template_str: str, source: str = "llm"
    ) -> "LogTemplate":
        tokens = template_str.split()
        return cls(
            template_id=cls.generate_id(template_str),
            template_str=template_str,
            tokens=tokens,
            token_count=len(tokens),
            first_token=tokens[0] if tokens else "",
            source=source,
        )


@dataclass
class GenericLogEntry:
    """通用日志条目"""
    timestamp: str = ""
    level: str = ""
    message: str = ""
    template: Optional[LogTemplate] = None
    parameters: List[str] = field(default_factory=list)
    source_file: str = ""
    line_number: int = 0
    raw_text: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class ParseResult:
    """批量解析结果"""
    entries: List[GenericLogEntry] = field(default_factory=list)
    cache_hits: int = 0
    llm_calls: int = 0
    drain3_fallbacks: int = 0
    static_shortcuts: int = 0
    batch_dedup: int = 0
    parse_time_ms: float = 0.0


def to_sundb_log_entry(entry: GenericLogEntry) -> SunDBLogEntry:
    """GenericLogEntry → SunDBLogEntry 转换（兼容下游 FaultEvent/AEU 管线）"""
    return SunDBLogEntry(
        timestamp=entry.timestamp,
        instance=entry.metadata.get("instance", ""),
        thread_pid=int(entry.metadata.get("thread_pid", "0") or "0"),
        thread_tid=int(entry.metadata.get("thread_tid", "0") or "0"),
        level=entry.level,
        message=entry.message,
        category=entry.metadata.get("category", ""),
        error_code=entry.metadata.get("error_code", ""),
        error_message=entry.metadata.get("error_message", ""),
        source_file=entry.source_file,
        raw_text=entry.raw_text,
    )
