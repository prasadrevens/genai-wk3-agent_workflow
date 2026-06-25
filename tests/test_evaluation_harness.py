import json
import tempfile
import unittest
from pathlib import Path

from evaluation.evaluate_incident import (
    EvaluationCase,
    evaluate_case,
    load_cases,
    summarize_results,
)


class EvaluationHarnessTests(unittest.TestCase):
    def test_evaluate_case_scores_expected_incident_fields(self):
        case = EvaluationCase(
            case_id="bad-checkout-deploy",
            name="Bad checkout deployment",
            input_state={"status": "degraded"},
            expected={
                "status": "degraded",
                "root_cause_keywords": ["checkout-api", "deployment"],
                "business_impact_keywords": ["revenue", "failed transactions"],
                "confidence": "High",
                "recommendation_keywords": ["roll back", "checkout-api"],
                "approval_gate_required": True,
            },
        )
        candidate = {
            "status": "degraded",
            "root_cause": "Recent checkout-api deployment is correlated with elevated checkout latency.",
            "business_impact": "Failed transactions increased and revenue is at risk.",
            "confidence": "High",
            "gated_action": "Roll back checkout-api to the last good version.",
            "approval_status": "awaiting human approval",
        }

        result = evaluate_case(case, candidate)

        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.total_checks, 6)
        self.assertEqual(result.passed_checks, 6)

    def test_evaluate_case_reports_failed_checks_without_throwing(self):
        case = EvaluationCase(
            case_id="healthy-checkout",
            name="Healthy checkout",
            input_state={"status": "healthy"},
            expected={
                "status": "healthy",
                "root_cause_keywords": ["normal"],
                "business_impact_keywords": ["within normal range"],
                "confidence": "Low",
                "recommendation_keywords": ["no rollback"],
                "approval_gate_required": False,
            },
        )
        candidate = {
            "status": "degraded",
            "root_cause": "payment-api timeout",
            "business_impact": "Revenue at risk",
            "confidence": "High",
            "gated_action": "Roll back checkout-api",
            "approval_status": "awaiting human approval",
        }

        result = evaluate_case(case, candidate)

        self.assertFalse(result.passed)
        self.assertLess(result.score, 1.0)
        failed_names = [check.name for check in result.checks if not check.passed]
        self.assertIn("status", failed_names)
        self.assertIn("approval_gate_required", failed_names)

    def test_no_approval_required_is_not_treated_as_gate(self):
        case = EvaluationCase(
            case_id="healthy-checkout",
            name="Healthy checkout",
            input_state={"status": "healthy"},
            expected={"approval_gate_required": False},
        )
        candidate = {
            "gated_action": "No rollback recommended.",
            "approval_status": "no approval required",
        }

        result = evaluate_case(case, candidate)

        self.assertTrue(result.passed)

    def test_load_cases_accepts_json_file(self):
        payload = [
            {
                "case_id": "case-1",
                "name": "Example",
                "input_state": {"status": "degraded"},
                "expected": {"status": "degraded"},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            cases = load_cases(path)

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].case_id, "case-1")
        self.assertEqual(cases[0].expected["status"], "degraded")

    def test_summarize_results_counts_passes_and_average_score(self):
        case = EvaluationCase("case-1", "Example", {}, {"status": "healthy"})
        passing = evaluate_case(case, {"status": "healthy"})
        failing = evaluate_case(case, {"status": "degraded"})

        summary = summarize_results([passing, failing])

        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["passed_cases"], 1)
        self.assertEqual(summary["failed_cases"], 1)
        self.assertEqual(summary["average_score"], 0.5)


if __name__ == "__main__":
    unittest.main()
