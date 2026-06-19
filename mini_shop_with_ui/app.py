from __future__ import annotations

import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from aiops_agent import build_app
from langgraph.types import Command

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
os.environ["MINISHOP_DATA"] = str(DATA_DIR)

STATE_FILE = DATA_DIR / "state.json"
APP_LOG_FILE = LOG_DIR / "app.log"
JSON_LOG_FILE = DATA_DIR / "logs.json"
METRICS_FILE = DATA_DIR / "metrics.json"
TRACES_FILE = DATA_DIR / "traces.json"
BUSINESS_FILE = DATA_DIR / "business_metrics.json"
DEPS_FILE = DATA_DIR / "service_dependencies.json"
CHANGES_FILE = DATA_DIR / "changes.json"
ALERT_FILE = DATA_DIR / "alert.json"

PRODUCTS = [
    {"id": "p-100", "name": "Nebula Hoodie", "price": 59.0},
    {"id": "p-200", "name": "Rocket Mug", "price": 18.0},
    {"id": "p-300", "name": "Moon Lamp", "price": 42.0},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2))


def append_json(path: Path, item: Any, max_items: int = 250) -> None:
    items = read_json(path, [])
    items.append(item)
    write_json(path, items[-max_items:])


def get_state() -> Dict[str, Any]:
    state = read_json(STATE_FILE, {})
    if not state:
        state = {
            "deploy_mode": "good",
            "deployment_version": "v1.0.0",
            "last_deploy_at": now_iso(),
            "transactions_today": 128,
            "transactions_same_period_last_week": 132,
            "failed_transactions_today": 2,
            "revenue_today": 5368.0,
            "revenue_same_period_last_week": 5544.0,
        }
        write_json(STATE_FILE, state)
    return state


def save_state(state: Dict[str, Any]) -> None:
    write_json(STATE_FILE, state)


def log_event(level: str, service: str, message: str, **fields: Any) -> None:
    event = {"ts": now_iso(), "level": level, "service": service, "message": message, **fields}
    APP_LOG_FILE.open("a").write(json.dumps(event) + "\n")
    append_json(JSON_LOG_FILE, event)


def record_metric(name: str, value: float, unit: str, service: str, **tags: Any) -> None:
    append_json(METRICS_FILE, {
        "ts": now_iso(), "metric": name, "value": value, "unit": unit, "service": service, "tags": tags,
    })


def record_trace(endpoint: str, spans: List[Dict[str, Any]], status: str, trace_id: Optional[str] = None) -> None:
    append_json(TRACES_FILE, {
        "trace_id": trace_id or str(uuid.uuid4()),
        "ts": now_iso(),
        "endpoint": endpoint,
        "status": status,
        "total_duration_ms": sum(span["duration_ms"] for span in spans),
        "spans": spans,
    })


def refresh_business_metrics() -> Dict[str, Any]:
    state = get_state()
    tx = state["transactions_today"]
    prev = state["transactions_same_period_last_week"]
    failed = state["failed_transactions_today"]
    checkout_attempts = tx + failed
    revenue = round(state["revenue_today"], 2)
    prev_revenue = round(state["revenue_same_period_last_week"], 2)
    drop_pct = round(((prev - tx) / prev) * 100, 1) if prev else 0
    payment_success_rate = round((tx / max(checkout_attempts, 1)) * 100, 1)
    baseline_gap = max(prev - tx, 0)
    # In this demo, generate-load may increase successful transactions even during an incident.
    # Treat failed checkout attempts as revenue-impact evidence too, so business impact remains
    # honest even when transaction_drop_percent is masked or negative.
    estimated_lost_transactions = baseline_gap + failed
    avg_order_value = round(prev_revenue / max(prev, 1), 2)
    estimated_revenue_impact = round(estimated_lost_transactions * avg_order_value, 2)

    payload = {
        "ts": now_iso(),
        "workflow": "checkout",
        "transactions_last_24h": checkout_attempts,
        "successful_transactions_last_24h": tx,
        "transactions_same_period_last_week": prev,
        "transaction_drop_percent": drop_pct,
        "failed_transactions_last_24h": failed,
        "payment_success_rate_percent": payment_success_rate,
        "revenue_last_24h": revenue,
        "revenue_same_period_last_week": prev_revenue,
        "estimated_lost_transactions": estimated_lost_transactions,
        "estimated_revenue_impact": estimated_revenue_impact,
        "business_summary": (
            "Checkout is degraded: payment success is low or failed transactions are elevated."
            if payment_success_rate < 95 or failed > 5 or drop_pct > 10
            else "Checkout purchases are within normal range."
        ),
    }
    write_json(BUSINESS_FILE, payload)
    return payload


