# ImpactIQ - Business-Aware AIOps

ImpactIQ is a LangGraph-based AIOps incident triage demo with a live Mini Shop telemetry source, a FastAPI backend, and a React dashboard.

The demo shows how an AI incident workflow can connect technical signals to business impact while keeping production remediation behind an explicit human approval gate.

## What Is Included

- LangGraph multi-agent incident triage workflow
- FastAPI Mini Shop demo app that generates telemetry
- React dashboard with light/dark theme and Executive/Engineer views
- Business-aware KPI cards and dependency view
- Commander-led agent workflow visualization
- Investigation timeline and root-cause analysis panel
- Human-in-the-loop gated action flow
- Voice Incident Commander panel with simulated transcript input
- Deterministic evaluation harness for incident replay cases
- API tests for the dashboard/backend contract

## Architecture

```text
Mini Shop telemetry
        |
        v
FastAPI backend
        |
        v
React dashboard

LangGraph workflow:

Metrics  \
Logs      \
Trace      -> Commander -> Business Impact -> RCA -> Human Gate
Changes   /
```

The current LangGraph implementation follows a commander-led supervisor pattern:

- Specialist agents gather evidence.
- Commander orchestrates the investigation.
- Business Impact evaluates customer/revenue impact.
- RCA synthesizes root cause, confidence, and recommendation.
- Approval remains gated through the dashboard controls.

## Project Layout

```text
.
├── aiops_agent.py                 # LangGraph workflow and agent nodes
├── aiops_tools.py                 # Tool layer reading Mini Shop telemetry
├── connectors/                    # Connector interface and implementations
├── evaluation/                    # Replay-case evaluation harness
├── mini_shop_with_ui/
│   ├── app.py                     # FastAPI app, demo UI, dashboard API routes
│   ├── requirements.txt
│   └── README.md
├── sentinel-dashboard/
│   ├── package.json
│   └── src/
│       ├── SentinelDashboard.jsx
│       ├── SentinelDashboard.css
│       └── main.jsx
├── tests/
│   └── test_sentinel_api.py
├── VOICE_ASSISTANT_PLAN.md
├── MINISHOP_INTEGRATION.md
├── README_aiops.md
└── .env.example
```

## Prerequisites

- Python 3.12+
- Node.js 20+
- An OpenAI-compatible API key for the LangGraph LLM calls

## Environment Setup

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Update the values:

```text
OPENAI_API_KEY=your_openai_api_key_here
AIOPS_DATA_SOURCE=minishop
MINISHOP_DATA=./mini_shop_with_ui/data
MINISHOP_URL=http://localhost:8000
VITE_SENTINEL_API_BASE=http://127.0.0.1:8000
```

Do not commit `.env`. It is intentionally ignored.

### Connector Data Sources

ImpactIQ uses the connector boundary:

```text
Agents -> Tools -> Connector Interface -> Connector Implementation -> Data Source
```

Mini Shop remains the default connector:

```text
AIOPS_DATA_SOURCE=minishop
```

Sprint 2 adds an opt-in Splunk Platform API connector for logs and changes:

```text
AIOPS_DATA_SOURCE=splunk_api
SPLUNK_BASE_URL=https://your-splunk-host:8089
SPLUNK_TOKEN=your_splunk_token_here
SPLUNK_INDEX=main
SPLUNK_VERIFY_SSL=true
SPLUNK_TIMEOUT_SECONDS=10
SPLUNK_AUTH_SCHEME=Splunk
```

The Sprint 2 Splunk connector does not provide metrics, traces, business metrics, or service dependencies yet. Those signals return controlled `NO_DATA` responses so agent code does not receive raw connector exceptions.

Sprint 4 adds hybrid connector routing:

```text
AIOPS_DATA_SOURCE=hybrid
```

Default hybrid routes:

| Signal | Connector |
|---|---|
| Logs | `splunk_api` |
| Changes | `splunk_api` |
| Metrics | `minishop` |
| Traces | `minishop` |
| Business metrics | `minishop` |
| Service dependencies | `minishop` |
| Alert | `minishop` |

