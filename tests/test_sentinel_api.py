import unittest
import os
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from mini_shop_with_ui.app import app, save_state, get_state, TRIAGE_RUNS, INCIDENT_MEMORY


client = TestClient(app)


class SentinelApiTests(unittest.TestCase):
    def test_dashboard_api_pins_triage_tools_to_live_mini_shop_data(self):
        expected = Path("mini_shop_with_ui/data").resolve()

        self.assertEqual(Path(os.environ["MINISHOP_DATA"]).resolve(), expected)

    def test_incident_contract_maps_live_telemetry(self):
        state = get_state()
        original_mode = state["deploy_mode"]
        try:
            state["deploy_mode"] = "bad"
            save_state(state)

            response = client.get("/api/incident")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["service"], "checkout-api")
            self.assertEqual(payload["workflow"], "checkout")
            self.assertGreaterEqual(
                payload["kpis"].keys(),
                {
                    "payment_success_pct",
                    "failed_transactions",
                    "total_transactions",
                    "revenue_24h",
                    "estimated_impact",
                },
            )
            self.assertEqual(payload["status"], "degraded")
            self.assertIn(
                {"name": "checkout-api", "depth": 2, "state": "bottleneck"},
                payload["dependencies"],
            )
        finally:
            state["deploy_mode"] = original_mode
            save_state(state)

    def test_healthy_incident_marks_all_dependencies_ok(self):
        state = get_state()
        original_mode = state["deploy_mode"]
        try:
            state["deploy_mode"] = "good"
            save_state(state)

            response = client.get("/api/incident")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "healthy")
            self.assertEqual(payload["severity"], "low")
            self.assertEqual(payload["title"], "Checkout workflow operating normally")
            self.assertTrue(all(dep["state"] == "ok" for dep in payload["dependencies"]))
        finally:
            state["deploy_mode"] = original_mode
            save_state(state)

    def test_rca_contract_provides_gated_action(self):
        response = client.get("/api/rca")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["business_impact"])
        self.assertTrue(payload["confidence"])
        self.assertIsInstance(payload["reasoning_signals"], int)
        self.assertTrue(payload["gated_action"])

    def test_reset_and_reload_contracts(self):
        reset_response = client.post("/api/triage/reset")
        reload_response = client.post("/api/telemetry/reload")

        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(reset_response.json()["status"], "reset")
        self.assertEqual(reload_response.status_code, 200)
        self.assertGreaterEqual(reload_response.json()["kpis"]["total_transactions"], 0)

    def test_confirm_rollback_requires_approval_and_restores_good_deploy(self):
        TRIAGE_RUNS.clear()
        INCIDENT_MEMORY.clear()
        state = get_state()
        original_mode = state["deploy_mode"]
        try:
            state["deploy_mode"] = "bad"
            save_state(state)
            TRIAGE_RUNS["test-run"] = {
                "run_id": "test-run",
                "thread_id": "test-thread",
                "created_at": "2026-06-18T00:00:00Z",
                "status": "awaiting_decision",
                "decision_status": None,
                "timeline": [],
            }

            blocked = client.post("/api/triage/confirm-rollback")
            self.assertEqual(blocked.status_code, 409)
            self.assertEqual(get_state()["deploy_mode"], "bad")

            decision = client.post("/api/triage/decision", json={"decision": "approve"})
            confirmed = client.post("/api/triage/confirm-rollback")

            self.assertEqual(decision.status_code, 200)
            self.assertEqual(confirmed.status_code, 200)
            self.assertEqual(confirmed.json()["status"], "rollback_applied")
            self.assertEqual(get_state()["deploy_mode"], "good")
            memory = client.get("/api/incident-memory")
            self.assertEqual(memory.status_code, 200)
            event_types = [record["event_type"] for record in memory.json()["records"]]
            self.assertIn("decision_recorded", event_types)
            self.assertIn("rollback_confirmed", event_types)
        finally:
            state = get_state()
            state["deploy_mode"] = original_mode
            save_state(state)
            TRIAGE_RUNS.clear()
            INCIDENT_MEMORY.clear()

    def test_triage_run_records_memory_entry(self):
        TRIAGE_RUNS.clear()
        INCIDENT_MEMORY.clear()
        try:
            response = client.post("/api/triage/run")

            self.assertEqual(response.status_code, 200)
            memory = client.get("/api/incident-memory")
            records = memory.json()["records"]
            self.assertEqual(records[-1]["event_type"], "triage_created")
            self.assertEqual(records[-1]["run_id"], response.json()["run_id"])
        finally:
            TRIAGE_RUNS.clear()
            INCIDENT_MEMORY.clear()

    def test_triage_stream_emits_timeline_and_evidence_events(self):
        class FakeGraph:
            def stream(self, *_args, **_kwargs):
                yield {
                    "metrics": {
                        "timeline": [("metrics", "12:00:00", "high_checkout_latency")],
                        "evidence_events": [
                            {
                                "agent": "metrics",
                                "type": "tool_result",
                                "summary": "Metrics tool returned high latency.",
                                "raw": {"metric": "checkout.latency", "value": 900},
                            }
                        ],
                    }
                }

        TRIAGE_RUNS.clear()
        try:
            run = client.post("/api/triage/run").json()
            with mock.patch("mini_shop_with_ui.app.build_app", return_value=FakeGraph()):
                response = client.get(f"/api/triage/stream?run_id={run['run_id']}")

            self.assertEqual(response.status_code, 200)
            body = response.text
            self.assertIn('"message": "high_checkout_latency"', body)
            self.assertIn("event: evidence", body)
            self.assertIn('"type": "tool_result"', body)
            self.assertIn('"metric": "checkout.latency"', body)
        finally:
            TRIAGE_RUNS.clear()


if __name__ == "__main__":
    unittest.main()
