# Mini Shop integration notes (v1.3)

The agent now reads telemetry from the **live Mini Shop app** instead of
`aiops_scenarios.py` (that script is no longer used).

## What changed
- `aiops_tools.py` now reads the app's real files in `mini_shop/data/`:
  `logs.json, metrics.json, traces.json, business_metrics.json,
  service_dependencies.json, changes.json, alert.json`. Schemas matched to the app
  (`ts`, `message`, nested workflows, single business-metrics object, etc.).
- Tool location is configurable: `export MINISHOP_DATA=/path/to/mini_shop/data`
  (default `./mini_shop/data`).
- `run_incident.py` and `streamlit_app.py` now load the alert from `MINISHOP_DATA`.
- The gated write `remediate()` can perform the **real corrective action**: if
  `MINISHOP_URL` is set, it calls `GET {url}/admin/deploy?mode=good` to roll the app
  back. Without it, it simulates.
- `aiops_scenarios.py` is deprecated (kept only as a fallback reference).

## ⚠️ Bug in the app you must fix
`/admin/deploy` (the `deploy?mode=bad` curl) crashes with
`TypeError: log_event() got multiple values for argument 'service'`, because
`**change` re-passes `service`. One-line fix in `app.py`, `deploy()`:

```python
# before
log_event("WARN" if mode == "bad" else "INFO", "deployment", change["summary"], **change)
# after
log_event("WARN" if mode == "bad" else "INFO", "deployment", change["summary"],
          **{k: v for k, v in change.items() if k != "service"})
```

## ⚠️ Business-metric gotcha
`transaction_drop_percent` is **unreliable here**: `generate-load` adds successful
transactions, which inflates today's count past last week's baseline, so the "drop"
can go negative even during the incident (observed: -5.3%). The reliable degradation
signals are **`payment_success_rate_percent`** (fell to ~75%) and
**`failed_transactions_last_24h`**. The Business agent prompt was updated to key off
those, and to treat the drop% as informational only.

## End-to-end run
```bash
# 1) start the app (after applying the deploy() fix)
cd mini_shop && uvicorn app:app --reload --port 8000

# 2) drive the bad deployment (your curl flow)
curl -X POST http://localhost:8000/admin/reset
curl -X POST "http://localhost:8000/admin/generate-load?count=20"
curl "http://localhost:8000/admin/deploy?mode=bad"
curl -X POST "http://localhost:8000/admin/generate-load?count=30"

# 3) run the agent against the app's telemetry
export MINISHOP_DATA=/abs/path/to/mini_shop/data
export MINISHOP_URL=http://localhost:8000     # optional: lets approve actually roll back
python run_incident.py                        # CLI
streamlit run streamlit_app.py                # UI
```

## Verified signals from the real app (after the bad-deploy flow)
- Logs: 15 ERROR events, `error_type=payment_timeout`
- Metrics: `checkout.latency` p95 ≈ 3861 ms (max 4148); 15 checkout failures
- Traces: bottleneck `checkout-api / validate cart` ≈ 3947 ms; 15 error traces
- Business: payment success ≈ 74.8%, 35 failed transactions
- Change: `v1.0.1-bad`, risk `high`
- Runbook match: `RB-CHK-01` (roll back checkout-api)

All tools verified against real app data; the live LLM run still needs your Nebius key.