Optional per-signal overrides:

```text
AIOPS_ROUTE_LOGS=splunk_api
AIOPS_ROUTE_CHANGES=splunk_api
AIOPS_ROUTE_METRICS=minishop
AIOPS_ROUTE_TRACES=minishop
AIOPS_ROUTE_BUSINESS_METRICS=minishop
AIOPS_ROUTE_SERVICE_DEPENDENCIES=minishop
```

The hybrid router is still below the tool layer, so LangGraph agents continue calling `get_logs`, `get_metrics`, `get_traces`, `get_changes`, `get_business_metrics`, and `get_service_dependencies` exactly as before.

Sprint 5 adds a Splunk Observability Cloud connector and updates hybrid routing:

```text
SPLUNK_O11Y_REALM=us0
SPLUNK_O11Y_ACCESS_TOKEN=your_splunk_o11y_access_token_here
SPLUNK_O11Y_METRIC_NAMES=checkout.latency,checkout.failure,deployment.event
SPLUNK_O11Y_SERVICE_DIMENSION=sf_service
SPLUNK_O11Y_SERVICE_NAME=checkout-api
SPLUNK_O11Y_ENVIRONMENT=demo
```

Current post-Sprint 5 hybrid routes:

| Signal | Connector |
|---|---|
| Logs | `splunk_api` |
| Changes | `splunk_api` |
| Metrics | `splunk_o11y` |
| Traces | `splunk_o11y` |
| Service dependencies | `splunk_o11y` |
| Business metrics | `minishop` |
| Alert | `minishop` |

If your O11y subscription is not configured yet, temporarily route metrics/traces/dependencies back to Mini Shop:

```text
AIOPS_ROUTE_METRICS=minishop
AIOPS_ROUTE_TRACES=minishop
AIOPS_ROUTE_SERVICE_DEPENDENCIES=minishop
```

Mini Shop also mirrors generated telemetry to Splunk O11y ingest when these values are set:

```text
SPLUNK_O11Y_REALM=us1
SPLUNK_O11Y_ACCESS_TOKEN=<your-o11y-access-token>
SPLUNK_O11Y_SERVICE_NAME=checkout-api
SPLUNK_O11Y_ENVIRONMENT=demo
```

The local JSON files are still written. O11y export is best-effort and will not break checkout requests if Splunk is unavailable.

Sprint 6 adds service identity mapping so each connector can translate between
ImpactIQ's canonical service names and platform-specific aliases:

```text
canonical: checkout-api
splunk_api: checkout-api
splunk_o11y: checkout
```

Override aliases with either an inline JSON map:

```text
AIOPS_SERVICE_IDENTITY_MAP='{"checkout-api":{"minishop":["checkout-api"],"splunk_api":["checkout-api"],"splunk_o11y":["checkout"]}}'
```

or a file:

```text
AIOPS_SERVICE_IDENTITY_FILE=./service_identity.json
```

Agents continue asking for the canonical name, such as `checkout-api`. The connector queries the platform alias and returns canonical service names in normalized findings.

Sprint 7 adds synchronized incident windows across connectors. If agents do not
pass `since` and `until`, the tool layer resolves one shared window and passes it
to logs, metrics, traces, changes, and business metrics.

Defaults:

```text
AIOPS_WINDOW_BEFORE_MINUTES=30
AIOPS_WINDOW_AFTER_MINUTES=15
AIOPS_DEFAULT_LOOKBACK_MINUTES=45
```

Resolution order:

1. Explicit `since` / `until` passed by a caller.
2. `AIOPS_INCIDENT_TS`, centered with before/after offsets.
3. Latest Mini Shop `alert.json` timestamp.
4. Recent lookback window.

This prevents Splunk Enterprise logs and Splunk O11y metrics/traces from being
queried over different time ranges during the same triage run.

Sprint 8 adds a lightweight connector cache below the tool layer. Cache keys
include signal type, service, and synchronized time window, so repeated agent
queries during the same triage do not repeatedly hit Splunk or O11y.

