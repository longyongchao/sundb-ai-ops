from unittest.mock import patch

from server.evolution.collector import (
    build_case_fingerprint,
    capture_diagnosis_result,
    sanitize_snapshot,
)


def test_sanitize_snapshot_redacts_sensitive_and_truncates():
    raw = {
        "user": "admin",
        "password": "secret",
        "nested": {"api_key": "abc", "value": "x" * 5000},
    }

    cleaned = sanitize_snapshot(raw)

    assert cleaned["password"] == "***REDACTED***"
    assert cleaned["nested"]["api_key"] == "***REDACTED***"
    assert cleaned["nested"]["value"].startswith("x" * 100)
    assert "<truncated:" in cleaned["nested"]["value"]


def test_build_case_fingerprint_is_stable():
    anomaly = {"alert_type": "SlowQueryDetected", "description": "slow query"}
    result = {"root_causes": [{"type": "missing_index", "description": "no index"}]}

    assert build_case_fingerprint(anomaly, result) == build_case_fingerprint(anomaly, result)


def test_capture_diagnosis_result_extracts_core_snapshots():
    anomaly = {
        "diagnosis_id": "diag_1",
        "alert_type": "SlowQueryDetected",
        "description": "query timeout",
        "password": "should_hide",
    }
    result = {
        "record_id": 7,
        "reasoning_steps": [{"thought": "check plan", "action": "get_query_plan", "observation": "seq scan"}],
        "search_stats": {"knowledge_matches": 2, "max_depth": 3},
        "retrieved_knowledge": [{"cause_name": "missing_index"}],
        "tool_match_scores": [{"action": "get_query_plan", "sentence_bert_score": 0.91}],
        "root_causes": [{"type": "missing_index", "confidence": 0.9}],
        "solutions": [{"action": "CREATE INDEX"}],
        "confidence": 0.88,
        "diagnosis_time": 12.5,
    }

    with patch("server.evolution.collector._create_evolution_case", return_value=123) as mock_create:
        case_id = capture_diagnosis_result(anomaly, result, record_id=7)

    assert case_id == 123
    payload = mock_create.call_args.args[0]
    assert payload["record_id"] == 7
    assert payload["diagnosis_id"] == "diag_1"
    assert payload["input_snapshot"]["password"] == "***REDACTED***"
    assert payload["trace_snapshot"]["reasoning_steps"][0]["action"] == "get_query_plan"
    assert payload["knowledge_snapshot"]["knowledge_chunks_used"] == 2
    assert payload["output_snapshot"]["root_causes"][0]["type"] == "missing_index"
    assert payload["label"] == "uncertain_case"


def test_capture_diagnosis_result_tolerates_unserializable_values():
    class OddObject:
        def __str__(self):
            return "odd-object"

    with patch("server.evolution.collector._create_evolution_case", return_value=9) as mock_create:
        case_id = capture_diagnosis_result(
            {"alert_type": "CPU", "description": OddObject()},
            {"root_causes": [], "reasoning_steps": [OddObject()]},
            record_id=1,
        )

    assert case_id == 9
    payload = mock_create.call_args.args[0]
    assert payload["input_snapshot"]["description"] == "odd-object"
    assert payload["trace_snapshot"]["reasoning_steps"] == ["odd-object"]
