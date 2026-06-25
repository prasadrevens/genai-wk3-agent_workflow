from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class SplunkO11yEmitter:
    """Best-effort Mini Shop telemetry emitter for Splunk Observability Cloud.

    Local JSON telemetry remains the source of truth for the demo. This emitter
    mirrors metrics and traces to Splunk O11y only when credentials are present.
    It never raises into request handlers.
    """

    def __init__(self) -> None:
        self.realm = os.environ.get("SPLUNK_O11Y_REALM", "").strip()
        self.token = os.environ.get("SPLUNK_O11Y_ACCESS_TOKEN", "").strip()
        self.service_name = os.environ.get("SPLUNK_O11Y_SERVICE_NAME", "checkout-api").strip() or "checkout-api"
        self.environment = os.environ.get("SPLUNK_O11Y_ENVIRONMENT", "demo").strip() or "demo"
        self.timeout_seconds = _env_float("SPLUNK_O11Y_INGEST_TIMEOUT_SECONDS", 3.0)
        self.enabled = bool(self.realm and self.token)
        ingest = os.environ.get("SPLUNK_O11Y_INGEST_BASE_URL", "").strip()
        self.ingest_base_url = ingest or (f"https://ingest.{self.realm}.signalfx.com" if self.realm else "")
        self.metric_path = os.environ.get("SPLUNK_O11Y_METRIC_PATH", "/v2/datapoint").strip() or "/v2/datapoint"
        self.trace_path = os.environ.get("SPLUNK_O11Y_TRACE_PATH", "/v2/trace").strip() or "/v2/trace"
        self.metrics_sent = 0
        self.traces_sent = 0
        self.last_error: Optional[str] = None
        self.last_metric_error: Optional[str] = None
        self.last_trace_error: Optional[str] = None
        self.last_metric_url: Optional[str] = None
        self.last_trace_url: Optional[str] = None
        self.trace_path_candidates = [
            path.strip()
            for path in os.environ.get(
                "SPLUNK_O11Y_TRACE_PATH_CANDIDATES",
                f"{self.trace_path},/v1/trace,/api/v2/spans",
            ).split(",")
            if path.strip()
        ]

    def emit_metric(self, name: str, value: float, unit: str, service: str, tags: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        dimensions = self._dimensions(service, tags)
        dimensions["unit"] = unit
        payload = {
            "gauge": [
                {
                    "metric": name,
                    "value": value,
                    "timestamp": int(time.time() * 1000),
                    "dimensions": dimensions,
                }
            ]
        }
        urls = self._candidate_urls(self.metric_path)
        self.last_metric_url = urls[0]
        ok, error = self._post_json_with_fallback(urls, payload)
        self.last_metric_error = error
        if ok:
            self.metrics_sent += 1

    def emit_trace(self, endpoint: str, spans: List[Dict[str, Any]], status: str, trace_id: str) -> None:
        if not self.enabled:
            return
        now_micros = int(time.time() * 1_000_000)
        parent_id: Optional[str] = None
        zipkin_spans = []
        for span in spans:
            span_id = _span_id()
            duration_ms = float(span.get("duration_ms", 0) or 0)
            service = str(span.get("service") or self.service_name)
            operation = str(span.get("operation") or endpoint)
            item = {
                "traceId": _trace_id(trace_id),
                "id": span_id,
                "name": operation,
                "timestamp": now_micros,
                "duration": max(int(duration_ms * 1000), 1),
                "localEndpoint": {"serviceName": service},
                "tags": {
                    "deployment.environment": self.environment,
                    "http.route": endpoint,
                    "status": status,
                    "duration_ms": str(duration_ms),
                },
            }
            if parent_id:
                item["parentId"] = parent_id
            parent_id = span_id
            zipkin_spans.append(item)
        urls = []
        for path in self.trace_path_candidates:
            urls.extend(self._candidate_urls(path))
        self.last_trace_url = urls[0]
        ok, error = self._post_json_with_fallback(urls, zipkin_spans)
        self.last_trace_error = error
        if ok:
            self.traces_sent += 1

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "realm": self.realm or None,
            "token_configured": bool(self.token),
            "service_name": self.service_name,
            "environment": self.environment,
            "ingest_base_url": self.ingest_base_url or None,
            "metric_path": self.metric_path,
            "trace_path": self.trace_path,
            "trace_path_candidates": self.trace_path_candidates,
            "metrics_sent": self.metrics_sent,
            "traces_sent": self.traces_sent,
            "last_error": self.last_error,
            "last_metric_error": self.last_metric_error,
            "last_trace_error": self.last_trace_error,
            "last_metric_url": self.last_metric_url,
            "last_trace_url": self.last_trace_url,
        }

    def _candidate_urls(self, path: str) -> List[str]:
        base = self.ingest_base_url.rstrip("/")
        normalized = path.strip() or "/"
        primary = f"{base}/{normalized.lstrip('/')}"
        if primary.endswith("/"):
            return [primary, primary.rstrip("/")]
        return [primary, f"{primary}/"]

    def _post_json_with_fallback(self, urls: List[str], payload: Any) -> tuple[bool, Optional[str]]:
        last_error = None
        for url in urls:
            ok, error = self._post_json(url, payload)
            if ok:
                return True, None
            last_error = error
            if error and "HTTP 404" not in error:
                break
        return False, last_error

    def _dimensions(self, service: str, tags: Dict[str, Any]) -> Dict[str, str]:
        dimensions = {
            "sf_service": service,
            "service.name": service,
            "deployment.environment": self.environment,
        }
        for key, value in tags.items():
            if value is not None:
                dimensions[str(key)] = str(value)
        return dimensions

    def _post_json(self, url: str, payload: Any) -> tuple[bool, Optional[str]]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-SF-TOKEN": self.token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response.read()
            self.last_error = None
            return True, None
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:
                detail = ""
            self.last_error = f"HTTP {exc.code}: {exc.reason}" + (f" - {detail}" if detail else "")
            return False, self.last_error
        except (OSError, urllib.error.URLError) as exc:
            self.last_error = f"O11y ingest request failed: {exc}"
            return False, self.last_error


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _trace_id(value: str) -> str:
    cleaned = "".join(ch for ch in value.lower() if ch in "0123456789abcdef")
    if len(cleaned) >= 16:
        return cleaned[-32:].rjust(16, "0")
    return f"{random.getrandbits(128):032x}"


def _span_id() -> str:
    return f"{random.getrandbits(64):016x}"
