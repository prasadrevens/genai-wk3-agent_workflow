"""
aiops_tools.py — tools the agents call (v1.3: reads the live Mini Shop app).

Reads the JSON telemetry the Mini Shop FastAPI app writes to its data dir.
Point the tools at it with:
    export MINISHOP_DATA=/path/to/mini_shop/data      # default: ./mini_shop/data

Demo flow (run against the app first):
    curl -X POST http://localhost:8000/admin/reset
    curl -X POST "http://localhost:8000/admin/generate-load?count=20"
    curl "http://localhost:8000/admin/deploy?mode=bad"
    curl -X POST "http://localhost:8000/admin/generate-load?count=30"

Failure injection for the degrade path:  export AIOPS_FAIL=metrics,traces
The gated write (remediate) can really roll back the app if MINISHOP_URL is set.
"""

import os
import json
import urllib.request
from pathlib import Path

def resolve_data_dir() -> Path:
    """Resolve the Mini Shop telemetry data directory.

    Priority:
    1. MINISHOP_DATA env var
    2. ./mini_shop_with_ui/data
    3. ./mini_shop/data
    4. sibling/parent variants for common repo layouts
    """
    env = os.environ.get("MINISHOP_DATA")
    if env:
        return Path(env).expanduser().resolve()
    candidates = [
        Path("mini_shop_with_ui/data"),
        Path("mini_shop/data"),
        Path("../mini_shop_with_ui/data"),
        Path("../mini_shop/data"),
        Path(__file__).resolve().parent / "mini_shop_with_ui" / "data",
        Path(__file__).resolve().parent / "mini_shop" / "data",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    return Path("mini_shop_with_ui/data").resolve()


def data_dir() -> Path:
    return resolve_data_dir()


DATA_DIR = data_dir()


class ToolError(RuntimeError):
    """Simulated or real transient tool failure."""


def _should_fail(name):
    return name in {x.strip() for x in os.environ.get("AIOPS_FAIL", "").split(",") if x.strip()}


def _read(fname, default=None):
    p = data_dir() / fname
    if not p.exists():
        raise ToolError(f"{fname} not found in {data_dir()} — run the Mini Shop demo flow first")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default if default is not None else []


def _pctl(vals, p=95):
    if not vals:
        return 0
    s = sorted(vals)
    return s[min(len(s) - 1, int(round((p / 100) * (len(s) - 1))))]


# ---- read tools (autonomous) ---------------------------------------------- #
def get_logs(service="", since="", until="", level="", contains=""):
    if _should_fail("logs"):
        raise ToolError("log backend timed out")
    logs = _read("logs.json", [])
    hits = [l for l in logs
            if (not service or l.get("service") == service)
            and (not level or l.get("level") == level)
            and (not contains or contains.lower() in l.get("message", "").lower())]
    by_level = {}
    for l in hits:
        by_level[l.get("level", "?")] = by_level.get(l.get("level", "?"), 0) + 1
    err_types = sorted({l.get("error_type") for l in hits if l.get("error_type")})
    return {"total_matched": len(hits), "by_level": by_level, "error_types": err_types,
            "first_match_time": hits[0]["ts"] if hits else None,
            "sample": [{"ts": l.get("ts"), "level": l.get("level"),
                        "service": l.get("service"), "message": l.get("message")} for l in hits[:5]]}


def get_metrics(service="", metric="", since="", until=""):
    if _should_fail("metrics"):
        raise ToolError("metrics query returned 503")
    rows = _read("metrics.json", [])
    summaries = {}
    for r in rows:
        if service and r.get("service") != service:
            continue
        if metric and r.get("metric") != metric:
            continue
        name = r.get("metric")
        summaries.setdefault(name, {"values": [], "unit": r.get("unit"), "service": r.get("service")})
        summaries[name]["values"].append(r.get("value", 0))
    out = {}
    for name, agg in summaries.items():
        v = agg["values"]
        out[name] = {"count": len(v), "avg": round(sum(v) / len(v), 1) if v else 0,
                     "p95": _pctl(v, 95), "max": max(v) if v else 0,
                     "unit": agg["unit"], "service": agg["service"]}
    # surface the headline failure signal
    fails = sum(r.get("value", 0) for r in rows if r.get("metric") == "checkout.failure")
    return {"summaries": out, "checkout_failures": fails}


def get_traces(service="", since="", until=""):
    if _should_fail("traces"):
        raise ToolError("trace store unavailable")
    traces = _read("traces.json", [])
    checkout = [t for t in traces if t.get("endpoint") == "/checkout"] or traces
    if not checkout:
        return {"trace_count": 0}
    slowest = max(checkout, key=lambda t: t.get("total_duration_ms", 0))
    spans = slowest.get("spans", [])
    bottleneck = max(spans, key=lambda s: s.get("duration_ms", 0)) if spans else {}
    errors = sum(1 for t in checkout if t.get("status") == "error")
    return {"trace_count": len(checkout), "error_traces": errors,
            "slowest_total_ms": slowest.get("total_duration_ms"),
            "bottleneck_service": bottleneck.get("service"),
            "bottleneck_operation": bottleneck.get("operation"),
            "bottleneck_ms": bottleneck.get("duration_ms"),
            "critical_path": [s.get("service") for s in spans]}


def get_changes(service="", since="", until=""):
    if _should_fail("changes"):
        raise ToolError("change feed unavailable")
    changes = _read("changes.json", [])
    return sorted(changes, key=lambda d: d.get("ts", ""), reverse=True)


def get_business_metrics(service="", since="", until=""):
    if _should_fail("business"):
        raise ToolError("business metrics warehouse unavailable")
    bm = _read("business_metrics.json", {})
    # NOTE: transaction_drop_percent can be masked by load generation; the reliable
    # degradation signals are payment_success_rate_percent and failed transactions.
    return {"workflow": bm.get("workflow"),
            "transactions_last_24h": bm.get("transactions_last_24h"),
            "transactions_same_period_last_week": bm.get("transactions_same_period_last_week"),
            "transaction_drop_percent": bm.get("transaction_drop_percent"),
            "failed_transactions_last_24h": bm.get("failed_transactions_last_24h"),
            "payment_success_rate_percent": bm.get("payment_success_rate_percent"),
            "revenue_last_24h": bm.get("revenue_last_24h"),
            "estimated_revenue_impact": bm.get("estimated_revenue_impact"),
            "summary": bm.get("business_summary")}


def get_service_dependencies(workflow="checkout", service=""):
    if _should_fail("dependencies"):
        raise ToolError("service map unavailable")
    deps = _read("service_dependencies.json", {})
    wf = (deps.get("business_workflows", {}) or {}).get(workflow, {})
    return {"workflow": workflow,
            "critical_path": wf.get("critical_path", []),
            "business_kpis": wf.get("business_kpis", []),
            "services": list((deps.get("services", {}) or {}).keys()),
            "dependencies": deps.get("services", {})}


# Runbooks aren't produced by the app — keep a tiny library here.
_RUNBOOKS = [
    {"id": "RB-CHK-01", "issue_type": "checkout_payment_timeout",
     "symptoms": ["payment", "timeout", "503", "checkout latency", "failed transaction",
                  "payment_success_rate", "bad deployment"],
     "remediation": "Roll back checkout-api to the last good version (deploy mode=good); "
                    "verify payment-api timeouts clear."},
    {"id": "RB-CHK-02", "issue_type": "checkout_latency",
     "symptoms": ["p95", "latency", "checkout", "slow"],
     "remediation": "Inspect the most recent deployment to checkout-api and roll back if correlated."},
]


def get_runbook(issue_type="", query=""):
    if _should_fail("runbook"):
        raise ToolError("runbook index unavailable")
    q = f"{issue_type} {query}".lower()
    scored = sorted(_RUNBOOKS, key=lambda b: (b["issue_type"] in q) * 3
                    + sum(1 for s in b["symptoms"] if s.lower() in q), reverse=True)
    return scored[0] if scored else {}


# ---- gated write (only from remediate, post-approval) --------------------- #
def remediate(action=""):
    """If MINISHOP_URL is set, actually roll the app back to good mode (the real
    corrective action). Otherwise simulate."""
    url = os.environ.get("MINISHOP_URL")
    if url:
        try:
            req = urllib.request.Request(f"{url.rstrip('/')}/admin/deploy?mode=good", method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                body = json.loads(r.read().decode())
            return {"status": "applied", "action": action, "rollback": body}
        except Exception as e:
            return {"status": "failed", "action": action, "error": str(e)}
    return {"status": "applied", "action": action, "note": "SIMULATED — set MINISHOP_URL to roll back for real"}


TOOLS = {"get_logs": get_logs, "get_metrics": get_metrics, "get_traces": get_traces,
         "get_changes": get_changes, "get_business_metrics": get_business_metrics,
         "get_service_dependencies": get_service_dependencies, "get_runbook": get_runbook,
         "remediate": remediate}
