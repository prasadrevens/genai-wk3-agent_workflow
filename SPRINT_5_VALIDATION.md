# Sprint 5 Validation - Splunk Observability Cloud Connector

## Status

Sprint 5 is complete for adding Splunk Observability Cloud behind the connector interface.

## What Sprint 5 Added

- `SplunkO11yConnector`.
- Factory support for `AIOPS_DATA_SOURCE=splunk_o11y`.
- Hybrid route support for `splunk_o11y`.
- Default post-Sprint 5 hybrid routes:
  - Logs -> `splunk_api`
  - Changes -> `splunk_api`
  - Metrics -> `splunk_o11y`
  - Traces -> `splunk_o11y`
  - Service dependencies -> `splunk_o11y`
  - Business metrics -> `minishop`
  - Alert -> `minishop`
- Canonical schema normalization for:
  - `MetricSeries`
  - `TraceSummary`
  - `ServiceDependency`

## Configuration

```text
AIOPS_DATA_SOURCE=hybrid
SPLUNK_O11Y_REALM=us0
SPLUNK_O11Y_ACCESS_TOKEN=<your-o11y-access-token>
SPLUNK_O11Y_METRIC_NAMES=checkout.latency,checkout.failure,deployment.event
SPLUNK_O11Y_SERVICE_DIMENSION=sf_service
```

If O11y is not configured yet, temporarily keep these routes on Mini Shop:

```text
AIOPS_ROUTE_METRICS=minishop
AIOPS_ROUTE_TRACES=minishop
AIOPS_ROUTE_SERVICE_DEPENDENCIES=minishop
```

## What Was Preserved

- LangGraph agent behavior.
- Mini Shop behavior.
- React dashboard behavior.
- Human approval and remediation behavior.
- Existing tool function names and return shapes.

## Validation Commands

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors -v
.venv/bin/python -m compileall aiops_tools.py connectors scripts
cd sentinel-dashboard
npm run build
```

## Acceptance Decision

Accepted for Sprint 5:

- `AIOPS_DATA_SOURCE=splunk_o11y` is selectable.
- `AIOPS_DATA_SOURCE=hybrid` can route metrics, traces, and service dependencies to Splunk O11y.
- Missing O11y credentials return controlled `AUTH_FAILURE`.
- O11y payloads normalize into canonical connector schemas.
- No LangGraph, Mini Shop, React, or remediation behavior changes were introduced.
