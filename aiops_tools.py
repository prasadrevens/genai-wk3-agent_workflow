"""
aiops_tools.py — tools the agents call.

Sprint 1 connector architecture:
    Agents -> Tools -> Connector Interface -> Connector Implementations -> Data Sources

The public tool function names and return shapes are intentionally preserved for
the existing LangGraph agents. Platform-specific Mini Shop file reads now live
behind connectors/minishop_connector.py.
"""

from __future__ import annotations

import os
import urllib.request
import json
from pathlib import Path
from typing import Any

from connectors.factory import get_connector
from connectors.minishop_connector import MiniShopConnector
from connectors.schemas import ConnectorResponse, ConnectorStatus
from connectors.time_window import apply_time_window, resolve_time_window


def resolve_data_dir() -> Path:
    """Preserve the legacy helper while delegating Mini Shop path rules to the connector."""
    return MiniShopConnector.resolve_data_dir()


def data_dir() -> Path:
    return resolve_data_dir()


DATA_DIR = data_dir()


class ToolError(RuntimeError):
    """Simulated, connector, or real transient tool failure."""


def _should_fail(name):
    return name in {x.strip() for x in os.environ.get("AIOPS_FAIL", "").split(",") if x.strip()}


def _connector() -> Any:
    try:
        return get_connector()
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def _require_success(response: ConnectorResponse, signal: str) -> Any:
    if response.status == ConnectorStatus.SUCCESS:
        return response.data
    message = response.error_message or f"{signal} connector returned {response.status.value}"
    raise ToolError(message)


def _window(since="", until="") -> tuple[str, str]:
    return apply_time_window(since=since or None, until=until or None)


def _pctl(vals, p=95):
    if not vals:
        return 0
    s = sorted(vals)
    return s[min(len(s) - 1, int(round((p / 100) * (len(s) - 1))))]


def _metric_points(series) -> list[dict]:
    rows = getattr(series, "raw", None)
    if rows:
        return rows
    return [
        {
            "ts": point.get("ts"),
            "metric": getattr(series, "name", None),
            "value": point.get("value"),
            "unit": getattr(series, "unit", None),
            "service": getattr(series, "service", None),
            "tags": point.get("tags", {}),
        }
        for point in getattr(series, "points", [])
    ]


# ---- read tools (autonomous) ---------------------------------------------- #
def get_logs(service="", since="", until="", level="", contains=""):
    if _should_fail("logs"):
        raise ToolError("log backend timed out")
    since, until = _window(since, until)
    rows = _require_success(_connector().get_logs(service=service, since=since, until=until), "logs")
    hits = [
        log
        for log in rows
        if (not level or log.level == level)
        and (not contains or contains.lower() in (log.message or "").lower())
    ]
    by_level = {}
    for log in hits:
        by_level[log.level or "?"] = by_level.get(log.level or "?", 0) + 1
    err_types = sorted({log.error_type for log in hits if log.error_type})
    return {
        "total_matched": len(hits),
        "by_level": by_level,
        "error_types": err_types,
        "first_match_time": hits[0].ts if hits else None,
        "sample": [
            {"ts": log.ts, "level": log.level, "service": log.service, "message": log.message}
            for log in hits[:5]
        ],
    }


def get_metrics(service="", metric="", since="", until=""):
    if _should_fail("metrics"):
        raise ToolError("metrics query returned 503")
    since, until = _window(since, until)
    series_list = _require_success(_connector().get_metrics(service=service, since=since, until=until), "metrics")
    rows = []
    for series in series_list:
        if metric and series.name != metric:
            continue
        rows.extend(_metric_points(series))
    summaries = {}
    for row in rows:
        name = row.get("metric")
        summaries.setdefault(name, {"values": [], "unit": row.get("unit"), "service": row.get("service")})
        summaries[name]["values"].append(row.get("value", 0))
    out = {}
    for name, agg in summaries.items():
        v = agg["values"]
        out[name] = {
            "count": len(v),
            "avg": round(sum(v) / len(v), 1) if v else 0,
            "p95": _pctl(v, 95),
            "max": max(v) if v else 0,
            "unit": agg["unit"],
            "service": agg["service"],
        }
    fails = sum(row.get("value", 0) for row in rows if row.get("metric") == "checkout.failure")
    return {"summaries": out, "checkout_failures": fails}


def get_traces(service="", since="", until=""):
    if _should_fail("traces"):
        raise ToolError("trace store unavailable")
    since, until = _window(since, until)
    traces = _require_success(_connector().get_traces(service=service, since=since, until=until), "traces")
    checkout = [trace for trace in traces if trace.endpoint == "/checkout"] or traces
    if not checkout:
        return {"trace_count": 0}
    slowest = max(checkout, key=lambda trace: trace.total_duration_ms or 0)
    spans = slowest.spans or []
    errors = sum(1 for trace in checkout if trace.status == "error")
    return {
        "trace_count": len(checkout),
        "error_traces": errors,
        "slowest_total_ms": slowest.total_duration_ms,
        "bottleneck_service": slowest.bottleneck_service,
        "bottleneck_operation": slowest.bottleneck_operation,
        "bottleneck_ms": slowest.bottleneck_ms,
        "critical_path": [span.get("service") for span in spans],
    }


def get_changes(service="", since="", until=""):
    if _should_fail("changes"):
        raise ToolError("change feed unavailable")
    since, until = _window(since, until)
    changes = _require_success(_connector().get_changes(service=service, since=since, until=until), "changes")
    return [
        {
            "ts": change.ts,
            "service": change.service,
            "change_type": change.change_type,
            "version": change.version,
            "risk": change.risk,
            "summary": change.summary,
            **{k: v for k, v in change.raw.items() if k not in {"ts", "service", "change_type", "version", "risk", "summary"}},
        }
        for change in changes
    ]


def get_business_metrics(service="", since="", until=""):
    if _should_fail("business"):
        raise ToolError("business metrics warehouse unavailable")
    since, until = _window(since, until)
    bm = _require_success(
        _connector().get_business_metrics(workflow=None, since=since, until=until),
        "business metrics",
    )
    # NOTE: transaction_drop_percent can be masked by load generation; the reliable
    # degradation signals are payment_success_rate_percent and failed transactions.
    return {
        "workflow": bm.workflow,
        "transactions_last_24h": bm.transactions_last_24h,
        "transactions_same_period_last_week": bm.transactions_same_period_last_week,
        "transaction_drop_percent": bm.transaction_drop_percent,
        "failed_transactions_last_24h": bm.failed_transactions_last_24h,
        "payment_success_rate_percent": bm.payment_success_rate_percent,
        "revenue_last_24h": bm.revenue_last_24h,
        "estimated_revenue_impact": bm.estimated_revenue_impact,
        "summary": bm.summary,
    }


def get_service_dependencies(workflow="checkout", service=""):
    if _should_fail("dependencies"):
        raise ToolError("service map unavailable")
    deps = _require_success(
        _connector().get_service_dependencies(service_or_workflow=workflow or service),
        "service dependencies",
    )
    return {
        "workflow": deps.workflow or workflow,
        "critical_path": deps.critical_path,
        "business_kpis": deps.business_kpis,
        "services": deps.services,
        "dependencies": deps.dependencies,
    }


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
    """If MINISHOP_URL is set, actually roll the app back to good mode. Otherwise simulate."""
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


def get_time_window(since="", until=""):
    window = resolve_time_window(since=since or None, until=until or None)
    return {"since": window.since, "until": window.until, "source": window.source}
