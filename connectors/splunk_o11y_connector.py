from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from connectors.base import BaseObservabilityConnector
from connectors.schemas import (
    ConnectorResponse,
    ConnectorStatus,
    MetricSeries,
    ServiceDependency,
    TraceSummary,
    utc_now_iso,
)
from connectors.service_identity import ServiceIdentityMapper


class SplunkO11yConnector(BaseObservabilityConnector):
    """Splunk Observability Cloud connector for Sprint 5.

    Sprint 5 adds O11y as the owner for metrics, traces, and service dependency
    data. Logs and changes remain owned by Splunk Platform API.
    """

    source_platform = "splunk_o11y"

    def __init__(
        self,
        realm: Optional[str] = None,
        access_token: Optional[str] = None,
        api_base_url: Optional[str] = None,
        stream_base_url: Optional[str] = None,
        metric_names: Optional[Iterable[str]] = None,
        service_dimension: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        verify_ssl: Optional[bool] = None,
    ):
        self.realm = (realm if realm is not None else os.environ.get("SPLUNK_O11Y_REALM", "")).strip()
        self.access_token = (
            access_token if access_token is not None else os.environ.get("SPLUNK_O11Y_ACCESS_TOKEN", "")
        ).strip()
        self.api_base_url = (
            api_base_url if api_base_url is not None else os.environ.get("SPLUNK_O11Y_API_BASE_URL", "")
        ).strip() or (f"https://api.{self.realm}.signalfx.com" if self.realm else "")
        self.stream_base_url = (
            stream_base_url if stream_base_url is not None else os.environ.get("SPLUNK_O11Y_STREAM_BASE_URL", "")
        ).strip() or (f"https://stream.{self.realm}.signalfx.com" if self.realm else "")
        raw_metric_names = os.environ.get(
            "SPLUNK_O11Y_METRIC_NAMES",
            "checkout.latency,checkout.failure,deployment.event",
        )
        self.metric_names = list(metric_names) if metric_names is not None else [
            name.strip() for name in raw_metric_names.split(",") if name.strip()
        ]
        self.service_dimension = (
            service_dimension if service_dimension is not None else os.environ.get("SPLUNK_O11Y_SERVICE_DIMENSION", "sf_service")
        ).strip() or "sf_service"
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else self._env_float("SPLUNK_O11Y_TIMEOUT_SECONDS", 15.0)
        )
        self.verify_ssl = verify_ssl if verify_ssl is not None else self._env_bool("SPLUNK_O11Y_VERIFY_SSL", True)
        self.identity = ServiceIdentityMapper()

    def capabilities(self) -> Dict[str, bool]:
        return {
            "logs": False,
            "metrics": True,
            "traces": True,
            "changes": False,
            "business_metrics": False,
            "service_dependencies": True,
        }

    def get_alert(self) -> ConnectorResponse:
        return self._unsupported("alert", {})

    def get_logs(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._unsupported("logs", {"service": service, "since": since, "until": until})

    def get_metrics(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        platform_service = self.identity.platform_service(service, self.source_platform)
        canonical_service = self.identity.canonical(service)
        query = {
            "service": service,
            "canonical_service": canonical_service,
            "platform_service": platform_service,
            "since": since,
            "until": until,
            "metric_names": self.metric_names,
            "service_dimension": self.service_dimension,
        }
        if not self.metric_names:
            return self._no_data(query, "No SPLUNK_O11Y_METRIC_NAMES configured")

        program = "\n".join(
            (
                f'data("{self._escape_signalflow(metric)}", '
                f'filter=filter("{self._escape_signalflow(self.service_dimension)}", '
                f'"{self._escape_signalflow(platform_service)}")).publish(label="{self._escape_signalflow(metric)}")'
            )
            for metric in self.metric_names
        )
        payload = self._execute_signalflow(program=program, since=since, until=until, query=query)
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        payload.data = self._normalize_metric_series(payload.data, query, payload.raw_ref, payload.fetched_at, canonical_service or service)
        if not payload.data:
            payload.status = ConnectorStatus.NO_DATA
            payload.error_message = "Splunk O11y metric query returned no usable datapoints"
        return payload

    def get_traces(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        platform_service = self.identity.platform_service(service, self.source_platform)
        canonical_service = self.identity.canonical(service)
        query = {"service": service, "canonical_service": canonical_service, "platform_service": platform_service, "since": since, "until": until}
        path = os.environ.get("SPLUNK_O11Y_TRACES_PATH", "/v2/apm/traces")
        payload = self._request_json(
            method="GET",
            url=self._url(self.api_base_url, path, query),
            query={**query, "path": path},
            default=[],
        )
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        rows = self._list_from_payload(payload.data, keys=("traces", "results", "data"))
        payload.data = [
            self._trace_from_row(row, query, payload.raw_ref, payload.fetched_at, canonical_service or service)
            for row in rows
        ]
        if not payload.data:
            payload.status = ConnectorStatus.NO_DATA
            payload.error_message = "Splunk O11y trace query returned no traces"
        return payload

    def get_changes(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._unsupported("changes", {"service": service, "since": since, "until": until})

    def get_business_metrics(
        self,
        workflow: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> ConnectorResponse:
        return self._unsupported("business_metrics", {"workflow": workflow, "since": since, "until": until})

    def get_service_dependencies(self, service_or_workflow: Optional[str] = None) -> ConnectorResponse:
        platform_service = self.identity.platform_service(service_or_workflow, self.source_platform)
        query = {
            "service_or_workflow": service_or_workflow,
            "canonical_service_or_workflow": self.identity.canonical(service_or_workflow),
            "platform_service_or_workflow": platform_service,
        }
        path = os.environ.get("SPLUNK_O11Y_SERVICE_MAP_PATH", "/v2/apm/service-map")
        payload = self._request_json(
            method="GET",
            url=self._url(self.api_base_url, path, query),
            query={**query, "path": path},
            default={},
        )
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        payload.data = self._dependency_from_payload(payload.data, query, payload.raw_ref, payload.fetched_at)
        return payload

    def _execute_signalflow(
        self,
        program: str,
        since: Optional[str],
        until: Optional[str],
        query: Dict[str, Any],
    ) -> ConnectorResponse:
        url = f"{self.stream_base_url.rstrip('/')}/v2/signalflow/execute"
        body = urllib.parse.urlencode(
            {
                "program": program,
                **({"start": since} if since else {}),
                **({"stop": until} if until else {}),
            }
        ).encode("utf-8")
        return self._request_text(
            method="POST",
            url=url,
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            query={**query, "program": program},
            raw_parser=self._parse_signalflow_events,
        )

    def _request_json(self, method: str, url: str, query: Dict[str, Any], default: Any) -> ConnectorResponse:
        return self._request_text(
            method=method,
            url=url,
            body=None,
            headers={},
            query=query,
            raw_parser=lambda text: json.loads(text) if text else default,
        )

    def _request_text(
        self,
        method: str,
        url: str,
        body: Optional[bytes],
        headers: Dict[str, str],
        query: Dict[str, Any],
        raw_parser,
    ) -> ConnectorResponse:
        fetched_at = utc_now_iso()
        if not self.access_token or not (self.api_base_url or self.stream_base_url):
            return ConnectorResponse(
                status=ConnectorStatus.AUTH_FAILURE,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message="SPLUNK_O11Y_REALM and SPLUNK_O11Y_ACCESS_TOKEN are required for Splunk O11y",
            )
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "X-SF-TOKEN": self.access_token,
                "Accept": "application/json",
                **headers,
            },
            method=method,
        )
        try:
            context = None if self.verify_ssl else ssl._create_unverified_context()
            with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=context) as response:
                text = response.read().decode("utf-8")
            data = raw_parser(text)
        except urllib.error.HTTPError as exc:
            status = ConnectorStatus.AUTH_FAILURE if exc.code in {401, 403} else ConnectorStatus.UNAVAILABLE
            return ConnectorResponse(
                status=status,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"Splunk O11y HTTP {exc.code}: {exc.reason}",
            )
        except (TimeoutError, socket.timeout) as exc:
            return ConnectorResponse(
                status=ConnectorStatus.TIMEOUT,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"Splunk O11y request timed out: {exc}",
            )
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            status = ConnectorStatus.TIMEOUT if isinstance(reason, socket.timeout) else ConnectorStatus.UNAVAILABLE
            return ConnectorResponse(
                status=status,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"Splunk O11y unavailable: {reason}",
            )
        except (OSError, json.JSONDecodeError) as exc:
            return ConnectorResponse(
                status=ConnectorStatus.UNAVAILABLE,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"Splunk O11y response could not be read: {exc}",
            )
        if data in (None, [], {}):
            return ConnectorResponse(
                status=ConnectorStatus.NO_DATA,
                data=data,
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message="Splunk O11y returned no data",
            )
        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=data,
            source_platform=self.source_platform,
            query=query,
            raw_ref=url,
            fetched_at=fetched_at,
        )

    def _normalize_metric_series(
        self,
        rows: Any,
        query: Dict[str, Any],
        raw_ref: Optional[str],
        fetched_at: str,
        service: str,
    ) -> List[MetricSeries]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in self._list_from_payload(rows, keys=("data", "events", "results")):
            metric = self._first(row.get("metric") or row.get("label") or row.get("metric_name"))
            value = self._first(row.get("value"))
            ts = self._first(row.get("ts") or row.get("timestamp") or row.get("time"))
            if metric is None or value is None:
                continue
            grouped.setdefault(metric, []).append({"ts": ts, "value": value, "tags": row.get("dimensions", {})})
        return [
            MetricSeries(
                source_platform=self.source_platform,
                query={**query, "metric": metric},
                raw_ref=raw_ref,
                fetched_at=fetched_at,
                name=metric,
            service=self.identity.canonical(service),
                unit=None,
                points=points,
                aggregation="signalflow",
                raw=points,
            )
            for metric, points in grouped.items()
        ]

    def _trace_from_row(
        self,
        row: Dict[str, Any],
        query: Dict[str, Any],
        raw_ref: Optional[str],
        fetched_at: str,
        service: str,
    ) -> TraceSummary:
        spans = row.get("spans") or []
        bottleneck = max(spans, key=lambda span: span.get("duration_ms", span.get("duration", 0)) or 0) if spans else {}
        return TraceSummary(
            source_platform=self.source_platform,
            query=query,
            raw_ref=raw_ref,
            fetched_at=fetched_at,
            trace_id=row.get("trace_id") or row.get("traceId") or row.get("id"),
            ts=row.get("ts") or row.get("timestamp") or row.get("startTime"),
            endpoint=row.get("endpoint") or row.get("operation") or row.get("rootOperation"),
            status=row.get("status") or row.get("outcome"),
            total_duration_ms=row.get("total_duration_ms") or row.get("duration_ms") or row.get("duration"),
            spans=spans,
            bottleneck_service=self.identity.canonical(
                bottleneck.get("service") or bottleneck.get("service.name") or service
            ),
            bottleneck_operation=bottleneck.get("operation") or bottleneck.get("name"),
            bottleneck_ms=bottleneck.get("duration_ms") or bottleneck.get("duration"),
            raw=row,
        )

    def _dependency_from_payload(
        self,
        payload: Any,
        query: Dict[str, Any],
        raw_ref: Optional[str],
        fetched_at: str,
    ) -> ServiceDependency:
        raw = payload if isinstance(payload, dict) else {"services": payload}
        services = raw.get("services") or raw.get("nodes") or []
        edges = raw.get("dependencies") or raw.get("edges") or []
        names = self.identity.canonicalize_services([name for name in (self._service_name(item) for item in services) if name])
        dependencies: Dict[str, List[str]] = {}
        if isinstance(edges, dict):
            dependencies = {str(k): list(v or []) for k, v in edges.items()}
        else:
            for edge in edges:
                src = self._first(edge.get("source") or edge.get("from") or edge.get("parent"))
                dst = self._first(edge.get("target") or edge.get("to") or edge.get("child"))
                if src and dst:
                    dependencies.setdefault(src, []).append(dst)
        dependencies = self.identity.canonicalize_dependencies(dependencies)
        workflow = query.get("service_or_workflow")
        return ServiceDependency(
            source_platform=self.source_platform,
            query=query,
            raw_ref=raw_ref,
            fetched_at=fetched_at,
            workflow=workflow,
            critical_path=raw.get("critical_path") or raw.get("criticalPath") or [],
            business_kpis=raw.get("business_kpis") or [],
            services=names,
            dependencies=dependencies,
            raw=raw,
        )

    def _unsupported(self, signal: str, query: Dict[str, Any]) -> ConnectorResponse:
        return ConnectorResponse(
            status=ConnectorStatus.NO_DATA,
            data=[],
            source_platform=self.source_platform,
            query=query,
            raw_ref=None,
            fetched_at=utc_now_iso(),
            error_message=f"Splunk O11y connector does not provide {signal}",
        )

    def _no_data(self, query: Dict[str, Any], message: str) -> ConnectorResponse:
        return ConnectorResponse(
            status=ConnectorStatus.NO_DATA,
            data=[],
            source_platform=self.source_platform,
            query=query,
            raw_ref=None,
            fetched_at=utc_now_iso(),
            error_message=message,
        )

    @staticmethod
    def _parse_signalflow_events(text: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line.removeprefix("data:").strip()
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") not in {None, "data", "dataPoint"}:
                continue
            data = payload.get("data", payload)
            if isinstance(data, list):
                rows.extend(item for item in data if isinstance(item, dict))
            elif isinstance(data, dict):
                rows.append(data)
        return rows

    @staticmethod
    def _list_from_payload(payload: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [payload]
        return []

    @staticmethod
    def _url(base_url: str, path: str, query: Dict[str, Any]) -> str:
        params = {k: v for k, v in query.items() if v not in (None, "")}
        separator = "&" if "?" in path else "?"
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}{separator}{urllib.parse.urlencode(params)}"

    @staticmethod
    def _service_name(item: Dict[str, Any]) -> Optional[str]:
        return item.get("name") or item.get("service") or item.get("serviceName") or item.get("id")

    @staticmethod
    def _first(value: Any) -> Any:
        if isinstance(value, list):
            return value[0] if value else None
        return value

    @staticmethod
    def _escape_signalflow(value: Optional[str]) -> str:
        return (value or "").replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() not in {"0", "false", "no", "off"}

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        raw = os.environ.get(name)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default
