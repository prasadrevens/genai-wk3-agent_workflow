# Sprint 7 Validation - Time Window Synchronization

## Status

Sprint 7 is complete for shared incident time-window resolution.

## What Sprint 7 Added

- `connectors/time_window.py`.
- Shared window resolver.
- Explicit `since` / `until` preservation.
- Alert-centered windows using:
  - `AIOPS_INCIDENT_TS`
  - Mini Shop `alert.json` timestamp
- Lookback fallback when no alert timestamp exists.
- Tool-layer window injection for:
  - logs
  - metrics
  - traces
  - changes
  - business metrics

## Configuration

```text
AIOPS_WINDOW_BEFORE_MINUTES=30
AIOPS_WINDOW_AFTER_MINUTES=15
AIOPS_DEFAULT_LOOKBACK_MINUTES=45
# AIOPS_INCIDENT_TS=2026-06-21T03:00:00+00:00
```

## What Was Preserved

- LangGraph agent behavior.
- Existing tool function names.
- Connector interfaces.
- Mini Shop behavior.
- React dashboard behavior.
- Human approval and remediation behavior.

## Validation Commands

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors tests.test_o11y_emitter tests.test_time_window -v
.venv/bin/python -m compileall aiops_tools.py connectors scripts mini_shop_with_ui
cd sentinel-dashboard
npm run build
```

## Acceptance Decision

Accepted for Sprint 7:

- All signal tools use the same default incident window.
- Explicit caller-provided windows still win.
- Alert-centered and lookback fallback windows work.
- No LangGraph, UI, Mini Shop workflow, or remediation behavior changes were introduced.
