# Sprint 8 Validation - Cache Layer

## Status

Sprint 8 is complete for connector-level response caching.

## What Sprint 8 Added

- `connectors/cache.py`.
- `CachedConnector` wrapper.
- `ConnectorCache` in-memory TTL cache.
- Factory wrapping for:
  - `minishop`
  - `splunk_api`
  - `splunk_o11y`
  - `hybrid`
- Cache opt-out:

```text
AIOPS_CACHE_ENABLED=false
```

## Configuration

```text
AIOPS_CACHE_ENABLED=true
AIOPS_CACHE_TTL_SECONDS=30
AIOPS_CACHE_MAX_ENTRIES=256
AIOPS_CACHE_SUCCESS_ONLY=true
```

## What Was Preserved

- LangGraph agent behavior.
- Tool function names and return shapes.
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

Accepted for Sprint 8:

- Repeated connector reads can be served from cache.
- Cache can be disabled.
- Cache entries are keyed by request parameters including time window.
- Cached responses are deep-copied to prevent mutation leaks.
- No LangGraph, UI, Mini Shop workflow, or remediation behavior changes were introduced.
