"""Unit tests for server.evolution.pattern_miner (V0.2)."""
from unittest.mock import patch

from server.evolution.pattern_miner import (
    _mine_low_confidence_prompt,
    _mine_missing_knowledge,
    _mine_retrieval_weight_issue,
    _mine_wrong_tool_selection,
    mine_patterns,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _case(
    case_id: int = 1,
    anomaly_type: str = "CPU_High",
    knowledge_used: int = 0,
    tools: list = None,
    confidence: float = 0.4,
    label: str = "negative_case",
) -> dict:
    return {
        "id": case_id,
        "anomaly_type": anomaly_type,
        "label": label,
        "outcome_score": 0.3,
        "knowledge_snapshot": {"knowledge_chunks_used": knowledge_used},
        "trace_snapshot": {
            "reasoning_steps": [{"action": t} for t in (tools or [])]
        },
        "output_snapshot": {
            "root_causes": [{"type": "cpu_spike", "confidence": confidence}],
            "diagnosis_time": 30,
        },
    }


# ── missing_knowledge ─────────────────────────────────────────────────────────

def test_missing_knowledge_detected_above_min():
    cases = [_case(case_id=i, knowledge_used=0) for i in range(1, 5)]
    patterns = _mine_missing_knowledge(cases, min_cases=3)
    assert len(patterns) == 1
    p = patterns[0]
    assert p["pattern_type"] == "missing_knowledge"
    assert p["cluster_key"] == "CPU_High"
    assert len(p["evidence_case_ids"]) == 4
    assert p["suggested_update_type"] == "knowledge_patch"
    assert 0.0 < p["confidence"] <= 1.0


def test_missing_knowledge_not_detected_below_min():
    cases = [_case(case_id=i, knowledge_used=0) for i in range(1, 3)]
    assert _mine_missing_knowledge(cases, min_cases=3) == []


def test_missing_knowledge_ignores_cases_with_knowledge():
    no_knowledge = [_case(case_id=i, knowledge_used=0) for i in range(1, 4)]
    with_knowledge = [_case(case_id=i, knowledge_used=2) for i in range(4, 7)]
    patterns = _mine_missing_knowledge(no_knowledge + with_knowledge, min_cases=3)
    assert len(patterns) == 1
    assert len(patterns[0]["evidence_case_ids"]) == 3


def test_missing_knowledge_caps_evidence_at_20():
    cases = [_case(case_id=i, knowledge_used=0) for i in range(1, 30)]
    patterns = _mine_missing_knowledge(cases, min_cases=3)
    assert len(patterns[0]["evidence_case_ids"]) == 20


# ── wrong_tool_selection ──────────────────────────────────────────────────────

def test_wrong_tool_detected_for_slow_query_no_tools():
    cases = [_case(case_id=i, anomaly_type="SlowQueryDetected", tools=[]) for i in range(1, 5)]
    patterns = _mine_wrong_tool_selection(cases, min_cases=3)
    assert len(patterns) == 1
    assert patterns[0]["pattern_type"] == "wrong_tool_selection"
    assert patterns[0]["suggested_update_type"] == "tool_strategy_patch"


def test_wrong_tool_not_detected_if_explain_query_used():
    cases = [
        _case(case_id=i, anomaly_type="SlowQueryDetected", tools=["explain_query"])
        for i in range(1, 5)
    ]
    assert _mine_wrong_tool_selection(cases, min_cases=3) == []


def test_wrong_tool_not_detected_below_min():
    cases = [_case(case_id=i, anomaly_type="SlowQuery", tools=[]) for i in range(1, 3)]
    assert _mine_wrong_tool_selection(cases, min_cases=3) == []


def test_wrong_tool_ignores_non_slow_query_cases():
    cases = [_case(case_id=i, anomaly_type="MemoryLeak", tools=[]) for i in range(1, 5)]
    assert _mine_wrong_tool_selection(cases, min_cases=3) == []


# ── low_confidence_prompt ─────────────────────────────────────────────────────

def test_low_confidence_detected_with_tools():
    cases = [
        _case(case_id=i, anomaly_type="LockWait", tools=["check_locks"], confidence=0.3)
        for i in range(1, 5)
    ]
    patterns = _mine_low_confidence_prompt(cases, min_cases=3)
    assert len(patterns) == 1
    p = patterns[0]
    assert p["pattern_type"] == "low_confidence_prompt"
    assert "LockWait" in p["cluster_key"]
    assert p["suggested_update_type"] == "prompt_patch"


def test_low_confidence_not_detected_without_tools():
    cases = [
        _case(case_id=i, anomaly_type="LockWait", tools=[], confidence=0.3)
        for i in range(1, 5)
    ]
    assert _mine_low_confidence_prompt(cases, min_cases=3) == []


def test_low_confidence_not_detected_if_confidence_high():
    cases = [
        _case(case_id=i, anomaly_type="LockWait", tools=["check_locks"], confidence=0.9)
        for i in range(1, 5)
    ]
    assert _mine_low_confidence_prompt(cases, min_cases=3) == []


# ── retrieval_weight_issue ────────────────────────────────────────────────────

def _case_with_retrieval(case_id: int, bm25: float, vec: float) -> dict:
    c = _case(case_id=case_id)
    c["knowledge_snapshot"] = {
        "knowledge_chunks_used": 2,
        "retrieved_knowledge": [{"bm25_score": bm25, "vector_score": vec}],
    }
    return c


def test_retrieval_weight_detected_when_imbalanced():
    cases = [_case_with_retrieval(i, bm25=0.8, vec=0.3) for i in range(1, 5)]
    patterns = _mine_retrieval_weight_issue(cases, min_cases=3)
    assert len(patterns) == 1
    assert patterns[0]["pattern_type"] == "retrieval_weight_issue"
    assert patterns[0]["suggested_update_type"] == "retrieval_strategy_patch"


def test_retrieval_weight_not_detected_when_balanced():
    cases = [_case_with_retrieval(i, bm25=0.6, vec=0.55) for i in range(1, 5)]
    assert _mine_retrieval_weight_issue(cases, min_cases=3) == []


def test_retrieval_weight_not_detected_without_score_data():
    cases = [_case(case_id=i) for i in range(1, 5)]
    assert _mine_retrieval_weight_issue(cases, min_cases=3) == []


# ── mine_patterns (integration) ───────────────────────────────────────────────

def test_mine_patterns_returns_empty_when_no_cases():
    with patch("server.evolution.pattern_miner._get_cases_for_mining", return_value=[]):
        result = mine_patterns(min_cases=3, save=False)
    assert result == []


def test_mine_patterns_returns_empty_on_db_error():
    with patch(
        "server.evolution.pattern_miner._get_cases_for_mining",
        side_effect=RuntimeError("db down"),
    ):
        result = mine_patterns(min_cases=3, save=False)
    assert result == []


def test_mine_patterns_persists_when_save_true():
    cases = [_case(case_id=i, knowledge_used=0) for i in range(1, 5)]
    with patch("server.evolution.pattern_miner._get_cases_for_mining", return_value=cases):
        with patch(
            "server.db.repository.evolution_repository.create_evolution_pattern",
            return_value=42,
        ) as mock_save:
            patterns = mine_patterns(min_cases=3, save=True)

    assert len(patterns) == 1
    mock_save.assert_called_once()
    assert patterns[0]["id"] == 42


def test_mine_patterns_no_persist_when_save_false():
    cases = [_case(case_id=i, knowledge_used=0) for i in range(1, 5)]
    with patch("server.evolution.pattern_miner._get_cases_for_mining", return_value=cases):
        with patch(
            "server.db.repository.evolution_repository.create_evolution_pattern"
        ) as mock_save:
            patterns = mine_patterns(min_cases=3, save=False)

    assert len(patterns) == 1
    mock_save.assert_not_called()
    assert "id" not in patterns[0]
