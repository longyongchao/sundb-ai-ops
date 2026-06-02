#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Candidate patch generator for self-evolution V0.2.

Converts a mined EvolutionPattern into a concrete EvolutionCandidate that
describes exactly what should be changed (knowledge block, tool rule, prompt
addition, or retrieval weight) and at what risk level.

Candidates are always created in ``pending`` status; they do NOT affect live
diagnosis until promoted through the gatekeeper (V0.3).
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PATCH_BUILDERS = {}  # populated below via decorator


def _patch_builder(pattern_type: str, candidate_type: str, target_artifact: str, risk: str):
    """Register a builder function for a pattern type."""
    def decorator(fn):
        _PATCH_BUILDERS[pattern_type] = {
            "fn": fn,
            "candidate_type": candidate_type,
            "target_artifact_type": target_artifact,
            "risk_level": risk,
        }
        return fn
    return decorator


# ── Evidence Fetcher ──────────────────────────────────────────────────────────

def _fetch_evidence_cases(evidence_case_ids: List[int], limit: int = 10) -> List[Dict]:
    if not evidence_case_ids:
        return []
    try:
        from server.db.repository.evolution_repository import get_evolution_case_by_id
        result = []
        for cid in evidence_case_ids[:limit]:
            case = get_evolution_case_by_id(cid)
            if case:
                result.append(case)
        return result
    except Exception as exc:
        logger.warning(f"候选生成：获取证据案例失败：{exc}")
        return []


# ── Patch Builders ────────────────────────────────────────────────────────────

@_patch_builder("missing_knowledge", "knowledge_patch", "knowledge", "low")
def _build_knowledge_patch(pattern: Dict, cases: List[Dict]) -> Dict:
    anomaly_type = pattern.get("cluster_key") or "unknown"

    root_cause_types = set()
    for case in cases:
        output = case.get("output_snapshot") or {}
        for rc in output.get("root_causes") or []:
            if isinstance(rc, dict) and rc.get("type"):
                root_cause_types.add(rc["type"])

    return {
        "operation": "add",
        "knowledge_block": {
            "cause_name": f"auto_patch_{anomaly_type.lower().replace(' ', '_')}",
            "anomaly_type": anomaly_type,
            "description": (
                f"针对 '{anomaly_type}' 异常类型，历史诊断案例中未能检索到有效知识块，"
                "建议根据实际故障案例补充该类型的根因分析知识。"
            ),
            "evidence_root_causes": sorted(root_cause_types),
            "suggested_steps": [
                f"收集 '{anomaly_type}' 历史告警与修复记录",
                "提炼根因描述、关联指标和处置步骤",
                "以 JSONL 格式补充到 doc2knowledge 知识库",
            ],
            "priority": "high" if len(cases) >= 5 else "medium",
        },
    }


@_patch_builder("wrong_tool_selection", "tool_strategy_patch", "tool_policy", "medium")
def _build_tool_strategy_patch(pattern: Dict, cases: List[Dict]) -> Dict:
    return {
        "operation": "add_rule",
        "rule": {
            "trigger_condition": "anomaly_type 包含 slow / query / sql / timeout 等慢查询关键词",
            "required_tools": ["explain_query", "get_slow_queries"],
            "recommended_sequence": [
                "get_slow_queries",
                "explain_query",
                "get_index_info",
                "analyze_query_plan",
            ],
            "rationale": (
                "慢 SQL 诊断中应优先调用 explain_query 获取执行计划，"
                "再结合索引信息分析瓶颈。历史案例显示缺失此步骤导致根因分析不完整。"
            ),
        },
    }


