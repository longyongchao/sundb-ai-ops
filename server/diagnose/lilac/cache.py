"""LILAC 自适应解析缓存（SQLite-backed）"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from typing import Dict, List, Optional

from server.diagnose.lilac.models import LogTemplate
from server.diagnose.lilac.similarity import token_similarity, token_similarity_fuzzy

logger = logging.getLogger(__name__)

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

    def __init__(self, db_path: str, similarity_threshold: float = 0.85, merge_enabled: bool = True):
        self._db_path = db_path
        self._threshold = similarity_threshold
        self._merge_enabled = merge_enabled
        self._lock = threading.RLock()

        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()

        self._cache: Dict[int, Dict[str, List[LogTemplate]]] = {}
        self._token_sig_index: Dict[tuple, LogTemplate] = {}
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

    def _gather_candidates(self, bucket: Dict[str, List[LogTemplate]], first_token: str) -> List[LogTemplate]:
        """从 bucket 中收集候选模板：精确匹配 + 通配 first_token"""
        candidates = list(bucket.get(first_token, []))
        for stored_ft, tpls in bucket.items():
            if stored_ft != first_token and "<*>" in stored_ft:
                candidates.extend(tpls)
        return candidates

    def lookup(self, tokens: List[str]) -> Optional[LogTemplate]:
        """缓存查找：签名精确匹配 → 相似度匹配 → 模糊 ±1 token 匹配"""
        if not tokens:
            return None

        # (0) token 签名精确匹配（处理 LLM 模板 token 结构与输入不一致的情况）
        sig = tuple(tokens)
        sig_hit = self._token_sig_index.get(sig)
        if sig_hit is not None:
            self._record_hit(sig_hit)
            return sig_hit

        token_count = len(tokens)
        first_token = tokens[0]

        best_match: Optional[LogTemplate] = None
        best_score = 0.0

        # (1) 精确 token_count 匹配
        bucket = self._cache.get(token_count)
        if bucket:
            candidates = self._gather_candidates(bucket, first_token)
            for tpl in candidates:
                score = token_similarity(tokens, tpl.tokens)
                if score > best_score:
                    best_score = score
                    best_match = tpl

        if best_score >= self._threshold and best_match is not None:
            self._record_hit(best_match)
            return best_match

        # (2) 模糊 ±1 token_count 匹配
        for offset in (-1, 1):
            fuzzy_bucket = self._cache.get(token_count + offset)
            if not fuzzy_bucket:
                continue
            candidates = self._gather_candidates(fuzzy_bucket, first_token)
            for tpl in candidates:
                score = token_similarity_fuzzy(tokens, tpl.tokens)
                if score > best_score:
                    best_score = score
                    best_match = tpl

        if best_score >= self._threshold and best_match is not None:
            self._record_hit(best_match)
            return best_match

        return None

    def insert(self, template: LogTemplate, raw_example: Optional[str] = None,
               lookup_tokens: Optional[List[str]] = None) -> LogTemplate:
        """插入新模板到缓存（去重）

        lookup_tokens: 如果模板的 token 结构与输入不一致（如 LLM 合并了多个 token），
                       传入原始输入的 tokens 用于建立签名索引。
        """
        with self._lock:
            existing = self._find_equivalent(template.template_str)
            if existing:
                self._record_hit(existing)
                if lookup_tokens:
                    self._token_sig_index[tuple(lookup_tokens)] = existing
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

            if lookup_tokens:
                self._token_sig_index[tuple(lookup_tokens)] = template

            if self._merge_enabled:
                self._try_merge_after_insert(template)

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
        with self._lock:
            self._conn.execute(
                "UPDATE templates SET hit_count = ?, last_hit_at = ? WHERE template_id = ?",
                (template.hit_count, template.last_hit_at, template.template_id),
            )
            self._conn.commit()

    # ------ Template Merging ------

    def _try_merge_after_insert(self, new_template: LogTemplate) -> None:
        """检查新插入模板是否可以与同 token_count 的已有模板合并"""
        bucket = self._cache.get(new_template.token_count)
        if not bucket:
            return

        for first_token, candidates in list(bucket.items()):
            for existing in candidates:
                if existing.template_id == new_template.template_id:
                    continue
                merged = self._compute_merge(existing, new_template)
                if merged:
                    self._apply_merge(existing, new_template, merged)
                    return

    def _compute_merge(self, t1: LogTemplate, t2: LogTemplate) -> Optional[LogTemplate]:
        """判断两个模板是否可合并（恰好 1 个位置不同且差异段是数字型）"""
        if t1.token_count != t2.token_count:
            return None

        diff_positions = []
        merged_tokens = []

        for i, (tok1, tok2) in enumerate(zip(t1.tokens, t2.tokens)):
            if tok1 == tok2:
                merged_tokens.append(tok1)
            else:
                diff_positions.append(i)
                if len(diff_positions) > 1:
                    return None
                merged_tok = self._merge_tokens(tok1, tok2)
                if merged_tok is None:
                    return None
                merged_tokens.append(merged_tok)

        if len(diff_positions) != 1:
            return None

        merged_str = " ".join(merged_tokens)
        return LogTemplate(
            template_id=LogTemplate.generate_id(merged_str),
            template_str=merged_str,
            tokens=merged_tokens,
            token_count=len(merged_tokens),
            first_token=merged_tokens[0],
            hit_count=t1.hit_count + t2.hit_count,
            created_at=min(t1.created_at, t2.created_at),
            last_hit_at=max(t1.last_hit_at, t2.last_hit_at),
            source=t1.source,
        )

    @staticmethod
    def _merge_tokens(tok1: str, tok2: str) -> Optional[str]:
        """合并两个不同 token：找公共前后缀，中间替换为 <*>

        仅当差异部分是数字型时才合并。
        如果任一 token 已经是 <*>，直接返回 <*>。
        """
        if tok1 == "<*>" or tok2 == "<*>":
            return "<*>"

        prefix_len = 0
        min_len = min(len(tok1), len(tok2))
        while prefix_len < min_len and tok1[prefix_len] == tok2[prefix_len]:
            prefix_len += 1

        suffix_len = 0
        while (suffix_len < min_len - prefix_len
               and tok1[-(suffix_len + 1)] == tok2[-(suffix_len + 1)]):
            suffix_len += 1

        end1 = len(tok1) - suffix_len if suffix_len else len(tok1)
        end2 = len(tok2) - suffix_len if suffix_len else len(tok2)
        mid1 = tok1[prefix_len:end1]
        mid2 = tok2[prefix_len:end2]

        # If either middle is already <*>, the merge result keeps <*>
        if mid1 == "<*>" or mid2 == "<*>":
            prefix = tok1[:prefix_len]
            suffix = tok1[end1:] if suffix_len else ""
            return f"{prefix}<*>{suffix}"

        if not AdaptiveParsingCache._is_variable_segment(mid1, mid2):
            return None

        # If middles are numeric and suffix is also numeric, absorb suffix into wildcard
        prefix = tok1[:prefix_len]
        suffix = tok1[end1:] if suffix_len else ""
        if suffix and suffix.isdigit():
            suffix = ""

        return f"{prefix}<*>{suffix}"

    @staticmethod
    def _is_variable_segment(mid1: str, mid2: str) -> bool:
        """判断两个差异段是否都适合作为变量（可合并为 <*>）

        规则：两段都必须是短的字母数字组合，且至少有一段包含数字。
        """
        if not mid1 and not mid2:
            return True

        combined = mid1 + mid2
        if not any(c.isdigit() for c in combined):
            return False

        return (AdaptiveParsingCache._is_numeric_like(mid1)
                and AdaptiveParsingCache._is_numeric_like(mid2))

    @staticmethod
    def _is_numeric_like(s: str) -> bool:
        """判断字符串是否为数字型（可作为模板变量的短标识符）

        接受：空串、纯数字、含数字的短字母数字混合、纯十六进制
        拒绝：纯字母长单词（如 ERROR、WARNING）
        """
        if not s:
            return True
        if s.isdigit():
            return True
        if re.fullmatch(r'[0-9a-fA-F]+', s) and len(s) <= 16:
            return True
        if re.fullmatch(r'[a-zA-Z0-9_.-]+', s) and len(s) <= 12 and any(c.isdigit() for c in s):
            return True
        return False

    def _apply_merge(self, old: LogTemplate, new: LogTemplate, merged: LogTemplate) -> None:
        """执行合并：删除旧模板，插入合并后的模板"""
        with self._lock:
            self._conn.execute("DELETE FROM templates WHERE template_id = ?", (old.template_id,))
            self._conn.execute("DELETE FROM templates WHERE template_id = ?", (new.template_id,))

            self._conn.execute(
                "UPDATE demonstrations SET template_id = ? WHERE template_id = ?",
                (merged.template_id, old.template_id),
            )
            self._conn.execute(
                "UPDATE demonstrations SET template_id = ? WHERE template_id = ?",
                (merged.template_id, new.template_id),
            )

            self._conn.execute(
                "INSERT OR IGNORE INTO templates "
                "(template_id, template_str, token_count, first_token, tokens_json, "
                "hit_count, created_at, last_hit_at, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    merged.template_id,
                    merged.template_str,
                    merged.token_count,
                    merged.first_token,
                    json.dumps(merged.tokens),
                    merged.hit_count,
                    merged.created_at,
                    merged.last_hit_at,
                    merged.source,
                ),
            )
            self._conn.commit()

        self._remove_from_memory(old)
        self._remove_from_memory(new)

        bucket = self._cache.setdefault(merged.token_count, {})
        bucket.setdefault(merged.first_token, []).append(merged)

        logger.debug(
            f"[LILAC] 模板合并: '{old.template_str}' + '{new.template_str}' → '{merged.template_str}'"
        )

    def _remove_from_memory(self, template: LogTemplate) -> None:
        """从内存缓存中移除指定模板"""
        bucket = self._cache.get(template.token_count)
        if not bucket:
            return
        candidates = bucket.get(template.first_token)
        if not candidates:
            return
        bucket[template.first_token] = [t for t in candidates if t.template_id != template.template_id]
        if not bucket[template.first_token]:
            del bucket[template.first_token]

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
            self._token_sig_index.clear()

    def close(self) -> None:
        self._conn.close()
