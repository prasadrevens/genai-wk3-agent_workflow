# Sprint 6 Validation - Service Identity Mapping

## Status

Sprint 6 is complete for canonical service identity mapping.

## What Sprint 6 Added

- `connectors/service_identity.py`.
- Default aliases for Mini Shop, Splunk Platform API, and Splunk O11y.
- Inline JSON override support:

```text
AIOPS_SERVICE_IDENTITY_MAP='{"checkout-api":{"minishop":["checkout-api"],"splunk_api":["checkout-api"],"splunk_o11y":["checkout"]}}'
```

- File override support:

```text
AIOPS_SERVICE_IDENTITY_FILE=./service_identity.json
```

- Splunk API query translation from canonical service to platform service.
- Splunk O11y query translation from canonical service to platform service.
- Connector output normalization back to canonical service names.

## What Was Preserved

- LangGraph agent behavior.
- Existing tool function names and return shapes.
- Mini Shop behavior.
- React dashboard behavior.
- Human approval and remediation behavior.

## Validation Commands

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors tests.test_o11y_emitter -v
.venv/bin/python -m compileall aiops_tools.py connectors scripts mini_shop_with_ui
cd sentinel-dashboard
npm run build
```

## Acceptance Decision

Accepted for Sprint 6:

- Service aliases can be normalized to canonical names.
- O11y can query platform alias names while returning canonical service names.
- Dependency maps are canonicalized.
- No LangGraph, UI, Mini Shop workflow, or remediation behavior changes were introduced.
