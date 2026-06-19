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
MINISHOP_DATA=./mini_shop_with_ui/data
MINISHOP_URL=http://localhost:8000
VITE_SENTINEL_API_BASE=http://127.0.0.1:8000
```

Do not commit `.env`. It is intentionally ignored.

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

It can answer questions about:

- Incident status
- Root cause
- Business impact
- Confidence
- Recommendation
- Approval status

ElevenLabs is not called yet.

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
.venv/bin/python -m unittest tests.test_sentinel_api -v
```

Build the frontend:

```bash
cd sentinel-dashboard
npm run build
```

## Notes

- Generated telemetry and logs are ignored by Git.
- `node_modules`, `dist`, `.venv`, `.env`, logs, cache files, and `MISC` are ignored.
- The dashboard is designed to be driven by live Mini Shop telemetry, not static fixtures.
- `README_aiops.md` and `MINISHOP_INTEGRATION.md` contain older project notes and deeper implementation context.
