from unittest.mock import AsyncMock, patch


class TestEvolutionApi:
    def test_list_cases_returns_base_response(self, client):
        with patch("server.db.repository.evolution_repository.list_evolution_cases", return_value=[{"id": 1}]):
            with patch("server.db.repository.evolution_repository.count_evolution_cases", return_value=1):
                resp = client.get("/evolution/cases")

        if resp.status_code == 404:
            raise AssertionError("Evolution routes are not mounted")
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 1
        assert data["data"]["cases"] == [{"id": 1}]

    def test_metrics_returns_base_response(self, client):
        metrics = {"total_cases": 2, "total_feedback": 1, "avg_outcome_score": 0.5}
        with patch("server.db.repository.evolution_repository.get_evolution_metrics", return_value=metrics):
            resp = client.get("/evolution/metrics")

        data = resp.json()
        assert data["code"] == 200
        assert data["data"] == metrics

    def test_create_feedback_returns_feedback_id(self, client):
        with patch("server.evolution.api.capture_user_feedback", return_value=33) as mock_capture:
            resp = client.post(
                "/evolution/feedback",
                json={
                    "record_id": 10,
                    "evolution_case_id": 20,
                    "score": 95,
                    "reason": "useful",
                    "accepted": True,
                    "metric_recovery": {"recovered": True},
                    "recurrence": False,
                },
            )

        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["feedback_id"] == 33
        assert mock_capture.call_args.kwargs["evolution_case_id"] == 20
        assert mock_capture.call_args.kwargs["score"] == 95

    def test_get_case_includes_feedback(self, client):
        with patch("server.db.repository.evolution_repository.get_evolution_case_by_id", return_value={"id": 3}):
            with patch("server.db.repository.evolution_repository.list_feedback_for_case", return_value=[{"id": 8}]):
                resp = client.get("/evolution/cases/3")

        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["case"] == {"id": 3}
        assert data["data"]["feedback"] == [{"id": 8}]


class TestEvolutionDiagnosisIntegration:
    def test_quick_diagnose_appends_evolution_case_id(self, client):
        mock_result = {
            "root_causes": [{"type": "missing_index", "confidence": 0.9}],
            "solutions": [{"action": "CREATE INDEX"}],
            "reasoning_steps": [{"action": "get_query_plan"}],
            "search_stats": {"knowledge_matches": 1},
            "diagnosis_time": 5,
            "confidence": 0.9,
        }

        with patch("server.diagnose.diagnose.check_auto_task_running", return_value={"auto_running": False}):
            with patch("server.diagnose.diagnose.can_start_task", return_value={"can_start": True, "reason": ""}):
                with patch("server.diagnose.diagnose.check_cancel_requested", return_value=False):
                    with patch("server.diagnose.diagnose.set_task_running"):
                        with patch("server.diagnose.diagnose.register_async_task"):
                            with patch("server.diagnose.diagnose.unregister_async_task"):
                                with patch("server.diagnose.diagnose.run_tree_search_diagnosis", new=AsyncMock(return_value=mock_result)):
                                    with patch("server.diagnose.diagnose._save_diagnosis_to_database", return_value=101):
                                        with patch("server.evolution.collector.capture_diagnosis_result", return_value=202):
                                            resp = client.post(
                                                "/diagnose/quick",
                                                json={
                                                    "alert_type": "SlowQueryDetected",
                                                    "description": "query timeout",
                                                    "severity": "high",
                                                },
                                            )

        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["record_id"] == 101
        assert data["data"]["evolution_case_id"] == 202