```text
AIOPS_CACHE_ENABLED=true
AIOPS_CACHE_TTL_SECONDS=30
AIOPS_CACHE_MAX_ENTRIES=256
AIOPS_CACHE_SUCCESS_ONLY=true
```

Set `AIOPS_CACHE_ENABLED=false` when you want every tool call to hit the source
platform during debugging.

Sprint 9 adds file-backed incident memory. The FastAPI backend records triage
lifecycle events and remediation outcomes to:

```text
mini_shop_with_ui/data/incident_memory.jsonl
```

Read recent records:

```bash
curl http://localhost:8000/api/incident-memory
```

Recorded events include:

- `triage_created`
- `decision_recorded`
- `rollback_confirmed`

This is intentionally append-only demo storage. It does not change the
human-approval gate or trigger any remediation by itself.

Sprint 10 adds a deterministic evaluation harness for replaying known incident
cases and checking RCA quality without calling the LLM during tests.

Run the default replay cases:

```bash
.venv/bin/python -m evaluation.evaluate_incident
```

Machine-readable output:

```bash
.venv/bin/python -m evaluation.evaluate_incident --json
```

The starter cases live in:

```text
evaluation/replay_cases.json
```

Checks currently cover incident status, root-cause keywords, business-impact
keywords, confidence band, recommendation keywords, and whether a human approval
gate is required.

Sprint 11 adds a backend voice assistant boundary and optional ElevenLabs
text-to-speech support. Text-mode voice Q&A works without ElevenLabs.

```text
IMPACTIQ_VOICE_AUDIO_ENABLED=false
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
```

ElevenLabs is called only when `IMPACTIQ_VOICE_AUDIO_ENABLED=true` and an API
key is configured. Voice answers are read-only and do not trigger approvals,
rollbacks, or LangGraph changes.

Sprint 12 adds an MCP connector strategy behind the existing connector
interface. It is opt-in and expects an HTTP bridge to a maintained MCP server:

```text
AIOPS_DATA_SOURCE=mcp
MCP_BRIDGE_URL=http://localhost:8765
MCP_BRIDGE_TOKEN=your_mcp_bridge_token_here
MCP_BRIDGE_TIMEOUT_SECONDS=10
MCP_OBSERVABILITY_TOOL_PREFIX=
```

Hybrid mode can route individual signals through MCP:

```text
AIOPS_DATA_SOURCE=hybrid
AIOPS_ROUTE_LOGS=mcp
AIOPS_ROUTE_CHANGES=mcp
```

The MCP connector preserves the same canonical schemas and return shapes used by
the other connectors. If the bridge is not configured, it returns controlled
`AUTH_FAILURE` responses instead of raising raw exceptions into the agents.

### Local Splunk Lab

Sprint 3 adds an optional local Splunk Enterprise lab for validating the Splunk Platform API connector.

Use it when you want ImpactIQ tools to read logs and changes from Splunk instead of Mini Shop JSON files:

```bash
cd splunk_lab
docker compose up -d
```

Then seed Mini Shop logs and changes:

```bash
python scripts/splunk_lab_seed.py
```

Create a Splunk session token:

```bash
python scripts/splunk_lab_session.py
```

Set `.env`:

```text
AIOPS_DATA_SOURCE=hybrid
SPLUNK_BASE_URL=https://localhost:18089
SPLUNK_TOKEN=<printed-session-token>
SPLUNK_INDEX=impactiq
SPLUNK_VERIFY_SSL=false
SPLUNK_AUTH_SCHEME=Splunk
```

See [splunk_lab/README.md](splunk_lab/README.md) for the full lab workflow.