def write_static_dependencies() -> None:
    deps = {
        "application": "Mini Shop",
        "business_workflows": {
            "checkout": {
                "description": "Customer browses product, submits checkout, payment is authorized, order is confirmed.",
                "critical_path": ["frontend", "checkout-api", "payment-api", "orders-db", "notification-service"],
                "business_kpis": ["transactions_last_24h", "payment_success_rate_percent", "revenue_last_24h"],
            },
            "product_browse": {
                "critical_path": ["frontend", "catalog-api", "products-db"],
                "business_kpis": ["product_page_views", "add_to_cart_rate"],
            },
        },
        "services": {
            "frontend": ["catalog-api", "checkout-api"],
            "checkout-api": ["payment-api", "orders-db", "notification-service"],
            "payment-api": ["third-party-payment-provider"],
            "catalog-api": ["products-db"],
            "notification-service": ["email-provider"],
        },
    }
    write_json(DEPS_FILE, deps)


def maybe_create_alert() -> None:
    state = get_state()
    business = refresh_business_metrics()
    if state["deploy_mode"] == "bad":
        alert = {
            "incident_id": "INC-MINISHOP-001",
            "ts": now_iso(),
            "severity": "critical",
            "service": "checkout-api",
            "workflow": "checkout",
            "title": "Checkout latency and failed transactions increased",
            "symptoms": [
                "p95 checkout latency above threshold",
                "payment failures increased",
                "transactions below same period last week",
            ],
            "business_impact": {
                "transaction_drop_percent": business["transaction_drop_percent"],
                "estimated_revenue_impact": business["estimated_revenue_impact"],
            },
        }
        write_json(ALERT_FILE, alert)


