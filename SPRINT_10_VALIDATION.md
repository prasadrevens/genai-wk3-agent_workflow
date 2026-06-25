# Sprint 10 Validation - Evaluation Harness

Sprint 10 adds a deterministic evaluation harness around ImpactIQ incident
replay cases.

## Scope

Included:

- `evaluation/evaluate_incident.py` command-line evaluator.
- `evaluation/replay_cases.json` starter replay cases.
- Unit coverage for case loading, scoring, failed checks, and summaries.
- README documentation for running evaluations.

Not included:

- LangGraph behavior changes.
- LLM calls from evaluation tests.
- React UI changes.
- Remediation or approval behavior changes.

## Run

```bash
.venv/bin/python -m evaluation.evaluate_incident
```

Machine-readable output:

```bash
.venv/bin/python -m evaluation.evaluate_incident --json
```

## Expected Result

The default replay cases should pass with a full score. Future cases can provide
candidate outputs in a separate JSON file using `--candidates`.