## Backend Setup

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r mini_shop_with_ui/requirements.txt
```

Start the FastAPI app:

```bash
uvicorn mini_shop_with_ui.app:app --reload --port 8000
```

Open the Mini Shop app:

```text
http://localhost:8000/
```

API docs are available at:

```text
http://localhost:8000/docs
```

## Frontend Setup

In a second terminal:

```bash
cd sentinel-dashboard
npm install
npm run dev
```

Open the dashboard:

```text
http://127.0.0.1:5173/
```

If your backend runs on a different port, set `VITE_SENTINEL_API_BASE` before starting Vite.

## Demo Flow

The officially supported demo path is **React dashboard + FastAPI backend**.
Legacy CLI and Streamlit entry points are not part of the current Sprint 1 acceptance path.

1. Start the FastAPI backend.
2. Start the React dashboard.
3. Open Mini Shop at `http://localhost:8000/`.
4. Generate normal traffic.
5. Trigger a bad deploy.
6. Generate more traffic so logs, metrics, traces, changes, and business metrics are written.
7. Open ImpactIQ at `http://127.0.0.1:5173/`.
8. Watch the alert panel and KPI cards update automatically.
9. Click **Run triage**.
10. Review the agent workflow, investigation timeline, and RCA.
11. Approve or reject only after the human approval gate unlocks.

The dashboard polls incident telemetry automatically about every 5 seconds. Manual Reset UI and Reload telemetry buttons are not exposed in the current UI.

## Dashboard Behavior

### Executive View

Executive view focuses on:

- Incident status
- Payment success
- Failed transactions
- Revenue impact
- Business-facing RCA summary

Approval controls are hidden from Executive view.

### Engineer View

Engineer view includes:

- Agent workflow
- Service dependency tree
- Business metrics
- Investigation timeline
- RCA confidence and reasoning
- Gated recommended action

### KPI Thresholds

- Payment success is healthy at or above 95%.
- Payment success below 95% is shown as critical.
- Business metrics use the same payment-success threshold as the top KPI cards.
- Estimated impact uses the same visual tone as the Revenue Impact KPI.

### Service Dependency State

When the incident is healthy, all service dependencies render as OK.

When degraded, affected services are highlighted:

- `bottleneck` in red
- `timeout` in amber
- `ok` in green

## Voice Incident Commander

Phase 1 and Phase 2 are implemented.

Current capabilities:

- Voice Incident Commander panel in the dashboard
- Suggested voice commands
- Text input that simulates a voice transcript
- `answer_voice_question(question, incident_state)` helper
- Backend `/api/voice/ask` endpoint
- Optional ElevenLabs text-to-speech boundary

It can answer questions about:

- Incident status
- Root cause
- Business impact
- Confidence
- Recommendation
- Approval status

ElevenLabs audio synthesis is disabled by default.

Future integration notes are in `VOICE_ASSISTANT_PLAN.md`.

## Human Approval And Remediation Guardrails

The dashboard never triggers remediation directly from a single click.

Current flow:

1. Triage reaches the human approval gate.
2. Approve or Reject controls unlock.
3. Reject records the decision and makes no automated change.
4. Approve records approval and shows a second confirmation step.
5. Rollback integration is only behind the explicit confirmation gate.

LangGraph logic and remediation behavior are intentionally kept separate from cosmetic UI changes.

## API Endpoints

Dashboard-facing endpoints:

```text
GET  /api/incident
GET  /api/rca
POST /api/triage/run
GET  /api/triage/stream?run_id=...
POST /api/triage/reset
POST /api/telemetry/reload
POST /api/triage/decision
POST /api/triage/confirm-rollback
GET  /api/voice/status
POST /api/voice/ask
```

Mini Shop demo endpoints:

```text
GET  /
GET  /health
GET  /products
POST /checkout
GET  /admin/deploy?mode=good|bad
POST /admin/generate-load?count=...
GET  /admin/telemetry
POST /admin/reset
```

## Testing