@_patch_builder("low_confidence_prompt", "prompt_patch", "prompt", "medium")
def _build_prompt_patch(pattern: Dict, cases: List[Dict]) -> Dict:
    anomaly_type = (pattern.get("cluster_key") or "").replace("low_conf_", "")
    return {
        "operation": "add_instruction",
        "target": "root_cause_extraction",
        "instruction": {
            "anomaly_type": anomaly_type or "general",
            "addition": (
                "在生成根因结论时，必须引用具体工具观察结果作为证据。"
                "如果无法找到直接证据，confidence 应设置为 0.3 以下并注明数据不足。"
                "不得基于假设输出高置信度根因。"
            ),
            "rationale": (
                f"'{anomaly_type}' 类型案例中工具调用有记录但根因置信度持续偏低，"
                "表明当前提示词未能有效引导模型将工具观测转化为高质量根因。"
            ),
        },
    }


@_patch_builder("retrieval_weight_issue", "retrieval_strategy_patch", "retrieval_policy", "low")
def _build_retrieval_strategy_patch(pattern: Dict, cases: List[Dict]) -> Dict:
    return {
        "operation": "adjust_weights",
        "target": "hybrid_retrieval",
        "adjustment": {
            "current_policy": "hybrid_default_v0.1",
            "suggested_bm25_weight": 0.4,
            "suggested_vector_weight": 0.6,
            "rationale": (
                "历史案例中检索权重失衡，建议适当提高向量检索权重以改善语义匹配质量。"
                "具体权重应在沙盒回放（V0.3）中通过对比实验最终确定。"
            ),
        },
    }


# ── Public API ────────────────────────────────────────────────────────────────

def generate_candidates_from_pattern(pattern: Dict, save: bool = True) -> List[Dict]:
    """Generate candidate patches for a single mined pattern.

    Args:
        pattern: EvolutionPattern dict (must have ``pattern_type`` and
            ``evidence_case_ids``). If ``id`` is present, it is stored as
            ``source_pattern_id`` in the candidate.
        save: Persist the candidate to the database.

    Returns:
        List with a single candidate dict, or empty list on unknown pattern type.
    """
    pattern_type = pattern.get("pattern_type")
    if pattern_type not in _PATCH_BUILDERS:
        logger.warning(f"候选生成：未知模式类型 '{pattern_type}'，跳过")
        return []

    spec = _PATCH_BUILDERS[pattern_type]
    evidence_ids = pattern.get("evidence_case_ids") or []
    cases = _fetch_evidence_cases(evidence_ids)

    try:
        patch_content = spec["fn"](pattern, cases)
    except Exception as exc:
        logger.error(f"候选生成：构建 {pattern_type} 补丁失败：{exc}")
        return []

    candidate: Dict[str, Any] = {
        "candidate_type": spec["candidate_type"],
        "source_pattern_id": pattern.get("id"),
        "patch_content": patch_content,
        "expected_benefit": pattern.get("failure_signature", ""),
        "risk_level": spec["risk_level"],
        "status": "pending",
        "evidence_case_ids": evidence_ids[:20],
        "target_artifact_type": spec["target_artifact_type"],
        "base_artifact_version": f"{spec['target_artifact_type']}_default_v0.1",
    }

    if save and pattern.get("id") is not None:
        try:
            from server.db.repository.evolution_repository import create_evolution_candidate
            cid = create_evolution_candidate(candidate)
            candidate["id"] = cid
        except Exception as exc:
            logger.warning(f"候选生成：持久化失败，候选仍返回（无 id）：{exc}")

    return [candidate]


def generate_all_candidates(patterns: List[Dict], save: bool = True) -> List[Dict]:
    """Generate candidates for every pattern in the list.

    Args:
        patterns: List of EvolutionPattern dicts (typically from mine_patterns).
        save: Forward to generate_candidates_from_pattern.

    Returns:
        Flat list of all generated candidate dicts.
    """
    all_candidates: List[Dict] = []
    for pattern in patterns:
        all_candidates.extend(generate_candidates_from_pattern(pattern, save=save))
    logger.info(f"候选生成：从 {len(patterns)} 个模式生成了 {len(all_candidates)} 个候选")
    return all_candidates
