#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Repository helpers for the self-evolution V0.1 module."""
from typing import Dict, List, Optional

from sqlalchemy import func

from server.db.models.evolution_model import EvolutionCase, EvolutionFeedback
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
def get_evolution_metrics(session) -> Dict:
    total_cases = session.query(EvolutionCase).count()
    total_feedback = session.query(EvolutionFeedback).count()

    label_rows = session.query(EvolutionCase.label, func.count(EvolutionCase.id)).group_by(EvolutionCase.label).all()
    status_rows = session.query(EvolutionCase.status, func.count(EvolutionCase.id)).group_by(EvolutionCase.status).all()

    avg_score = session.query(func.avg(EvolutionCase.outcome_score)).scalar()

    return {
        "total_cases": total_cases,
        "total_feedback": total_feedback,
        "avg_outcome_score": round(float(avg_score or 0.0), 4),
        "labels": {label or "unknown": count for label, count in label_rows},
        "statuses": {status or "unknown": count for status, count in status_rows},
    }
