#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Repository helpers for the self-evolution module (V0.1 + V0.2)."""
from typing import Dict, List, Optional

from sqlalchemy import func, or_

from server.db.models.evolution_model import (
    EvolutionCandidate,
    EvolutionCase,
    EvolutionFeedback,
    EvolutionPattern,
)
from server.db.session import with_session


@with_session
def create_evolution_case(session, payload: Dict) -> Optional[int]:
    case = EvolutionCase(**payload)
    session.add(case)
    session.flush()
    return case.id


@with_session
def get_evolution_case_by_id(session, case_id: int) -> Optional[Dict]:
    case = session.query(EvolutionCase).filter_by(id=case_id).first()
    return case.to_dict() if case else None


@with_session
def get_evolution_case_by_record_id(session, record_id: int) -> Optional[Dict]:
    case = (
        session.query(EvolutionCase)
        .filter_by(record_id=record_id)
        .order_by(EvolutionCase.create_time.desc())
        .first()
    )
    return case.to_dict() if case else None


@with_session
def list_evolution_cases(
    session,
    limit: int = 20,
    offset: int = 0,
    label: str = None,
    status: str = None,
    anomaly_type: str = None,
) -> List[Dict]:
    query = session.query(EvolutionCase)
    if label:
        query = query.filter_by(label=label)
    if status:
        query = query.filter_by(status=status)
    if anomaly_type:
        query = query.filter_by(anomaly_type=anomaly_type)

    rows = query.order_by(EvolutionCase.create_time.desc()).offset(offset).limit(limit).all()
    return [row.to_dict() for row in rows]


@with_session
def count_evolution_cases(session, label: str = None, status: str = None, anomaly_type: str = None) -> int:
    query = session.query(EvolutionCase)
    if label:
        query = query.filter_by(label=label)
    if status:
        query = query.filter_by(status=status)
    if anomaly_type:
        query = query.filter_by(anomaly_type=anomaly_type)
    return query.count()


@with_session
def create_evolution_feedback(session, payload: Dict) -> Optional[int]:
    feedback = EvolutionFeedback(**payload)
    session.add(feedback)
    session.flush()
    return feedback.id


@with_session
def list_feedback_for_case(session, case_id: int) -> List[Dict]:
    rows = (
        session.query(EvolutionFeedback)
        .filter_by(case_id=case_id)
        .order_by(EvolutionFeedback.create_time.desc())
        .all()
    )
    return [row.to_dict() for row in rows]


@with_session
def update_evolution_case_score(session, case_id: int, outcome_score: float, label: str) -> bool:
    case = session.query(EvolutionCase).filter_by(id=case_id).first()
    if not case:
        return False

    case.outcome_score = outcome_score
    case.label = label
    case.status = "evaluated"
    session.add(case)
    return True


@with_session
def list_evolution_cases_for_mining(session, limit: int = 500) -> List[Dict]:
    """Return non-positive cases for pattern mining analysis."""
    rows = (
        session.query(EvolutionCase)
        .filter(
            or_(
                EvolutionCase.label == "negative_case",
                EvolutionCase.label == "uncertain_case",
            )
        )
        .order_by(EvolutionCase.create_time.desc())
        .limit(limit)
        .all()
    )
    return [row.to_dict() for row in rows]


# ── V0.2 Pattern ──────────────────────────────────────────────────────────────

@with_session
def create_evolution_pattern(session, payload: Dict) -> Optional[int]:
    pattern = EvolutionPattern(**payload)
    session.add(pattern)
    session.flush()
    return pattern.id


@with_session
def get_evolution_pattern_by_id(session, pattern_id: int) -> Optional[Dict]:
    pattern = session.query(EvolutionPattern).filter_by(id=pattern_id).first()
    return pattern.to_dict() if pattern else None


@with_session
def list_evolution_patterns(
    session,
    limit: int = 20,
    offset: int = 0,
    pattern_type: str = None,
    status: str = None,
) -> List[Dict]:
    query = session.query(EvolutionPattern)
    if pattern_type:
        query = query.filter_by(pattern_type=pattern_type)
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by(EvolutionPattern.create_time.desc()).offset(offset).limit(limit).all()
    return [row.to_dict() for row in rows]


@with_session
def count_evolution_patterns(session, pattern_type: str = None, status: str = None) -> int:
    query = session.query(EvolutionPattern)
    if pattern_type:
        query = query.filter_by(pattern_type=pattern_type)
    if status:
        query = query.filter_by(status=status)
    return query.count()


# ── V0.2 Candidate ────────────────────────────────────────────────────────────

@with_session
def create_evolution_candidate(session, payload: Dict) -> Optional[int]:
    candidate = EvolutionCandidate(**payload)
    session.add(candidate)
    session.flush()
    return candidate.id


@with_session
def get_evolution_candidate_by_id(session, candidate_id: int) -> Optional[Dict]:
    candidate = session.query(EvolutionCandidate).filter_by(id=candidate_id).first()
    return candidate.to_dict() if candidate else None


@with_session
def list_evolution_candidates(
    session,
    limit: int = 20,
    offset: int = 0,
    candidate_type: str = None,
    status: str = None,
    risk_level: str = None,
) -> List[Dict]:
    query = session.query(EvolutionCandidate)
    if candidate_type:
        query = query.filter_by(candidate_type=candidate_type)
    if status:
        query = query.filter_by(status=status)
    if risk_level:
        query = query.filter_by(risk_level=risk_level)
    rows = query.order_by(EvolutionCandidate.create_time.desc()).offset(offset).limit(limit).all()
    return [row.to_dict() for row in rows]


@with_session
def count_evolution_candidates(
    session,
    candidate_type: str = None,
    status: str = None,
    risk_level: str = None,
) -> int:
    query = session.query(EvolutionCandidate)
    if candidate_type:
        query = query.filter_by(candidate_type=candidate_type)
    if status:
        query = query.filter_by(status=status)
    if risk_level:
        query = query.filter_by(risk_level=risk_level)
    return query.count()


# ── Metrics (V0.1) ────────────────────────────────────────────────────────────

@with_session
def get_evolution_metrics(session) -> Dict:
    total_cases = session.query(EvolutionCase).count()
    total_feedback = session.query(EvolutionFeedback).count()
    total_patterns = session.query(EvolutionPattern).count()
    total_candidates = session.query(EvolutionCandidate).count()

    label_rows = session.query(EvolutionCase.label, func.count(EvolutionCase.id)).group_by(EvolutionCase.label).all()
    status_rows = session.query(EvolutionCase.status, func.count(EvolutionCase.id)).group_by(EvolutionCase.status).all()
    candidate_status_rows = (
        session.query(EvolutionCandidate.status, func.count(EvolutionCandidate.id))
        .group_by(EvolutionCandidate.status)
        .all()
    )

    avg_score = session.query(func.avg(EvolutionCase.outcome_score)).scalar()

    return {
        "total_cases": total_cases,
        "total_feedback": total_feedback,
        "total_patterns": total_patterns,
        "total_candidates": total_candidates,
        "avg_outcome_score": round(float(avg_score or 0.0), 4),
        "labels": {label or "unknown": count for label, count in label_rows},
        "statuses": {status or "unknown": count for status, count in status_rows},
        "candidate_statuses": {s or "unknown": c for s, c in candidate_status_rows},
    }
