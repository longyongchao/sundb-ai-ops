#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rule-based pattern miner for self-evolution V0.2.

Analyzes negative and uncertain cases to identify four types of systematic
failure patterns, then persists them as EvolutionPattern records.
"""
import logging
from collections import defaultdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PATTERN_MISSING_KNOWLEDGE = "missing_knowledge"
PATTERN_WRONG_TOOL = "wrong_tool_selection"
PATTERN_LOW_CONFIDENCE = "low_confidence_prompt"
PATTERN_RETRIEVAL_WEIGHT = "retrieval_weight_issue"

SLOW_QUERY_KEYWORDS = ("slow", "query", "sql", "latency", "timeout", "slowquery")
SLOW_QUERY_EXPECTED_TOOLS = ("explain_query", "index", "slow_query", "query_plan", "get_query_plan", "get_slow_queries")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_cases_for_mining(limit: int = 500) -> List[Dict]:
    from server.db.repository.evolution_repository import list_evolution_cases_for_mining
    return list_evolution_cases_for_mining(limit=limit)


def _knowledge_chunks_used(case: Dict) -> int:
    snap = case.get("knowledge_snapshot") or {}
    try:
        return int(snap.get("knowledge_chunks_used") or 0)
    except (TypeError, ValueError):
        return 0


def _tool_names(case: Dict) -> List[str]:
    """Extract all action/tool names from reasoning steps."""
    trace = case.get("trace_snapshot") or {}
    steps = trace.get("reasoning_steps") or []
    names = []
    for step in steps:
        if isinstance(step, dict):
            action = step.get("action") or step.get("tool") or ""
            if action:
                names.append(str(action).lower())
    return names


def _max_root_cause_confidence(case: Dict) -> float:
    output = case.get("output_snapshot") or {}
    root_causes = output.get("root_causes") or []
    values = []
    for rc in root_causes:
        if isinstance(rc, dict):
            conf = rc.get("confidence")
            if conf is not None:
                try:
                    v = float(conf)
                    values.append(v / 100.0 if v > 1 else v)
                except (TypeError, ValueError):
                    pass
    return max(values) if values else 0.0


def _is_slow_query_case(case: Dict) -> bool:
    atype = (case.get("anomaly_type") or "").lower()
    return any(kw in atype for kw in SLOW_QUERY_KEYWORDS)


# ── Mining Rules ──────────────────────────────────────────────────────────────

def _mine_missing_knowledge(cases: List[Dict], min_cases: int) -> List[Dict]:
    """Detect anomaly clusters where knowledge retrieval consistently returns nothing."""
    clusters: Dict[str, List[Dict]] = defaultdict(list)
    for case in cases:
        if _knowledge_chunks_used(case) == 0:
            key = case.get("anomaly_type") or "unknown"
            clusters[key].append(case)

    patterns = []
    for anomaly_type, cluster in clusters.items():
        if len(cluster) < min_cases:
            continue
        evidence_ids = [c["id"] for c in cluster if c.get("id")]
        confidence = min(0.50 + 0.05 * (len(cluster) - min_cases), 0.95)
        patterns.append({
            "pattern_type": PATTERN_MISSING_KNOWLEDGE,
            "cluster_key": anomaly_type,
            "evidence_case_ids": evidence_ids[:20],
            "failure_signature": (
                f"异常类型 '{anomaly_type}' 下有 {len(cluster)} 个案例"
                "检索知识为空（knowledge_chunks_used=0），"
                "可能存在知识库空洞。"
            ),
            "suggested_update_type": "knowledge_patch",
            "confidence": round(confidence, 4),
        })
    return patterns


def _mine_wrong_tool_selection(cases: List[Dict], min_cases: int) -> List[Dict]:
    """Detect slow-query cases that skipped essential diagnostic tools."""
    weak = [
        c for c in cases
        if _is_slow_query_case(c)
        and not any(t in " ".join(_tool_names(c)) for t in SLOW_QUERY_EXPECTED_TOOLS)
    ]
    if len(weak) < min_cases:
        return []

    evidence_ids = [c["id"] for c in weak if c.get("id")]
    confidence = min(0.50 + 0.04 * (len(weak) - min_cases), 0.90)
    return [{
        "pattern_type": PATTERN_WRONG_TOOL,
        "cluster_key": "slow_query_missing_tools",
        "evidence_case_ids": evidence_ids[:20],
        "failure_signature": (
            f"{len(weak)} 个慢 SQL 相关案例未调用 explain_query 或索引建议工具，"
            "可能导致根因分析不完整。"
        ),
        "suggested_update_type": "tool_strategy_patch",
        "confidence": round(confidence, 4),
    }]


def _mine_low_confidence_prompt(cases: List[Dict], min_cases: int) -> List[Dict]:
    """Detect cases with tool calls but persistently low root-cause confidence."""
    candidates = [
        c for c in cases
        if len(_tool_names(c)) > 0 and _max_root_cause_confidence(c) < 0.5
    ]

    clusters: Dict[str, List[Dict]] = defaultdict(list)
    for c in candidates:
        clusters[c.get("anomaly_type") or "unknown"].append(c)

    patterns = []
    for anomaly_type, cluster in clusters.items():
        if len(cluster) < min_cases:
            continue
        evidence_ids = [c["id"] for c in cluster if c.get("id")]
        confidence = min(0.40 + 0.08 * len(cluster), 0.85)
        patterns.append({
            "pattern_type": PATTERN_LOW_CONFIDENCE,
            "cluster_key": f"low_conf_{anomaly_type}",
            "evidence_case_ids": evidence_ids[:20],
            "failure_signature": (
                f"异常类型 '{anomaly_type}' 下有 {len(cluster)} 个案例"
                "有工具调用但根因置信度 < 0.5，"
                "可能需要优化提示词以提升根因提取质量。"
            ),
            "suggested_update_type": "prompt_patch",
            "confidence": round(confidence, 4),
        })
    return patterns


def _mine_retrieval_weight_issue(cases: List[Dict], min_cases: int) -> List[Dict]:
    """Detect cases with imbalanced BM25 / vector retrieval scores."""
    imbalanced = []
    for c in cases:
        knowledge_snap = c.get("knowledge_snapshot") or {}
        retrieved = knowledge_snap.get("retrieved_knowledge") or []
        bm25_scores, vector_scores = [], []
        for chunk in retrieved:
            if not isinstance(chunk, dict):
                continue
            bm25 = chunk.get("bm25_score") or chunk.get("score_bm25")
            vec = chunk.get("vector_score") or chunk.get("score_vector")
            if bm25 is not None:
                try:
                    bm25_scores.append(float(bm25))
                except (TypeError, ValueError):
                    pass
            if vec is not None:
                try:
                    vector_scores.append(float(vec))
                except (TypeError, ValueError):
                    pass

        if bm25_scores and vector_scores:
            avg_bm25 = sum(bm25_scores) / len(bm25_scores)
            avg_vec = sum(vector_scores) / len(vector_scores)
            if abs(avg_bm25 - avg_vec) > 0.3:
                imbalanced.append({"case": c, "diff": avg_bm25 - avg_vec})

    if len(imbalanced) < min_cases:
        return []

    evidence_ids = [item["case"]["id"] for item in imbalanced if item["case"].get("id")]
    avg_diff = sum(i["diff"] for i in imbalanced) / len(imbalanced)
    direction = "BM25 偏低" if avg_diff < 0 else "向量检索偏低"
    confidence = min(0.40 + 0.06 * len(imbalanced), 0.80)
    return [{
        "pattern_type": PATTERN_RETRIEVAL_WEIGHT,
        "cluster_key": "retrieval_weight_imbalance",
        "evidence_case_ids": evidence_ids[:20],
        "failure_signature": (
            f"{len(imbalanced)} 个案例检索权重失衡（{direction}，"
            f"平均差值 {abs(avg_diff):.2f}），可能影响知识检索质量。"
        ),
        "suggested_update_type": "retrieval_strategy_patch",
        "confidence": round(confidence, 4),
    }]


# ── Public API ────────────────────────────────────────────────────────────────

def mine_patterns(min_cases: int = 3, save: bool = True) -> List[Dict]:
    """Mine failure patterns from recent negative and uncertain evolution cases.

    Args:
        min_cases: Minimum cluster size required to emit a pattern.
        save: Persist discovered patterns to the database.

    Returns:
        List of pattern dicts (EvolutionPattern fields).
        Each saved pattern will have its ``id`` populated.
    """
    try:
        cases = _get_cases_for_mining()
    except Exception as exc:
        logger.error(f"模式挖掘：获取案例失败：{exc}")
        return []

    if not cases:
        logger.info("模式挖掘：暂无可用的负例/不确定案例")
        return []

    logger.info(f"模式挖掘：开始分析 {len(cases)} 个案例，min_cases={min_cases}")

    all_patterns: List[Dict] = []
    all_patterns += _mine_missing_knowledge(cases, min_cases)
    all_patterns += _mine_wrong_tool_selection(cases, min_cases)
    all_patterns += _mine_low_confidence_prompt(cases, min_cases)
    all_patterns += _mine_retrieval_weight_issue(cases, min_cases)

    logger.info(f"模式挖掘：发现 {len(all_patterns)} 个模式")

    if save and all_patterns:
        try:
            from server.db.repository.evolution_repository import create_evolution_pattern
            for pattern in all_patterns:
                pid = create_evolution_pattern(pattern)
                pattern["id"] = pid
        except Exception as exc:
            logger.warning(f"模式挖掘：持久化失败，模式仍返回（无 id）：{exc}")

    return all_patterns
