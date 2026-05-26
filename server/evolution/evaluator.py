#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Outcome scoring for self-evolution cases."""
from typing import Dict, Optional


def _normalize_score(score) -> Optional[float]:
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value > 1:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def calc_root_cause_match(case: Dict, feedback: Dict = None) -> float:
    output = case.get("output_snapshot") or {}
    root_causes = output.get("root_causes") or []
    if not root_causes:
        return 0.0

    confidences = []
    for cause in root_causes:
        if isinstance(cause, dict):
            confidences.append(_normalize_score(cause.get("confidence")) or 0.6)
    return max(confidences) if confidences else 0.6


def calc_metric_recovery(case: Dict, post_metrics: Dict = None) -> float:
    metrics = post_metrics or {}
    if not metrics:
        return 0.5

    for key in ("recovered", "metric_recovered", "is_recovered"):
        if isinstance(metrics.get(key), bool):
            return 1.0 if metrics[key] else 0.0

    recovery_score = _normalize_score(metrics.get("recovery_score"))
    if recovery_score is not None:
        return recovery_score

    before = metrics.get("before")
    after = metrics.get("after")
    if isinstance(before, (int, float)) and isinstance(after, (int, float)) and before > 0:
        return max(0.0, min(1.0, (before - after) / before))

    return 0.5


def calc_user_feedback(feedback: Dict = None) -> float:
    if not feedback:
        return 0.5
    if feedback.get("accepted") is True:
        return 1.0
    if feedback.get("accepted") is False:
        return 0.0

    feedback_score = _normalize_score(feedback.get("score"))
    if feedback_score is not None:
        return feedback_score
    return 0.5


def calc_recurrence(case: Dict, feedback: Dict = None) -> float:
    if feedback and feedback.get("recurrence") is True:
        return 0.0
    if feedback and feedback.get("recurrence") is False:
        return 1.0
    return 0.5


def calc_efficiency(case: Dict) -> float:
    output = case.get("output_snapshot") or {}
    diagnosis_time = output.get("diagnosis_time", 0)
    try:
        seconds = float(diagnosis_time)
    except (TypeError, ValueError):
        return 0.5

    if seconds <= 0:
        return 0.5
    if seconds <= 30:
        return 1.0
    if seconds <= 120:
        return 0.8
    if seconds <= 300:
        return 0.6
    return 0.3


def calculate_outcome_score(case: Dict, feedback: Dict = None, post_metrics: Dict = None) -> Dict:
    """Calculate case outcome score and label.

    Without feedback or post metrics, V0.1 keeps the case uncertain to avoid
    over-learning from model confidence alone.
    """
    if not feedback and not post_metrics:
        return {"outcome_score": 0.0, "label": "uncertain_case"}

    metric_recovery = post_metrics or (feedback or {}).get("metric_recovery")
    score = (
        0.35 * calc_root_cause_match(case, feedback)
        + 0.25 * calc_metric_recovery(case, metric_recovery)
        + 0.15 * calc_user_feedback(feedback)
        + 0.15 * calc_recurrence(case, feedback)
        + 0.10 * calc_efficiency(case)
    )

    if score >= 0.75:
        label = "positive_case"
    elif score <= 0.45:
        label = "negative_case"
    else:
        label = "uncertain_case"

    return {"outcome_score": round(score, 4), "label": label}
