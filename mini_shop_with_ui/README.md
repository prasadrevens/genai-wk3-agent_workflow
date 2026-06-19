# Mini Shop — Lightweight AIOps Demo App

Mini Shop is a tiny FastAPI e-commerce app for your AIOps multi-agent triage project. It creates realistic demo telemetry that your agent can investigate without running a heavy microservices app.

## What it includes

- Lightweight HTML UI at `http://localhost:8000/`
- Swagger API docs at `http://localhost:8000/docs`
- Product browsing and checkout
- Bad deployment simulation
- Normal traffic generation
- Synthetic logs, metrics, traces, business metrics, service dependencies, changes, and alert files

## Run locally

```bash
cd mini_shop
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open:

```text
http://localhost:8000/
```

## Demo flow

1. Open the UI.
2. Click **Generate normal traffic**.
3. Click **Trigger bad deploy**.
4. Click **Generate normal traffic** again.
5. Click **Telemetry files** or **Business metrics**.
6. Run your AIOps agent against the generated files in `mini_shop/data/`.

## Generated telemetry files

```text
data/logs.json
data/metrics.json
data/traces.json
data/business_metrics.json
data/service_dependencies.json
data/changes.json
data/alert.json
logs/app.log
```

## Useful commands

```bash
curl -X POST http://localhost:8000/admin/reset
curl -X POST "http://localhost:8000/admin/generate-load?count=20"
curl "http://localhost:8000/admin/deploy?mode=bad"
curl -X POST "http://localhost:8000/admin/generate-load?count=30"
curl http://localhost:8000/admin/telemetry
```
