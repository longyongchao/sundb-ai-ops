from server.evolution.evaluator import calculate_outcome_score


def test_no_feedback_keeps_case_uncertain():
    case = {
        "output_snapshot": {
            "root_causes": [{"type": "missing_index", "confidence": 0.95}],
            "diagnosis_time": 10,
        }
    }

    result = calculate_outcome_score(case)

    assert result == {"outcome_score": 0.0, "label": "uncertain_case"}


def test_high_quality_feedback_becomes_positive_case():
    case = {
        "output_snapshot": {
            "root_causes": [{"type": "missing_index", "confidence": 0.9}],
            "diagnosis_time": 20,
        }
    }
    feedback = {
        "score": 100,
        "accepted": True,
        "metric_recovery": {"recovered": True},
        "recurrence": False,
    }

    result = calculate_outcome_score(case, feedback=feedback)

    assert result["label"] == "positive_case"
    assert result["outcome_score"] >= 0.75


def test_low_quality_feedback_becomes_negative_case():
    case = {"output_snapshot": {"root_causes": [], "diagnosis_time": 600}}
    feedback = {
        "score": 0,
        "accepted": False,
        "metric_recovery": {"recovered": False},
        "recurrence": True,
    }

    result = calculate_outcome_score(case, feedback=feedback)

    assert result["label"] == "negative_case"
    assert result["outcome_score"] <= 0.45


def test_metric_recovery_score_accepts_numeric_improvement():
    case = {
        "output_snapshot": {
            "root_causes": [{"type": "cpu", "confidence": 0.8}],
            "diagnosis_time": 60,
        }
    }
    feedback = {"score": 80, "metric_recovery": {"before": 100, "after": 20}, "recurrence": False}

    result = calculate_outcome_score(case, feedback=feedback)

    assert result["outcome_score"] > 0.7
