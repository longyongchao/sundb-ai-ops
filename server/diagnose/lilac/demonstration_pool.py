"""LILAC Demonstration 池管理 + 贪心 DPP 采样"""

import sqlite3
from typing import Dict, List, Optional, Tuple

from server.diagnose.lilac.similarity import token_similarity


class DemonstrationPool:
    """ICL 示例池，支持贪心多样化采样"""

    def __init__(self, conn: sqlite3.Connection, max_size: int = 500):
        self._conn = conn
        self._max_size = max_size

    def get_all(self) -> List[Dict[str, str]]:
        cursor = self._conn.execute(
            "SELECT d.raw_log, t.template_str "
            "FROM demonstrations d "
            "JOIN templates t ON d.template_id = t.template_id "
            "ORDER BY d.created_at DESC "
            "LIMIT ?",
            (self._max_size,),
        )
        return [{"raw_log": row[0], "template": row[1]} for row in cursor.fetchall()]

    def sample(self, query_tokens: List[str], k: int = 5) -> List[Dict[str, str]]:
        """贪心 DPP 采样：兼顾相关性和多样性"""
        pool = self.get_all()
        if not pool:
            return []
        if len(pool) <= k:
            return pool

        scored = []
        for demo in pool:
            demo_tokens = demo["template"].split()
            rel_score = token_similarity(query_tokens, demo_tokens)
            scored.append((demo, rel_score, demo_tokens))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_n = scored[: k * 3]

        if not top_n:
            return pool[:k]

        selected: List[Tuple[Dict[str, str], List[str]]] = []
        selected.append((top_n[0][0], top_n[0][2]))
        remaining = top_n[1:]

        while len(selected) < k and remaining:
            best_idx = -1
            best_diversity = -1.0
            for i, (demo, _rel, demo_tokens) in enumerate(remaining):
                min_sim = min(
                    token_similarity(demo_tokens, sel_tokens)
                    for _, sel_tokens in selected
                )
                diversity = 1.0 - min_sim
                if diversity > best_diversity:
                    best_diversity = diversity
                    best_idx = i

            if best_idx < 0:
                break
            chosen = remaining.pop(best_idx)
            selected.append((chosen[0], chosen[2]))

        return [s[0] for s in selected]

    def size(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) FROM demonstrations")
        return cursor.fetchone()[0]
