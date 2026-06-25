# Sprint 2 Validation - Splunk Platform API Connector

## Status

Sprint 2 is complete for the connector architecture path.

## What Sprint 2 Added

- `SplunkApiConnector` for Splunk Platform API search export.
- Factory support for `AIOPS_DATA_SOURCE=splunk_api`.
- Logs support mapped to canonical `LogEvent`.
- Changes support mapped to canonical `ChangeEvent`.
- Controlled connector responses for missing credentials, timeouts, unavailable Splunk APIs, and unsupported signal types.

## What Was Preserved

- Mini Shop remains the default connector when `AIOPS_DATA_SOURCE` is unset.
- `aiops_tools.py` public function names and return shapes remain unchanged.
- `aiops_agent.py` behavior is unchanged.
- React dashboard behavior is unchanged.
- Remediation approval behavior is unchanged.

## Splunk Scope

Included:

- Logs
- Changes

Not included:

- Splunk Observability Cloud
- Metrics
- Traces
- Business metrics
- Service dependencies
- Hybrid routing across Mini Shop and Splunk

## Validation Commands

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors -v
.venv/bin/python -m compileall aiops_tools.py connectors
cd sentinel-dashboard
npm run build
AIOPS_DATA_SOURCE=minishop .venv/bin/python -c 'from aiops_tools import get_changes; print(len(get_changes(service="checkout-api")))'
AIOPS_DATA_SOURCE=splunk_api .venv/bin/python -c 'from aiops_tools import get_logs, ToolError
try:
    get_logs(service="checkout-api")
except ToolError as exc:
    print(str(exc))'
```

## Acceptance Decision

Accepted for Sprint 2:

- Mini Shop default path still works.
- Splunk API connector is selectable.
- Splunk logs and changes normalize into canonical connector schemas.
- Missing Splunk credentials produce controlled `AUTH_FAILURE` at the connector layer and controlled `ToolError` at the tool layer.
- Unsupported Splunk signal types return controlled `NO_DATA`.
