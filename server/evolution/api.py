#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FastAPI handlers for the self-evolution module (V0.1 + V0.2)."""
from fastapi import Body

from server.evolution.collector import capture_user_feedback
from server.evolution.schemas import EvolutionFeedbackInput
from server.utils import BaseResponse


def list_evolution_cases(limit: int = 20, offset: int = 0, label: str = None, status: str = None, anomaly_type: str = None):
    try:
        from server.db.repository.evolution_repository import count_evolution_cases, list_evolution_cases as repo_list

        cases = repo_list(limit=limit, offset=offset, label=label, status=status, anomaly_type=anomaly_type)
        total = count_evolution_cases(label=label, status=status, anomaly_type=anomaly_type)
        return BaseResponse(
            code=200,
            msg="Success",
            data={"cases": cases, "total": total, "limit": limit, "offset": offset},
        )
    except Exception as e:
        return BaseResponse(code=500, msg=f"Failed to list evolution cases: {str(e)}")


def get_evolution_case(case_id: int):
    try:
        from server.db.repository.evolution_repository import get_evolution_case_by_id, list_feedback_for_case

        case = get_evolution_case_by_id(case_id=case_id)
        if not case:
            return BaseResponse(code=404, msg="Evolution case not found")
        feedback = list_feedback_for_case(case_id=case_id)
        return BaseResponse(code=200, msg="Success", data={"case": case, "feedback": feedback})
    except Exception as e:
        return BaseResponse(code=500, msg=f"Failed to get evolution case: {str(e)}")


def get_evolution_metrics():
    try:
        from server.db.repository.evolution_repository import get_evolution_metrics as repo_metrics

        return BaseResponse(code=200, msg="Success", data=repo_metrics())
    except Exception as e:
        return BaseResponse(code=500, msg=f"Failed to get evolution metrics: {str(e)}")


def create_evolution_feedback(payload: EvolutionFeedbackInput = Body(...)):
    try:
        feedback_id = capture_user_feedback(
            message_id=payload.message_id,
            score=payload.score,
            reason=payload.reason,
            record_id=payload.record_id,
            case_id=payload.case_id,
            evolution_case_id=payload.evolution_case_id,
            feedback_type=payload.feedback_type,
            accepted=payload.accepted,
            metric_recovery=payload.metric_recovery,
            recurrence=payload.recurrence,
            raw_feedback=payload.raw_feedback,
        )
        return BaseResponse(code=200, msg="Success", data={"feedback_id": feedback_id})
    except Exception as e:
        return BaseResponse(code=500, msg=f"Failed to create evolution feedback: {str(e)}")


# ── V0.2: Pattern + Candidate ─────────────────────────────────────────────────

def list_evolution_patterns(
    limit: int = 20,
    offset: int = 0,
    pattern_type: str = None,
    status: str = None,
):
    try:
        from server.db.repository.evolution_repository import (
            count_evolution_patterns,
            list_evolution_patterns as repo_list,
        )
        patterns = repo_list(limit=limit, offset=offset, pattern_type=pattern_type, status=status)
        total = count_evolution_patterns(pattern_type=pattern_type, status=status)
        return BaseResponse(
            code=200,
            msg="Success",
            data={"patterns": patterns, "total": total, "limit": limit, "offset": offset},
        )
    except Exception as e:
        return BaseResponse(code=500, msg=f"Failed to list evolution patterns: {str(e)}")


def list_evolution_candidates(
    limit: int = 20,
    offset: int = 0,
    candidate_type: str = None,
    status: str = None,
    risk_level: str = None,
):
    try:
        from server.db.repository.evolution_repository import (
            count_evolution_candidates,
            list_evolution_candidates as repo_list,
        )
        candidates = repo_list(
            limit=limit, offset=offset,
            candidate_type=candidate_type, status=status, risk_level=risk_level,
        )
        total = count_evolution_candidates(
            candidate_type=candidate_type, status=status, risk_level=risk_level,
        )
        return BaseResponse(
            code=200,
            msg="Success",
            data={"candidates": candidates, "total": total, "limit": limit, "offset": offset},
        )
    except Exception as e:
        return BaseResponse(code=500, msg=f"Failed to list evolution candidates: {str(e)}")


def generate_evolution_candidates(min_cases: int = 3):
    """Trigger pattern mining followed by candidate generation.

    Mines patterns from recent negative/uncertain cases, then generates a
    candidate patch for each discovered pattern.  All results are persisted
    to the database.
    """
    try:
        from server.evolution.candidate_generator import generate_all_candidates
        from server.evolution.pattern_miner import mine_patterns

        patterns = mine_patterns(min_cases=min_cases, save=True)
        candidates = generate_all_candidates(patterns, save=True)
        return BaseResponse(
            code=200,
            msg="Success",
            data={
                "patterns_found": len(patterns),
                "candidates_generated": len(candidates),
                "patterns": patterns,
                "candidates": candidates,
            },
        )
    except Exception as e:
        return BaseResponse(code=500, msg=f"Failed to generate evolution candidates: {str(e)}")
