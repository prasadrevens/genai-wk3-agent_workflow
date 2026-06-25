# Sprint 4 Validation - Hybrid Connector Routing

## Status

Sprint 4 is complete for signal-type connector routing.

## What Sprint 4 Added

- `HybridConnector`, a connector-level router that preserves the existing tool interface.
- Factory support for `AIOPS_DATA_SOURCE=hybrid`.
- Default routes:
  - Logs -> `splunk_api`
  - Changes -> `splunk_api`
  - Metrics -> `minishop`
  - Traces -> `minishop`
  - Business metrics -> `minishop`
  - Service dependencies -> `minishop`
  - Alert -> `minishop`
- Per-signal route overrides with `AIOPS_ROUTE_<SIGNAL>`.

## What Was Preserved

- Agents still call the same tool functions.
- `aiops_agent.py` behavior is unchanged.
- Mini Shop behavior is unchanged.
- React dashboard behavior is unchanged.
- Human approval and remediation behavior are unchanged.

## Usage

With local Splunk lab running and seeded:

```text
AIOPS_DATA_SOURCE=hybrid
SPLUNK_BASE_URL=https://localhost:18089
SPLUNK_TOKEN=<printed-session-token>
SPLUNK_INDEX=impactiq
SPLUNK_VERIFY_SSL=false
SPLUNK_AUTH_SCHEME=Splunk
```

## Validation Commands

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors -v
.venv/bin/python -m compileall aiops_tools.py connectors scripts
cd sentinel-dashboard
npm run build
```

## Acceptance Decision

Accepted for Sprint 4:

- `AIOPS_DATA_SOURCE=hybrid` is selectable.
- Hybrid connector routes logs and changes separately from other signals.
- Per-signal route overrides work.
- Existing Mini Shop default path still works.
- No LangGraph, Mini Shop, React, or remediation behavior changes were introduced.
