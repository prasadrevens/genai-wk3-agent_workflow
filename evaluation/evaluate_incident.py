from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    name: str
    input_state: Dict[str, Any]
    expected: Dict[str, Any]
    candidate: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationCheck:
    name: str
    passed: bool
    expected: Any
    actual: Any
    message: str


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    name: str
    passed: bool
    score: float
    passed_checks: int
    total_checks: int
    checks: List[EvaluationCheck]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "passed": self.passed,
            "score": self.score,
            "passed_checks": self.passed_checks,
            "total_checks": self.total_checks,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "expected": check.expected,
                    "actual": check.actual,
                    "message": check.message,
                }
                for check in self.checks
            ],
        }


DEFAULT_CASES_PATH = Path(__file__).with_name("replay_cases.json")


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> List[EvaluationCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Evaluation cases file must contain a JSON list")
    return [
        EvaluationCase(
            case_id=str(item["case_id"]),
            name=str(item.get("name") or item["case_id"]),
            input_state=dict(item.get("input_state") or {}),
            expected=dict(item.get("expected") or {}),
            candidate=dict(item.get("candidate") or {}),
        )
        for item in raw
    ]


def evaluate_case(case: EvaluationCase, candidate: Mapping[str, Any]) -> EvaluationResult:
    expected = case.expected
    checks: List[EvaluationCheck] = []

    if "status" in expected:
        checks.append(_equals_check("status", expected["status"], candidate.get("status")))
    if "confidence" in expected:
        checks.append(_equals_check("confidence", expected["confidence"], candidate.get("confidence")))
    if "root_cause_keywords" in expected:
        checks.append(_keyword_check("root_cause_keywords", expected["root_cause_keywords"], candidate.get("root_cause")))
    if "business_impact_keywords" in expected:
        checks.append(
            _keyword_check("business_impact_keywords", expected["business_impact_keywords"], candidate.get("business_impact"))
        )
    if "recommendation_keywords" in expected:
        checks.append(_keyword_check("recommendation_keywords", expected["recommendation_keywords"], candidate.get("gated_action")))
    if "approval_gate_required" in expected:
        checks.append(_approval_gate_check(bool(expected["approval_gate_required"]), candidate))

    passed_checks = sum(1 for check in checks if check.passed)
    total_checks = len(checks)
    score = round(passed_checks / total_checks, 3) if total_checks else 0.0
    return EvaluationResult(
        case_id=case.case_id,
        name=case.name,
        passed=total_checks > 0 and passed_checks == total_checks,
        score=score,
        passed_checks=passed_checks,
        total_checks=total_checks,
        checks=checks,
    )


def summarize_results(results: Sequence[EvaluationResult]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    average = round(sum(result.score for result in results) / total, 3) if total else 0.0
    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "average_score": average,
    }


def evaluate_cases(cases: Iterable[EvaluationCase], candidates: Mapping[str, Mapping[str, Any]] | None = None) -> List[EvaluationResult]:
    candidate_map = candidates or {}
    results = []
    for case in cases:
        candidate = candidate_map.get(case.case_id) or case.candidate
        results.append(evaluate_case(case, candidate))
    return results


def load_candidate_map(path: str | Path) -> Dict[str, Dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and all(isinstance(value, dict) for value in raw.values()):
        return {str(key): dict(value) for key, value in raw.items()}
    if isinstance(raw, list):
        return {str(item["case_id"]): dict(item.get("candidate") or item) for item in raw}
    raise ValueError("Candidate file must contain a case-id map or a JSON list")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate ImpactIQ incident replay cases.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH), help="Path to replay_cases.json")
    parser.add_argument("--candidates", help="Optional JSON file with candidate RCA outputs by case_id")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    candidate_map = load_candidate_map(args.candidates) if args.candidates else None
    results = evaluate_cases(cases, candidate_map)
    summary = summarize_results(results)

    if args.json:
        print(json.dumps({"summary": summary, "results": [result.to_dict() for result in results]}, indent=2))
    else:
        print(f"ImpactIQ evaluation: {summary['passed_cases']}/{summary['total_cases']} cases passed")
        print(f"Average score: {summary['average_score']}")
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            print(f"- {status} {result.case_id}: {result.passed_checks}/{result.total_checks} checks, score={result.score}")
            for check in result.checks:
                if not check.passed:
                    print(f"  - {check.name}: {check.message}")

    return 0 if summary["failed_cases"] == 0 else 1


def _equals_check(name: str, expected: Any, actual: Any) -> EvaluationCheck:
    passed = _normalize_text(expected) == _normalize_text(actual)
    return EvaluationCheck(
        name=name,
        passed=passed,
        expected=expected,
        actual=actual,
        message="matched" if passed else f"expected {expected!r}, got {actual!r}",
    )


def _keyword_check(name: str, expected_keywords: Any, actual_text: Any) -> EvaluationCheck:
    keywords = [str(keyword) for keyword in _as_list(expected_keywords)]
    text = _normalize_text(actual_text)
    missing = [keyword for keyword in keywords if _normalize_text(keyword) not in text]
    passed = not missing
    return EvaluationCheck(
        name=name,
        passed=passed,
        expected=keywords,
        actual=actual_text,
        message="all keywords present" if passed else f"missing keyword(s): {', '.join(missing)}",
    )


def _approval_gate_check(expected_required: bool, candidate: Mapping[str, Any]) -> EvaluationCheck:
    status = _normalize_text(candidate.get("approval_status"))
    gated_action = _normalize_text(candidate.get("gated_action"))
    non_gated = any(
        phrase in f"{status} {gated_action}"
        for phrase in ("no approval required", "approval not required", "no rollback", "no gated action")
    )
    actual_required = False if non_gated else (
        any(token in status for token in ("approval", "gate", "awaiting", "pending")) or bool(gated_action)
    )
    passed = actual_required is expected_required
    return EvaluationCheck(
        name="approval_gate_required",
        passed=passed,
        expected=expected_required,
        actual=actual_required,
        message="approval gate expectation matched" if passed else "approval gate expectation did not match",
    )


def _normalize_text(value: Any) -> str:
    return str(value or "").casefold().strip()


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


if __name__ == "__main__":
    raise SystemExit(main())