Run backend/API tests:

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors tests.test_o11y_emitter tests.test_time_window tests.test_evaluation_harness tests.test_voice_assistant -v
```

Run the evaluation harness:

```bash
.venv/bin/python -m evaluation.evaluate_incident
```

Build the frontend:

```bash
cd sentinel-dashboard
npm run build
```

## Sprint 1 Acceptance Scope

Sprint 1 validates the connector foundation through the supported React + FastAPI path:

- FastAPI dashboard APIs continue to read Mini Shop telemetry through the connector-backed tool layer.
- React dashboard can load incidents, display business impact, and run triage.
- `aiops_agent.py` behavior is unchanged.
- Mini Shop behavior is unchanged.
- Approval and rollback gating remain unchanged.

Out of scope for Sprint 1 acceptance:

- `python run_incident.py`
- `streamlit run streamlit_app.py`

Those older entry points are treated as legacy/reference paths unless they are explicitly restored in a future sprint.

## Sprint 2 Connector Scope

Sprint 2 introduces `connectors/splunk_api_connector.py` and factory support for:

```text
AIOPS_DATA_SOURCE=splunk_api
```

Included in Sprint 2:

- Splunk Platform API connector selection through `connectors/factory.py`.
- Logs support through Splunk search export.
- Changes support through Splunk search export.
- Canonical `LogEvent` and `ChangeEvent` normalization.
- Controlled `AUTH_FAILURE`, `TIMEOUT`, `UNAVAILABLE`, and `NO_DATA` connector responses.

Not included in Sprint 2:

- Splunk Observability Cloud.
- Splunk metrics and traces.
- Hybrid Mini Shop + Splunk routing.
- LangGraph agent behavior changes.
- Remediation or approval behavior changes.

## Sprint 4 Hybrid Routing Scope

Sprint 4 introduces `connectors/hybrid_connector.py` and factory support for:

```text
AIOPS_DATA_SOURCE=hybrid
```

Included in Sprint 4:

- Per-signal connector routing.
- Logs and changes routed to `SplunkApiConnector`.
- Metrics, traces, business metrics, service dependencies, and alert data routed to `MiniShopConnector`.
- Environment overrides using `AIOPS_ROUTE_<SIGNAL>`.

Not included in Sprint 4:

- Splunk Observability Cloud.
- Metrics/traces from Splunk O11y.
- Service map from Splunk O11y.
- LangGraph agent behavior changes.
- React dashboard behavior changes.
- Approval or remediation behavior changes.

## Sprint 5 Splunk Observability Cloud Scope

Sprint 5 introduces `connectors/splunk_o11y_connector.py` and factory support for:

```text
AIOPS_DATA_SOURCE=splunk_o11y
```

Hybrid mode now supports this route value:

```text
AIOPS_ROUTE_METRICS=splunk_o11y
AIOPS_ROUTE_TRACES=splunk_o11y
AIOPS_ROUTE_SERVICE_DEPENDENCIES=splunk_o11y
```

Included in Sprint 5:

- Splunk O11y connector selection through `connectors/factory.py`.
- Metrics support through a SignalFlow query path.
- Trace support through a configurable O11y APM trace path.
- Service dependency support through a configurable O11y service-map path.
- Canonical `MetricSeries`, `TraceSummary`, and `ServiceDependency` normalization.
- Controlled `AUTH_FAILURE`, `TIMEOUT`, `UNAVAILABLE`, and `NO_DATA` responses.

Not included in Sprint 5:

- Real O11y token storage beyond environment variables.
- Business metrics from Splunk O11y.
- Logs or changes from Splunk O11y.
- LangGraph agent behavior changes.
- React dashboard behavior changes.
- Approval or remediation behavior changes.

## Sprint 6 Service Identity Mapping Scope

Sprint 6 introduces `connectors/service_identity.py`.

Included in Sprint 6:

- Canonical service-name mapping.
- Platform alias lookup for `minishop`, `splunk_api`, and `splunk_o11y`.
- Environment override support through `AIOPS_SERVICE_IDENTITY_MAP`.
- File override support through `AIOPS_SERVICE_IDENTITY_FILE`.
- Connector query translation from canonical service to platform service.
- Connector output normalization from platform service back to canonical service.

Not included in Sprint 6:

- UI changes.
- Agent prompt changes.
- Persistent service catalog storage.
- Time-window synchronization.

## Sprint 7 Time Window Synchronization Scope

Sprint 7 introduces `connectors/time_window.py`.

Included in Sprint 7:

- Shared incident window resolution.
- Explicit caller windows are preserved.
- Alert-centered windows using `AIOPS_INCIDENT_TS` or Mini Shop `alert.json`.
- Lookback fallback when no alert timestamp exists.
- Tool-layer injection into logs, metrics, traces, changes, and business metrics.

Not included in Sprint 7:

- Persistent incident window storage.
- UI controls for time windows.
- Agent prompt changes.
- Connector-specific pagination or long-range query optimization.

## Sprint 8 Cache Layer Scope

Sprint 8 introduces `connectors/cache.py`.

Included in Sprint 8:

- Connector-level TTL cache wrapper.
- Factory integration for all connector modes.
- Cache opt-out with `AIOPS_CACHE_ENABLED=false`.
- TTL and max-entry controls.
- Deep-copy protection so cached mutable responses cannot leak mutations.
- Cache keys include signal parameters, service, and time window.

Not included in Sprint 8:

- Persistent cache storage.
- Distributed cache coordination.
- UI cache controls.
- Caching write/remediation actions.

## Sprint 9 Incident Memory Scope

Sprint 9 introduces `incident_memory.py`.

Included in Sprint 9:

- File-backed incident memory records.
- Triage creation records.
- Human decision records.
- Rollback confirmation outcome records.
- Read endpoint at `GET /api/incident-memory`.

Not included in Sprint 9:

- Vector search or semantic recurrence detection.
- Persistent database storage.
- UI incident-memory views.
- Automatic remediation from memory.

## Sprint 10 Evaluation Harness Scope

Sprint 10 introduces `evaluation/evaluate_incident.py`.

Included in Sprint 10:

- Replay-case loading from JSON.
- Deterministic scoring of expected RCA fields.
- CLI output for human-readable and JSON evaluation reports.
- Starter Mini Shop replay cases for bad deploy and healthy checkout.
- Unit tests for evaluator scoring and summary behavior.

Not included in Sprint 10:

- LangGraph agent behavior changes.
- LLM-based evaluation.
- React dashboard changes.
- Remediation or approval behavior changes.

## Sprint 11 ElevenLabs Voice Assistant Scope

Sprint 11 introduces `voice_assistant.py`.

Included in Sprint 11:

- Backend voice Q&A service boundary.
- `GET /api/voice/status`.
- `POST /api/voice/ask`.
- Optional ElevenLabs text-to-speech client guarded by environment flags.
- React voice panel calls the backend endpoint with a local text fallback.
- Tests ensuring audio is disabled by default and secrets are not exposed.

Not included in Sprint 11:

- Microphone capture.
- Speech-to-text streaming.
- Dashboard audio playback controls.
- LangGraph agent behavior changes.
- Remediation or approval behavior changes.

## Sprint 12 MCP Connector Scope

Sprint 12 introduces `connectors/mcp_connector.py`.

Included in Sprint 12:

- `AIOPS_DATA_SOURCE=mcp` factory support.
- `AIOPS_ROUTE_<SIGNAL>=mcp` hybrid routing support.
- HTTP bridge adapter for MCP-backed observability tools.
- Canonical normalization for logs, metrics, traces, changes, business metrics, and dependencies.
- Controlled `AUTH_FAILURE`, `TIMEOUT`, `UNAVAILABLE`, and `NO_DATA` responses.

Not included in Sprint 12:

- A bundled MCP server.
- Vendor-specific MCP server installation.
- LangGraph agent behavior changes.
- React dashboard changes.
- Remediation or approval behavior changes.

## Notes

- Generated telemetry and logs are ignored by Git.
- `node_modules`, `dist`, `.venv`, `.env`, logs, cache files, and `MISC` are ignored.
- The dashboard is designed to be driven by live Mini Shop telemetry, not static fixtures.
- `README_aiops.md` and `MINISHOP_INTEGRATION.md` contain older project notes and deeper implementation context.
