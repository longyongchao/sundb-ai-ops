"""LILAC 自适应解析缓存（SQLite-backed）"""

import json
import os
import sqlite3
import threading
import time
from typing import Dict, List, Optional

from server.diagnose.lilac.models import LogTemplate
from server.diagnose.lilac.similarity import token_similarity

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS templates (
    template_id TEXT PRIMARY KEY,
    template_str TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    first_token TEXT NOT NULL,
    tokens_json TEXT NOT NULL,
    hit_count INTEGER DEFAULT 0,
    created_at REAL,
    last_hit_at REAL,
    source TEXT DEFAULT 'llm'
);

CREATE INDEX IF NOT EXISTS idx_lookup ON templates(token_count, first_token);

CREATE TABLE IF NOT EXISTS demonstrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_log TEXT NOT NULL,
    template_id TEXT NOT NULL REFERENCES templates(template_id),
    created_at REAL,
    UNIQUE(raw_log)
);
"""


class AdaptiveParsingCache:
    """SQLite-backed 自适应前缀树缓存

    索引结构：token_count → first_token → 候选模板列表
    匹配：逐位置比较，<*> 匹配任何 token，相似度 ≥ 阈值即命中
    """

    def __init__(self, db_path: str, similarity_threshold: float = 0.85):
        self._db_path = db_path
        self._threshold = similarity_threshold
        self._lock = threading.Lock()

        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()

        self._cache: Dict[int, Dict[str, List[LogTemplate]]] = {}
        self._load_into_memory()

    def _load_into_memory(self) -> None:
        cursor = self._conn.execute(
            "SELECT template_id, template_str, token_count, first_token, "
            "tokens_json, hit_count, created_at, last_hit_at, source FROM templates"
        )
        for row in cursor.fetchall():
            tpl = LogTemplate(
                template_id=row[0],
                template_str=row[1],
                token_count=row[2],
                first_token=row[3],
                tokens=json.loads(row[4]),
                hit_count=row[5],
                created_at=row[6] or 0.0,
                last_hit_at=row[7] or 0.0,
                source=row[8] or "llm",
            )
            bucket = self._cache.setdefault(tpl.token_count, {})
            bucket.setdefault(tpl.first_token, []).append(tpl)

    def lookup(self, tokens: List[str]) -> Optional[LogTemplate]:
        """缓存查找：返回最佳匹配模板或 None"""
        if not tokens:
            return None

        token_count = len(tokens)
        first_token = tokens[0]

        bucket = self._cache.get(token_count)
        if bucket is None:
            return None

        candidates = bucket.get(first_token, [])
        if not candidates:
            return None

        best_match: Optional[LogTemplate] = None
        best_score = 0.0

        for tpl in candidates:
            score = token_similarity(tokens, tpl.tokens)
            if score > best_score:
                best_score = score
                best_match = tpl

        if best_score >= self._threshold and best_match is not None:
            self._record_hit(best_match)
            return best_match

        return None

    def insert(self, template: LogTemplate, raw_example: Optional[str] = None) -> LogTemplate:
        """插入新模板到缓存（去重）"""
        with self._lock:
            existing = self._find_equivalent(template.template_str)
            if existing:
                self._record_hit(existing)
                return existing

            now = time.time()
            template.created_at = now
            template.last_hit_at = now

            self._conn.execute(
                "INSERT OR IGNORE INTO templates "
                "(template_id, template_str, token_count, first_token, tokens_json, "
                "hit_count, created_at, last_hit_at, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    template.template_id,
                    template.template_str,
                    template.token_count,
                    template.first_token,
                    json.dumps(template.tokens),
                    template.hit_count,
                    template.created_at,
                    template.last_hit_at,
                    template.source,
                ),
            )

            if raw_example:
                self._conn.execute(
                    "INSERT OR IGNORE INTO demonstrations (raw_log, template_id, created_at) "
                    "VALUES (?, ?, ?)",
                    (raw_example, template.template_id, now),
                )

            self._conn.commit()

            bucket = self._cache.setdefault(template.token_count, {})
            bucket.setdefault(template.first_token, []).append(template)

            return template

    def _find_equivalent(self, template_str: str) -> Optional[LogTemplate]:
        tid = LogTemplate.generate_id(template_str)
        for bucket in self._cache.values():
            for candidates in bucket.values():
                for tpl in candidates:
                    if tpl.template_id == tid:
                        return tpl
        return None

    def _record_hit(self, template: LogTemplate) -> None:
        template.hit_count += 1
        template.last_hit_at = time.time()
        self._conn.execute(
            "UPDATE templates SET hit_count = ?, last_hit_at = ? WHERE template_id = ?",
            (template.hit_count, template.last_hit_at, template.template_id),
        )

    def get_statistics(self) -> Dict[str, int]:
        total_templates = sum(
            len(cands)
            for bucket in self._cache.values()
            for cands in bucket.values()
        )
        total_hits = sum(
            tpl.hit_count
            for bucket in self._cache.values()
            for cands in bucket.values()
            for tpl in cands
        )
        return {"total_templates": total_templates, "total_hits": total_hits}

    def get_all_templates(self) -> List[LogTemplate]:
        result = []
        for bucket in self._cache.values():
            for cands in bucket.values():
                result.extend(cands)
        return result

    def clear(self) -> None:
        with self._lock:
            self._conn.executescript(
                "DELETE FROM demonstrations; DELETE FROM templates;"
            )
            self._conn.commit()
            self._cache.clear()

    def close(self) -> None:
        self._conn.close()
