#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sidecar collectors for self-evolution V0.1."""
import hashlib
import json
import logging
import os
from datetime import date, datetime
from typing import Any, Dict, Optional

from server.evolution.evaluator import calculate_outcome_score

SENSITIVE_KEYWORDS = ("password", "passwd", "pwd", "token", "api_key", "apikey", "secret", "authorization", "credential")
MAX_STRING_LENGTH = 4000
logger = logging.getLogger(__name__)


def sanitize_snapshot(value: Any, max_string_length: int = MAX_STRING_LENGTH) -> Any:
    """Recursively sanitize snapshots before persisting them."""
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) > max_string_length:
            return value[:max_string_length] + f"...<truncated:{len(value) - max_string_length}>"
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, bytes):
        return sanitize_snapshot(value.decode("utf-8", errors="replace"), max_string_length=max_string_length)

    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_str = str(key)
            if any(keyword in key_str.lower() for keyword in SENSITIVE_KEYWORDS):
                cleaned[key_str] = "***REDACTED***"
            else:
                cleaned[key_str] = sanitize_snapshot(item, max_string_length=max_string_length)
        return cleaned

    if isinstance(value, (list, tuple, set)):
        return [sanitize_snapshot(item, max_string_length=max_string_length) for item in value]

    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return sanitize_snapshot(str(value), max_string_length=max_string_length)


def build_case_fingerprint(anomaly_info: Dict[str, Any], result: Dict[str, Any]) -> str:
    seed = {
        "alert_type": anomaly_info.get("alert_type") or result.get("alert_type") or result.get("anomaly_type"),
        "description": anomaly_info.get("description") or anomaly_info.get("user_input"),
        "root_causes": [
            {
                "type": cause.get("type"),
                "description": cause.get("description"),
            }
            for cause in result.get("root_causes", [])
            if isinstance(cause, dict)
        ],
    }
    raw = json.dumps(sanitize_snapshot(seed), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_file(path: str) -> Optional[str]:
    if not os.path.exists(path) or not os.path.isfile(path):
        return None

    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_current_asset_versions() -> Dict[str, Any]:
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    knowledge_path = os.path.join(root, "doc2knowledge", "root_causes_dbmind.jsonl")
    knowledge_hash = _hash_file(knowledge_path)

    return {
        "knowledge": {
            "source": "doc2knowledge/root_causes_dbmind.jsonl",
            "sha256": knowledge_hash or "missing",
        },
        "retrieval_policy": "hybrid_default_v0.1",
        "tool_policy": "tree_search_default_v0.1",
        "prompt": "tree_search_prompt_default_v0.1",
    }


def _create_evolution_case(payload: Dict[str, Any]) -> Optional[int]:
    from server.db.repository.evolution_repository import create_evolution_case

    return create_evolution_case(payload)


def capture_diagnosis_result(anomaly_info: Dict[str, Any], result: Dict[str, Any], record_id: int = None) -> Optional[int]:
    search_stats = result.get("search_stats", {}) or {}
    reasoning_steps = result.get("reasoning_steps", []) or []
    retrieved_knowledge = result.get("retrieved_knowledge", []) or []

    payload = {
        "record_id": record_id or result.get("record_id"),
        "diagnosis_id": anomaly_info.get("diagnosis_id") or result.get("diagnosis_id"),
        "case_fingerprint": build_case_fingerprint(anomaly_info, result),
        "anomaly_type": anomaly_info.get("alert_type") or result.get("anomaly_type") or result.get("alert_type"),
        "input_snapshot": sanitize_snapshot(anomaly_info or {}),
        "trace_snapshot": sanitize_snapshot({
            "reasoning_steps": reasoning_steps,
            "search_stats": search_stats,
            "tool_match_scores": result.get("tool_match_scores", []),
            "reflection_insights": result.get("reflection_insights", []),
        }),
        "knowledge_snapshot": sanitize_snapshot({
            "retrieved_knowledge": retrieved_knowledge,
            "knowledge_chunks_used": search_stats.get("knowledge_matches", 0),
        }),
        "output_snapshot": sanitize_snapshot({
            "root_causes": result.get("root_causes", []),
            "solutions": result.get("solutions", []),
            "confidence": result.get("confidence", 0.0),
            "diagnosis_time": result.get("diagnosis_time", 0.0),
            "anomaly_type_display": result.get("anomaly_type_display"),
            "quick_action_guide": result.get("quick_action_guide", []),
        }),
        "asset_versions": sanitize_snapshot(get_current_asset_versions()),
        "outcome_score": 0.0,
        "label": "uncertain_case",
        "status": "captured",
    }

    return _create_evolution_case(payload)


def capture_user_feedback(
    message_id: str = None,
    score: float = None,
    reason: str = "",
    record_id: int = None,
    case_id: int = None,
    evolution_case_id: int = None,
    feedback_type: str = "user_feedback",
    accepted: Optional[bool] = None,
    metric_recovery: Dict[str, Any] = None,
    recurrence: Optional[bool] = None,
    raw_feedback: Dict[str, Any] = None,
) -> Optional[int]:
    from server.db.repository.evolution_repository import (
        create_evolution_feedback,
        get_evolution_case_by_id,
        get_evolution_case_by_record_id,
        update_evolution_case_score,
    )

    resolved_case_id = evolution_case_id or case_id
    case = get_evolution_case_by_id(resolved_case_id) if resolved_case_id else None

    if not case and record_id:
        case = get_evolution_case_by_record_id(record_id)
        resolved_case_id = case.get("id") if case else None

    payload = {
        "case_id": resolved_case_id,
        "record_id": record_id or (case or {}).get("record_id"),
        "message_id": message_id,
        "feedback_type": feedback_type or "user_feedback",
        "score": score,
        "reason": reason,
        "accepted": accepted,
        "metric_recovery": sanitize_snapshot(metric_recovery or {}),
        "recurrence": recurrence,
        "raw_feedback": sanitize_snapshot(raw_feedback or {}),
    }
    feedback_id = create_evolution_feedback(payload)

    if resolved_case_id and case:
        feedback_for_score = {
            "score": score,
            "accepted": accepted,
            "metric_recovery": metric_recovery or {},
            "recurrence": recurrence,
        }
        evaluation = calculate_outcome_score(case, feedback=feedback_for_score)
        updated = update_evolution_case_score(
            resolved_case_id,
            evaluation["outcome_score"],
            evaluation["label"],
        )
        if not updated:
            logger.warning(f"自进化案例评分更新失败，case_id={resolved_case_id}")

    return feedback_id
