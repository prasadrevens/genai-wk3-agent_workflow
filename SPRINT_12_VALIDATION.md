# Sprint 12 Validation - MCP Connectors

Sprint 12 adds MCP as an opt-in connector strategy behind the existing
observability connector interface.

## Scope

Included:

- `connectors/mcp_connector.py`.
- Factory support for `AIOPS_DATA_SOURCE=mcp`.
- Hybrid routing support for `AIOPS_ROUTE_<SIGNAL>=mcp`.
- Canonical schema normalization for MCP tool results.
- Controlled connector errors when the MCP bridge is unavailable or unconfigured.

Not included:

- A bundled MCP server.
- Vendor-specific MCP installation.
- LangGraph agent behavior changes.
- React dashboard changes.
- Remediation or approval behavior changes.

## Environment

```text
AIOPS_DATA_SOURCE=mcp
MCP_BRIDGE_URL=http://localhost:8765
MCP_BRIDGE_TOKEN=your_mcp_bridge_token_here
MCP_BRIDGE_TIMEOUT_SECONDS=10
MCP_OBSERVABILITY_TOOL_PREFIX=
```

For hybrid routing:

```text
AIOPS_DATA_SOURCE=hybrid
AIOPS_ROUTE_LOGS=mcp
AIOPS_ROUTE_CHANGES=mcp
```

## Run

```bash
.venv/bin/python -m unittest tests.test_connectors -v
```

Full validation:

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors tests.test_o11y_emitter tests.test_time_window tests.test_evaluation_harness tests.test_voice_assistant -v
```
