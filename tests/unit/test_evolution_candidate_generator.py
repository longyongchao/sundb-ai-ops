"""Unit tests for server.evolution.candidate_generator (V0.2)."""
from unittest.mock import patch

from server.evolution.candidate_generator import (
    generate_all_candidates,
    generate_candidates_from_pattern,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _pattern(
    pattern_type: str,
    cluster_key: str = "test_cluster",
    evidence_ids: list = None,
    pattern_id: int = 1,
) -> dict:
    return {
        "id": pattern_id,
        "pattern_type": pattern_type,
        "cluster_key": cluster_key,
        "evidence_case_ids": evidence_ids or [1, 2, 3],
        "failure_signature": f"测试失败特征：{pattern_type}",
        "suggested_update_type": "test_patch",
        "confidence": 0.7,
    }


_NO_CASES = patch(
    "server.evolution.candidate_generator._fetch_evidence_cases",
    return_value=[],
)
_SAVE_OK = patch(
    "server.db.repository.evolution_repository.create_evolution_candidate",
    return_value=99,
)


# ── knowledge_patch ───────────────────────────────────────────────────────────

def test_knowledge_patch_generated():
    with _NO_CASES, _SAVE_OK:
        candidates = generate_candidates_from_pattern(
            _pattern("missing_knowledge", cluster_key="CPU_High"), save=True
        )
    assert len(candidates) == 1
    c = candidates[0]
    assert c["candidate_type"] == "knowledge_patch"
    assert c["target_artifact_type"] == "knowledge"
    assert c["risk_level"] == "low"
    assert c["status"] == "pending"
    assert "CPU_High" in c["patch_content"]["knowledge_block"]["anomaly_type"]
    assert c["id"] == 99


def test_knowledge_patch_includes_root_cause_types():
    evidence_cases = [
        {
            "id": 1,
            "output_snapshot": {
                "root_causes": [{"type": "missing_index"}, {"type": "seq_scan"}]
            },
        }
    ]
    with patch(
        "server.evolution.candidate_generator._fetch_evidence_cases",
        return_value=evidence_cases,
    ):
        with _SAVE_OK:
            candidates = generate_candidates_from_pattern(
                _pattern("missing_knowledge"), save=True
            )
    block = candidates[0]["patch_content"]["knowledge_block"]
    assert "missing_index" in block["evidence_root_causes"]
    assert "seq_scan" in block["evidence_root_causes"]


# ── tool_strategy_patch ───────────────────────────────────────────────────────

def test_tool_strategy_patch_generated():
    with _NO_CASES, _SAVE_OK:
        candidates = generate_candidates_from_pattern(
            _pattern("wrong_tool_selection"), save=True
        )
    assert len(candidates) == 1
    c = candidates[0]
    assert c["candidate_type"] == "tool_strategy_patch"
    assert c["target_artifact_type"] == "tool_policy"
    assert c["risk_level"] == "medium"
    assert "explain_query" in c["patch_content"]["rule"]["required_tools"]


# ── prompt_patch ──────────────────────────────────────────────────────────────

def test_prompt_patch_generated():
    with _NO_CASES, _SAVE_OK:
        candidates = generate_candidates_from_pattern(
            _pattern("low_confidence_prompt", cluster_key="low_conf_LockWait"), save=True
        )
    assert len(candidates) == 1
    c = candidates[0]
    assert c["candidate_type"] == "prompt_patch"
    assert c["target_artifact_type"] == "prompt"
    assert c["risk_level"] == "medium"
    assert "LockWait" in c["patch_content"]["instruction"]["anomaly_type"]


# ── retrieval_strategy_patch ──────────────────────────────────────────────────

def test_retrieval_strategy_patch_generated():
    with _NO_CASES, _SAVE_OK:
        candidates = generate_candidates_from_pattern(
            _pattern("retrieval_weight_issue"), save=True
        )
    assert len(candidates) == 1
    c = candidates[0]
    assert c["candidate_type"] == "retrieval_strategy_patch"
    assert c["target_artifact_type"] == "retrieval_policy"
    assert c["risk_level"] == "low"
    adj = c["patch_content"]["adjustment"]
    assert adj["suggested_bm25_weight"] + adj["suggested_vector_weight"] == 1.0


# ── unknown pattern type ──────────────────────────────────────────────────────

def test_unknown_pattern_type_returns_empty():
    candidates = generate_candidates_from_pattern(
        _pattern("totally_unknown_type"), save=False
    )
    assert candidates == []


# ── save=False skips DB ───────────────────────────────────────────────────────

def test_no_db_write_when_save_false():
    with _NO_CASES:
        with patch(
            "server.db.repository.evolution_repository.create_evolution_candidate"
        ) as mock_save:
            candidates = generate_candidates_from_pattern(
                _pattern("missing_knowledge"), save=False
            )
    assert len(candidates) == 1
    mock_save.assert_not_called()
    assert "id" not in candidates[0]


# ── generate_all_candidates ───────────────────────────────────────────────────

def test_generate_all_candidates_covers_multiple_patterns():
    patterns = [
        _pattern("missing_knowledge", pattern_id=1),
        _pattern("wrong_tool_selection", pattern_id=2),
        _pattern("low_confidence_prompt", cluster_key="low_conf_X", pattern_id=3),
        _pattern("retrieval_weight_issue", pattern_id=4),
    ]
    with _NO_CASES:
        with patch(
            "server.db.repository.evolution_repository.create_evolution_candidate",
            side_effect=[10, 11, 12, 13],
        ):
            candidates = generate_all_candidates(patterns, save=True)

    assert len(candidates) == 4
    types = {c["candidate_type"] for c in candidates}
    assert types == {
        "knowledge_patch",
        "tool_strategy_patch",
        "prompt_patch",
        "retrieval_strategy_patch",
    }


def test_generate_all_candidates_empty_input():
    assert generate_all_candidates([], save=False) == []


def test_generate_all_candidates_skips_unknown_pattern_type():
    patterns = [
        _pattern("missing_knowledge", pattern_id=1),
        _pattern("unknown_type", pattern_id=2),
    ]
    with _NO_CASES:
        with patch(
            "server.db.repository.evolution_repository.create_evolution_candidate",
            return_value=5,
        ):
            candidates = generate_all_candidates(patterns, save=True)
    assert len(candidates) == 1
    assert candidates[0]["candidate_type"] == "knowledge_patch"
