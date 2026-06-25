# Sprint 1 Validation - Connector Layer Foundation

## Status

Sprint 1 is complete for the officially supported ImpactIQ demo path:

```text
React dashboard -> FastAPI backend -> aiops_tools.py -> connector layer -> Mini Shop telemetry files
```

## Supported Demo Path

The supported demo path is:

1. Start FastAPI.
2. Start the React dashboard.
3. Generate Mini Shop telemetry.
4. Run triage from the React dashboard.
5. Review RCA, business impact, confidence, and gated recommendation.

Legacy CLI and Streamlit entry points are not part of Sprint 1 acceptance.

## What Sprint 1 Added

- `connectors/` package.
- Canonical connector schemas.
- `BaseObservabilityConnector`.
- `MiniShopConnector`.
- Connector factory using `AIOPS_DATA_SOURCE=minishop`.
- `aiops_tools.py` delegation to connector methods while preserving legacy tool names and return shapes.

## What Was Preserved

- LangGraph agent behavior.
- Mini Shop behavior.
- React dashboard behavior.
- Existing RCA, business impact, confidence, and approval flow.
- Human approval gate and remediation guardrails.

## Acceptance Decision

Accepted for Sprint 1:

- React + FastAPI path works.
- Mini Shop connector works by default.
- `AIOPS_DATA_SOURCE=minishop` works.
- Missing telemetry produces connector-level `NO_DATA`.
- Tool layer converts connector failures into controlled `ToolError`.
- `aiops_agent.py` does not need changes.

Not required for Sprint 1:

```bash
python run_incident.py
streamlit run streamlit_app.py
```

These are legacy/reference paths unless restored in a future sprint.

## Validation Commands

```bash
.venv/bin/python -m unittest tests.test_sentinel_api -v
.venv/bin/python -m compileall aiops_tools.py connectors
cd sentinel-dashboard
npm run build
```

## Next Sprint

Sprint 2 should start from the connector interface and add the next platform connector without changing agent behavior.