app = FastAPI(title="Mini Shop", version="1.0.0", description="Lightweight e-commerce app for AIOps multi-agent monitoring demos.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TRIAGE_RUNS: Dict[str, Dict[str, Any]] = {}


class CheckoutRequest(BaseModel):
    product_id: str = "p-100"
    quantity: int = 1


class TriageDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


def _latest_run() -> Optional[Dict[str, Any]]:
    if not TRIAGE_RUNS:
        return None
    return max(TRIAGE_RUNS.values(), key=lambda run: run.get("created_at", ""))


def _status_from_state() -> str:
    state = get_state()
    if state["deploy_mode"] == "bad":
        return "degraded"
    return "healthy"


def _dependency_rows(alert: Dict[str, Any], incident_status: str) -> List[Dict[str, Any]]:
    deps = read_json(DEPS_FILE, {}) or {}
    workflow = alert.get("workflow", "checkout")
    workflow_deps = (deps.get("business_workflows", {}) or {}).get(workflow, {})
    critical_path = workflow_deps.get("critical_path") or [
        "frontend",
        "checkout-api",
        "payment-api",
        "catalog-api",
        "notification-svc",
    ]
    children = (deps.get("services", {}) or {}).get("checkout-api", [])
    child_aliases = {
        "orders-db": "catalog-api",
        "notification-service": "notification-svc",
    }

    rows = []
    for index, name in enumerate(critical_path):
        display = child_aliases.get(name, name)
        if display == "orders-db":
            continue
        if display == "notification-service":
            display = "notification-svc"
        if display == "frontend":
            depth = 1
        elif display == alert.get("service", "checkout-api"):
            depth = 2
        else:
            depth = 3
        state = "ok"
        if incident_status != "healthy":
            if display == alert.get("service", "checkout-api"):
                state = "bottleneck"
            elif display == "payment-api":
                state = "timeout"
        rows.append({"name": display, "depth": depth, "state": state})

    for name in children:
        display = child_aliases.get(name, name)
        if not any(row["name"] == display for row in rows):
            rows.append({"name": display, "depth": 3, "state": "ok"})
    return rows


def _incident_payload() -> Dict[str, Any]:
    business = refresh_business_metrics()
    maybe_create_alert()
    status = _status_from_state()
    alert = read_json(ALERT_FILE, {}) or {
        "severity": "low",
        "service": "checkout-api",
        "workflow": "checkout",
        "title": "Checkout workflow operating normally",
    }
    payment_success = business.get("payment_success_rate_percent", 0) or 0
    failed = business.get("failed_transactions_last_24h", 0) or 0
    total = business.get("transactions_last_24h", 0) or 0
    confidence = "high" if failed > 5 or payment_success < 95 else "low"
    severity = alert.get("severity", "low")
    title = alert.get("title", "Checkout workflow operating normally")
    if status == "healthy":
        severity = "low"
        title = "Checkout workflow operating normally"
    return {
        "severity": severity,
        "confidence": confidence,
        "title": title,
        "service": alert.get("service", "checkout-api"),
        "workflow": alert.get("workflow", "checkout"),
        "status": status,
        "alert_received_at": alert.get("ts") or now_iso(),
        "telemetry_path": str(DATA_DIR),
        "mini_shop_url": "http://localhost:8000",
        "kpis": {
            "payment_success_pct": payment_success,
            "failed_transactions": failed,
            "total_transactions": total,
            "revenue_24h": business.get("revenue_last_24h", 0) or 0,
            "estimated_impact": business.get("estimated_revenue_impact", 0) or 0,
        },
        "dependencies": _dependency_rows(alert, status),
    }


def _rca_payload() -> Dict[str, Any]:
    latest = _latest_run() or {}
    pause = latest.get("pause") or {}
    business = refresh_business_metrics()
    business_impact = pause.get("business_impact") or business.get("business_summary") or (
        "Checkout business metrics are available for triage."
    )
    confidence = pause.get("confidence_band") or (
        "High" if (business.get("failed_transactions_last_24h") or 0) > 5 else "Low"
    )
    reasoning = pause.get("confidence_reasoning") or []
    if not reasoning:
        reasoning = ["business telemetry refreshed from Mini Shop data"]
    gated_action = pause.get("proposed_fix") or (
        "Inspect the most recent deployment to checkout-api and roll back if correlated."
    )
    return {
        "root_cause": pause.get("root_cause") or "Awaiting triage run for synthesized root cause.",
        "business_impact": business_impact,
        "confidence": confidence,
        "reasoning": reasoning,
        "reasoning_signals": len(reasoning),
        "gated_action": gated_action,
        "decision_status": latest.get("decision_status"),
    }


def _stage_name(agent: str) -> str:
    return {
        "orchestrator": "commander",
        "synthesize": "rca",
        "resolver": "rca",
        "human": "rca",
    }.get(agent, agent)


def _sse(payload: Dict[str, Any], event: Optional[str] = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(payload)}\n\n"


@app.on_event("startup")
def startup() -> None:
    get_state()
    write_static_dependencies()
    refresh_business_metrics()
    log_event("INFO", "mini-shop", "Mini Shop started")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """Lightweight browser UI for the monitored demo shop."""
    state = get_state()
    business = refresh_business_metrics()
    mode_class = "bad" if state["deploy_mode"] == "bad" else "good"
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Mini Shop — AIOps Demo App</title>
  <style>
    :root {{
      --bg: #08111f;
      --panel: #101b2d;
      --panel2: #0d1728;
      --text: #e8f1ff;
      --muted: #9fb4d0;
      --accent: #2dd4bf;
      --danger: #fb7185;
      --warning: #fbbf24;
      --ok: #34d399;
      --border: #21314b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top left, #12345a 0, var(--bg) 36%);
      color: var(--text);
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    .hero {{ display: grid; grid-template-columns: 1.4fr 0.8fr; gap: 18px; align-items: stretch; }}
    .card {{
      background: linear-gradient(180deg, rgba(16,27,45,.96), rgba(10,18,32,.96));
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 20px 60px rgba(0,0,0,.28);
    }}
    h1 {{ margin: 0 0 10px; font-size: 36px; letter-spacing: -.03em; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; }}
    p {{ color: var(--muted); line-height: 1.5; }}
    .badge {{ display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 999px; font-weight: 700; }}
    .badge.good {{ color: #06281d; background: var(--ok); }}
    .badge.bad {{ color: #3a0710; background: var(--danger); }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }}
    .metric {{ background: var(--panel2); border: 1px solid var(--border); border-radius: 14px; padding: 16px; }}
    .metric .value {{ font-size: 26px; font-weight: 800; margin-top: 6px; }}
    .metric .label {{ color: var(--muted); font-size: 13px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    button, a.button {{
      border: 1px solid #28405f;
      background: #12233a;
      color: var(--text);
      padding: 11px 14px;
      border-radius: 12px;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
    }}
    button.primary {{ background: var(--accent); color: #04221e; border-color: var(--accent); }}
    button.danger {{ background: #3b111b; border-color: #7f1d2d; color: #fecdd3; }}
    button.warning {{ background: #3b2a0b; border-color: #8a5b05; color: #fde68a; }}
    button:hover, a.button:hover {{ filter: brightness(1.12); }}
    .products {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 14px; }}
    .product {{ background: var(--panel2); border: 1px solid var(--border); border-radius: 14px; padding: 16px; }}
    .product-name {{ font-size: 18px; font-weight: 800; }}
    .price {{ color: var(--accent); font-weight: 800; margin: 8px 0 12px; }}
    pre {{
      min-height: 240px;
      max-height: 420px;
      overflow: auto;
      background: #050b14;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      color: #d9ecff;
      white-space: pre-wrap;
    }}
    .footer {{ margin-top: 18px; color: var(--muted); font-size: 13px; }}
    @media (max-width: 900px) {{ .hero, .grid, .products {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <section class="card">
        <span class="badge {mode_class}">Deploy mode: {state['deploy_mode'].upper()}</span>
        <h1>Mini Shop</h1>
        <p>A lightweight e-commerce demo app for your AIOps multi-agent triage system. Use this page to generate normal traffic, trigger a bad deploy, and create telemetry files for your agent to investigate.</p>
        <div class="actions">
          <button class="primary" onclick="loadProducts()">View products</button>
          <button onclick="generateLoad(20)">Generate normal traffic</button>
          <button class="warning" onclick="badDeploy()">Trigger bad deploy</button>
          <button onclick="goodDeploy()">Rollback to good deploy</button>
          <button class="danger" onclick="resetDemo()">Reset demo</button>
          <a class="button" href="/docs" target="_blank">Swagger API docs</a>
        </div>
      </section>
      <section class="card">
        <h2>Business health</h2>
        <div class="grid" style="grid-template-columns: 1fr 1fr;">
          <div class="metric"><div class="label">Transactions 24h</div><div class="value">{business['transactions_last_24h']}</div></div>
          <div class="metric"><div class="label">Drop vs last week</div><div class="value">{business['transaction_drop_percent']}%</div></div>
          <div class="metric"><div class="label">Failed transactions</div><div class="value">{business['failed_transactions_last_24h']}</div></div>
          <div class="metric"><div class="label">Revenue impact</div><div class="value">${business['estimated_revenue_impact']}</div></div>
        </div>
      </section>
    </div>

    <section class="card" style="margin-top: 18px;">
      <h2>Products</h2>
      <div id="products" class="products"></div>
    </section>

    <section class="card" style="margin-top: 18px;">
      <h2>Telemetry / response output</h2>
      <div class="actions">
        <button onclick="showHealth()">Health</button>
        <button onclick="showTelemetry()">Telemetry files</button>
        <button onclick="showBusinessMetrics()">Business metrics</button>
      </div>
      <pre id="output">Click an action above. Your agent can later read generated files under mini_shop/data/.</pre>
      <div class="footer">Generated files: data/logs.json, data/metrics.json, data/traces.json, data/business_metrics.json, data/service_dependencies.json, data/changes.json, data/alert.json</div>
    </section>
  </div>

<script>
const out = document.getElementById('output');
function show(obj) {{ out.textContent = JSON.stringify(obj, null, 2); }}
async function api(path, opts={{}}) {{
  const res = await fetch(path, opts);
  const text = await res.text();
  let data;
  try {{ data = JSON.parse(text); }} catch {{ data = text; }}
  if (!res.ok) throw data;
  return data;
}}
async function loadProducts() {{
  try {{
    const data = await api('/products');
    const products = document.getElementById('products');
    products.innerHTML = data.products.map(p => `
      <div class="product">
        <div class="product-name">${{p.name}}</div>
        <div class="price">$${{p.price.toFixed(2)}}</div>
        <button class="primary" onclick="checkout('${{p.id}}')">Checkout</button>
      </div>
    `).join('');
    show(data);
  }} catch(e) {{ show(e); }}
}}
async function checkout(productId) {{
  try {{
    const data = await api('/checkout', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{product_id:productId, quantity:1}})}});
    show(data);
  }} catch(e) {{ show(e); }}
}}
async function generateLoad(count) {{
  try {{ show(await api(`/admin/generate-load?count=${{count}}`, {{method:'POST'}})); }} catch(e) {{ show(e); }}
}}
async function badDeploy() {{
  try {{ show(await api('/admin/deploy?mode=bad')); setTimeout(()=>location.reload(), 800); }} catch(e) {{ show(e); }}
}}
async function goodDeploy() {{
  try {{ show(await api('/admin/deploy?mode=good')); setTimeout(()=>location.reload(), 800); }} catch(e) {{ show(e); }}
}}
async function resetDemo() {{
  try {{ show(await api('/admin/reset', {{method:'POST'}})); setTimeout(()=>location.reload(), 800); }} catch(e) {{ show(e); }}
}}
async function showHealth() {{ try {{ show(await api('/health')); }} catch(e) {{ show(e); }} }}
async function showTelemetry() {{ try {{ show(await api('/admin/telemetry')); }} catch(e) {{ show(e); }} }}
async function showBusinessMetrics() {{ try {{ const t = await api('/admin/telemetry'); show(t.business_metrics); }} catch(e) {{ show(e); }} }}
loadProducts();
</script>
</body>
</html>
"""


@app.get("/health")
def health() -> Dict[str, Any]:
    state = get_state()
    latency = 45 if state["deploy_mode"] == "good" else 650
    record_metric("service.health.latency", latency, "ms", "frontend")
    return {"status": "ok" if state["deploy_mode"] == "good" else "degraded", "deploy_mode": state["deploy_mode"]}


@app.get("/products")
def products() -> Dict[str, Any]:
    state = get_state()
    latency = random.randint(40, 90) if state["deploy_mode"] == "good" else random.randint(180, 450)
    record_metric("catalog.latency", latency, "ms", "catalog-api")
    log_event("INFO", "catalog-api", "Product catalog viewed", latency_ms=latency)
    record_trace("/products", [{"service": "frontend", "operation": "GET /products", "duration_ms": latency}], "ok")
    return {"products": PRODUCTS}


@app.post("/checkout")
def checkout(req: CheckoutRequest) -> Dict[str, Any]:
    state = get_state()
    product = next((p for p in PRODUCTS if p["id"] == req.product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    bad = state["deploy_mode"] == "bad"
    checkout_latency = random.randint(120, 260) if not bad else random.randint(1500, 4200)
    payment_latency = random.randint(80, 160) if not bad else random.randint(900, 2200)
    db_latency = random.randint(30, 90) if not bad else random.randint(350, 900)
    fail_probability = 0.02 if not bad else 0.35
    failed = random.random() < fail_probability

    time.sleep(min((checkout_latency + payment_latency + db_latency) / 10000, 0.4))

    state["transactions_today"] += 0 if failed else 1
    state["failed_transactions_today"] += 1 if failed else 0
    if not failed:
        state["revenue_today"] += product["price"] * req.quantity
    save_state(state)

    status = "error" if failed else "ok"
    level = "ERROR" if failed else "INFO"
    message = "Checkout failed due to payment timeout" if failed else "Checkout completed"
    log_event(level, "checkout-api", message, product_id=req.product_id, quantity=req.quantity, latency_ms=checkout_latency, error_type="payment_timeout" if failed else None)
    record_metric("checkout.latency", checkout_latency, "ms", "checkout-api")
    record_metric("payment.latency", payment_latency, "ms", "payment-api")
    record_metric("orders_db.latency", db_latency, "ms", "orders-db")
    record_metric("checkout.failure", 1 if failed else 0, "count", "checkout-api")
    record_trace("/checkout", [
        {"service": "frontend", "operation": "POST /checkout", "duration_ms": 40},
        {"service": "checkout-api", "operation": "validate cart", "duration_ms": checkout_latency},
        {"service": "payment-api", "operation": "authorize payment", "duration_ms": payment_latency},
        {"service": "orders-db", "operation": "write order", "duration_ms": db_latency},
        {"service": "notification-service", "operation": "send confirmation", "duration_ms": 60},
    ], status)
    refresh_business_metrics()
    maybe_create_alert()

    if failed:
        raise HTTPException(status_code=503, detail="Checkout failed: payment timeout")
    return {"status": "success", "order_id": str(uuid.uuid4()), "amount": product["price"] * req.quantity}


@app.get("/admin/deploy")
def deploy(mode: Literal["good", "bad"] = Query(...)) -> Dict[str, Any]:
    state = get_state()
    old = state["deploy_mode"]
    state["deploy_mode"] = mode
    state["deployment_version"] = "v1.0.1-bad" if mode == "bad" else "v1.0.2-rollback"
    state["last_deploy_at"] = now_iso()
    if mode == "bad":
        # create an immediate dip so the agent has useful business evidence even before load generation
        state["transactions_today"] = max(state["transactions_today"] - 24, 0)
        state["failed_transactions_today"] += 18
        state["revenue_today"] = max(state["revenue_today"] - 950, 0)
    save_state(state)

    change = {
        "ts": now_iso(),
        "service": "checkout-api",
        "change_type": "deployment",
        "from_mode": old,
        "to_mode": mode,
        "version": state["deployment_version"],
        "risk": "high" if mode == "bad" else "low",
        "summary": "Bad deployment introduced payment timeout behavior." if mode == "bad" else "Rollback restored stable checkout behavior.",
    }
    append_json(CHANGES_FILE, change)
    log_event("WARN" if mode == "bad" else "INFO", "deployment", change["summary"],
              **{k: v for k, v in change.items() if k != "service"})
    record_metric("deployment.event", 1, "count", "checkout-api", version=state["deployment_version"], mode=mode)
    refresh_business_metrics()
    maybe_create_alert()
    return {"status": "deployed", "mode": mode, "version": state["deployment_version"]}


@app.post("/admin/generate-load")
def generate_load(count: int = 20) -> Dict[str, Any]:
    failures = 0
    successes = 0
    for _ in range(max(1, min(count, 100))):
        req = CheckoutRequest(product_id=random.choice(PRODUCTS)["id"], quantity=random.randint(1, 2))
        try:
            checkout(req)
            successes += 1
        except HTTPException:
            failures += 1
    return {"attempted": count, "successes": successes, "failures": failures, "business_metrics": refresh_business_metrics()}


@app.get("/admin/telemetry")
def telemetry() -> Dict[str, Any]:
    return {
        "logs_file": str(JSON_LOG_FILE),
        "metrics_file": str(METRICS_FILE),
        "traces_file": str(TRACES_FILE),
        "business_metrics_file": str(BUSINESS_FILE),
        "dependencies_file": str(DEPS_FILE),
        "changes_file": str(CHANGES_FILE),
        "alert_file": str(ALERT_FILE),
        "business_metrics": refresh_business_metrics(),
    }


@app.get("/api/incident")
def api_incident() -> Dict[str, Any]:
    # TODO: replace file reads with the production telemetry provider when available.
    return _incident_payload()


@app.get("/api/rca")
def api_rca() -> Dict[str, Any]:
    # TODO: persist RCA snapshots outside process memory for multi-worker deployments.
    return _rca_payload()


@app.post("/api/triage/run")
def api_triage_run() -> Dict[str, str]:
    run_id = f"triage-{uuid.uuid4().hex[:10]}"
    TRIAGE_RUNS[run_id] = {
        "run_id": run_id,
        "thread_id": f"incident-{uuid.uuid4().hex[:8]}",
        "created_at": now_iso(),
        "status": "created",
        "timeline": [],
        "pause": None,
        "final": None,
        "decision_status": None,
    }
    return {"run_id": run_id}


@app.get("/api/triage/stream")
def api_triage_stream(run_id: str) -> StreamingResponse:
    if run_id not in TRIAGE_RUNS:
        raise HTTPException(status_code=404, detail="Unknown triage run")

    def events():
        run = TRIAGE_RUNS[run_id]
        run["status"] = "running"
        alert = read_json(ALERT_FILE, {}) or {
            "severity": "critical",
            "service": "checkout-api",
            "workflow": "checkout",
            "title": "Checkout latency and failed transactions increased",
        }
        try:
            graph = build_app("local")
            cfg = {"configurable": {"thread_id": run["thread_id"]}}
            for chunk in graph.stream({"alert": alert, "findings": [], "timeline": []}, cfg, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    pause = chunk["__interrupt__"][0].value
                    run["pause"] = pause
                    run["status"] = "awaiting_decision"
                    yield _sse({
                        "ts": datetime.now().strftime("%H:%M:%S"),
                        "agent": "rca",
                        "message": "Root cause synthesized; human approval required",
                        "stage_done": "rca",
                    })
                    yield _sse({"status": "awaiting_decision", "rca": pause}, event="done")
                    return
                for _node, upd in chunk.items():
                    if isinstance(upd, dict) and upd.get("timeline"):
                        for agent, ts, message in upd["timeline"]:
                            event = {
                                "ts": ts,
                                "agent": _stage_name(agent),
                                "message": str(message),
                                "stage_done": _stage_name(agent),
                            }
                            run["timeline"].append(event)
                            yield _sse(event)
            run["status"] = "completed"
            yield _sse({"status": "completed"}, event="done")
        except Exception as exc:
            run["status"] = "error"
            run["error"] = str(exc)
            yield _sse({"message": str(exc)}, event="error")
            yield _sse({"status": "error"}, event="done")

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/triage/reset")
def api_triage_reset() -> Dict[str, str]:
    TRIAGE_RUNS.clear()
    return {"status": "reset"}


@app.post("/api/telemetry/reload")
def api_telemetry_reload() -> Dict[str, Any]:
    # TODO: swap this refresh with live observability queries in production.
    refresh_business_metrics()
    maybe_create_alert()
    return _incident_payload()


@app.post("/api/triage/decision")
def api_triage_decision(req: TriageDecisionRequest) -> Dict[str, Any]:
    run = _latest_run()
    if not run:
        raise HTTPException(status_code=404, detail="No triage run is awaiting a decision")
    run["decision_status"] = req.decision
    run["decided_at"] = now_iso()

    if req.decision == "approve":
        run["status"] = "pending_rollback_confirmation"
        return {
            "status": "pending_confirmation",
            "message": "Approval recorded. Confirm rollback explicitly before any production change is attempted.",
            "approved_at": run["decided_at"],
        }

    final = "Fix rejected. RCA + recommended actions handed off to the team; no automated change was made."
    try:
        if run.get("pause"):
            graph = build_app("local")
            cfg = {"configurable": {"thread_id": run["thread_id"]}}
            for chunk in graph.stream(Command(resume="reject"), cfg, stream_mode="updates"):
                for _node, upd in chunk.items():
                    if isinstance(upd, dict) and upd.get("final"):
                        final = upd["final"]
                    if isinstance(upd, dict) and upd.get("timeline"):
                        for agent, ts, message in upd["timeline"]:
                            run["timeline"].append({
                                "ts": ts,
                                "agent": _stage_name(agent),
                                "message": str(message),
                                "stage_done": _stage_name(agent),
                            })
    except Exception as exc:
        run["decision_error"] = str(exc)
    run["status"] = "rejected"
    run["final"] = final
    return {"status": "rejected", "message": final}


@app.post("/api/triage/confirm-rollback")
def api_triage_confirm_rollback() -> Dict[str, Any]:
    run = _latest_run()
    if not run:
        raise HTTPException(status_code=404, detail="No triage run is available for rollback confirmation")
    if run.get("decision_status") != "approve" or run.get("status") != "pending_rollback_confirmation":
        raise HTTPException(status_code=409, detail="Rollback requires an approved triage decision first")

    confirmed_at = now_iso()
    rollback = deploy(mode="good")
    run["status"] = "rollback_applied"
    run["confirmed_at"] = confirmed_at
    run["confirmed_by"] = "dashboard-user"
    run["rollback"] = rollback
    run["final"] = "Rollback applied after explicit human confirmation."
    run["timeline"].append({
        "ts": datetime.now().strftime("%H:%M:%S"),
        "agent": "rca",
        "message": "rollback applied after second human confirmation",
        "stage_done": "rca",
    })
    return {
        "status": "rollback_applied",
        "message": "Rollback applied after explicit human confirmation.",
        "confirmed_at": confirmed_at,
        "confirmed_by": "dashboard-user",
        "rollback": rollback,
        "incident": _incident_payload(),
    }


@app.post("/admin/reset")
def reset() -> Dict[str, Any]:
    for path in [STATE_FILE, JSON_LOG_FILE, METRICS_FILE, TRACES_FILE, BUSINESS_FILE, CHANGES_FILE, ALERT_FILE, APP_LOG_FILE]:
        if path.exists():
            path.unlink()
    get_state()
    write_static_dependencies()
    refresh_business_metrics()
    log_event("INFO", "mini-shop", "Demo state reset")
    return {"status": "reset", "mode": get_state()["deploy_mode"]}
