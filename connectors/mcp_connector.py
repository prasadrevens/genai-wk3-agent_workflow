from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from connectors.base import BaseObservabilityConnector
from connectors.schemas import (
    BusinessMetric,
    ChangeEvent,
    ConnectorResponse,
    ConnectorStatus,
    LogEvent,
    MetricSeries,
    ServiceDependency,
    TraceSummary,
    utc_now_iso,
)
from connectors.service_identity import ServiceIdentityMapper


class McpConnector(BaseObservabilityConnector):
    """HTTP bridge adapter for MCP-backed observability tools.

    Sprint 12 intentionally keeps MCP behind the same connector interface used
    by Mini Shop, Splunk API, and Splunk O11y. Agents still call signal tools;
    this adapter translates signal requests into MCP tool calls.
    """

    source_platform = "mcp"

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        tool_prefix: Optional[str] = None,
    ):
        self.base_url = (base_url if base_url is not None else os.environ.get("MCP_BRIDGE_URL", "")).strip()
        self.token = (token if token is not None else os.environ.get("MCP_BRIDGE_TOKEN", "")).strip()
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.environ.get("MCP_BRIDGE_TIMEOUT_SECONDS", "10"))
        )
        self.tool_prefix = (
            tool_prefix if tool_prefix is not None else os.environ.get("MCP_OBSERVABILITY_TOOL_PREFIX", "")
        ).strip()
        self.identity = ServiceIdentityMapper()

    def capabilities(self) -> Dict[str, bool]:
        return {
            "logs": True,
            "metrics": True,
            "traces": True,
            "changes": True,
            "business_metrics": True,
            "service_dependencies": True,
        }

    def get_alert(self) -> ConnectorResponse:
        return self._normalize_alert(self._call_tool("get_alert", {}))

    def get_logs(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._normalize_logs(
            self._call_tool("get_logs", {"service": service, "since": since, "until": until})
        )

    def get_metrics(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._normalize_metrics(
            self._call_tool("get_metrics", {"service": service, "since": since, "until": until}),
            service=service,
        )

    def get_traces(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._normalize_traces(
            self._call_tool("get_traces", {"service": service, "since": since, "until": until})
        )

    def get_changes(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._normalize_changes(
            self._call_tool("get_changes", {"service": service, "since": since, "until": until})
        )

    def get_business_metrics(
        self,
        workflow: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> ConnectorResponse:
        return self._normalize_business_metrics(
            self._call_tool("get_business_metrics", {"workflow": workflow, "since": since, "until": until})
        )

    def get_service_dependencies(self, service_or_workflow: Optional[str] = None) -> ConnectorResponse:
        return self._normalize_dependencies(
            self._call_tool("get_service_dependencies", {"service_or_workflow": service_or_workflow})
        )

    def _call_tool(self, tool: str, arguments: Dict[str, Any]) -> ConnectorResponse:
        fetched_at = utc_now_iso()
        tool_name = f"{self.tool_prefix}{tool}"
        query = {"tool": tool_name, "arguments": arguments}
        if not self.base_url or not self.token:
            return ConnectorResponse(
                status=ConnectorStatus.AUTH_FAILURE,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=None,
                fetched_at=fetched_at,
                error_message="MCP_BRIDGE_URL and MCP_BRIDGE_TOKEN are required for AIOPS_DATA_SOURCE=mcp",
            )

        url = f"{self.base_url.rstrip('/')}/tools/{tool_name}"
        body = json.dumps({"arguments": arguments}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            status = ConnectorStatus.AUTH_FAILURE if exc.code in {401, 403} else ConnectorStatus.UNAVAILABLE
            return ConnectorResponse(
                status=status,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"MCP bridge HTTP {exc.code}: {exc.reason}",
            )
        except (TimeoutError, socket.timeout) as exc:
            return ConnectorResponse(
                status=ConnectorStatus.TIMEOUT,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"MCP bridge timed out: {exc}",
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            return ConnectorResponse(
                status=ConnectorStatus.UNAVAILABLE,
                data=[],
                source_platform=self.source_platform,
                query=query,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"MCP bridge unavailable: {exc}",
            )

        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=data,
            source_platform=self.source_platform,
            query=query,
            raw_ref=url,
            fetched_at=fetched_at,
        )

    def _normalize_logs(self, response: ConnectorResponse) -> ConnectorResponse:
        rows = self._rows(response)
        if response.status != ConnectorStatus.SUCCESS:
            return response
        if not rows:
            return self._no_data(response)
        response.data = [
            LogEvent(
                source_platform=self.source_platform,
                query=response.query,
                raw_ref=response.raw_ref,
                fetched_at=response.fetched_at,
                ts=row.get("ts") or row.get("timestamp"),
                level=row.get("level") or row.get("severity"),
                service=self.identity.canonical(row.get("service")),
                message=row.get("message") or row.get("_raw"),
                error_type=row.get("error_type"),
                raw=row,
            )
            for row in rows
        ]
        return response

    def _normalize_metrics(self, response: ConnectorResponse, service: str) -> ConnectorResponse:
        rows = self._rows(response)
        if response.status != ConnectorStatus.SUCCESS:
            return response
        if not rows:
            return self._no_data(response)
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            by_name.setdefault(str(row.get("metric") or row.get("name") or "unknown"), []).append(row)
        response.data = [
            MetricSeries(
                source_platform=self.source_platform,
                query=response.query,
                raw_ref=response.raw_ref,
                fetched_at=response.fetched_at,
                name=name,
                service=self.identity.canonical(rows_for_metric[0].get("service") or service),
                unit=rows_for_metric[0].get("unit"),
                points=[
                    {"ts": row.get("ts") or row.get("timestamp"), "value": row.get("value")}
                    for row in rows_for_metric
                ],
                raw=rows_for_metric,
            )
            for name, rows_for_metric in by_name.items()
        ]
        return response

    def _normalize_traces(self, response: ConnectorResponse) -> ConnectorResponse:
        rows = self._rows(response)
        if response.status != ConnectorStatus.SUCCESS:
            return response
        if not rows:
            return self._no_data(response)
        response.data = [
            TraceSummary(
                source_platform=self.source_platform,
                query=response.query,
                raw_ref=response.raw_ref,
                fetched_at=response.fetched_at,
                trace_id=row.get("trace_id") or row.get("traceId"),
                ts=row.get("ts") or row.get("timestamp"),
                endpoint=row.get("endpoint") or row.get("rootOperation"),
                status=row.get("status"),
                total_duration_ms=row.get("total_duration_ms") or row.get("duration"),
                spans=row.get("spans") or [],
                bottleneck_service=self.identity.canonical(row.get("bottleneck_service")),
                bottleneck_operation=row.get("bottleneck_operation"),
                bottleneck_ms=row.get("bottleneck_ms"),
                raw=row,
            )
            for row in rows
        ]
        return response

    def _normalize_changes(self, response: ConnectorResponse) -> ConnectorResponse:
        rows = self._rows(response)
        if response.status != ConnectorStatus.SUCCESS:
            return response
        if not rows:
            return self._no_data(response)
        response.data = [
            ChangeEvent(
                source_platform=self.source_platform,
                query=response.query,
                raw_ref=response.raw_ref,
                fetched_at=response.fetched_at,
                ts=row.get("ts") or row.get("timestamp"),
                service=self.identity.canonical(row.get("service")),
                change_type=row.get("change_type") or row.get("event_type"),
                version=row.get("version"),
                risk=row.get("risk"),
                summary=row.get("summary") or row.get("message"),
                raw=row,
            )
            for row in rows
        ]
        return response

    def _normalize_business_metrics(self, response: ConnectorResponse) -> ConnectorResponse:
        rows = self._rows(response)
        if response.status != ConnectorStatus.SUCCESS:
            return response
        if not rows:
            return self._no_data(response)
        row = rows[0]
        response.data = BusinessMetric(
            source_platform=self.source_platform,
            query=response.query,
            raw_ref=response.raw_ref,
            fetched_at=response.fetched_at,
            workflow=row.get("workflow"),
            transactions_last_24h=row.get("transactions_last_24h"),
            transactions_same_period_last_week=row.get("transactions_same_period_last_week"),
            transaction_drop_percent=row.get("transaction_drop_percent"),
            failed_transactions_last_24h=row.get("failed_transactions_last_24h"),
            payment_success_rate_percent=row.get("payment_success_rate_percent"),
            revenue_last_24h=row.get("revenue_last_24h"),
            estimated_revenue_impact=row.get("estimated_revenue_impact"),
            summary=row.get("summary") or row.get("business_summary"),
            raw=row,
        )
        return response

    def _normalize_dependencies(self, response: ConnectorResponse) -> ConnectorResponse:
        rows = self._rows(response)
        if response.status != ConnectorStatus.SUCCESS:
            return response
        if not rows:
            return self._no_data(response)
        payload = rows[0]
        dependencies = payload.get("dependencies") or payload.get("services") or {}
        response.data = ServiceDependency(
            source_platform=self.source_platform,
            query=response.query,
            raw_ref=response.raw_ref,
            fetched_at=response.fetched_at,
            workflow=payload.get("workflow"),
            critical_path=payload.get("critical_path") or [],
            business_kpis=payload.get("business_kpis") or [],
            services=payload.get("service_names") or list(dependencies.keys()),
            dependencies=self.identity.canonicalize_dependencies(dependencies),
            raw=payload,
        )
        return response

    def _normalize_alert(self, response: ConnectorResponse) -> ConnectorResponse:
        rows = self._rows(response)
        if response.status != ConnectorStatus.SUCCESS:
            return response
        if not rows:
            return self._no_data(response)
        response.data = rows[0]
        return response

    def _rows(self, response: ConnectorResponse) -> List[Dict[str, Any]]:
        data = response.data
        if isinstance(data, dict):
            for key in ("data", "results", "rows", "events"):
                if key in data:
                    data = data[key]
                    break
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            return [data]
        return []

    def _no_data(self, response: ConnectorResponse) -> ConnectorResponse:
        return ConnectorResponse(
            status=ConnectorStatus.NO_DATA,
            data=[],
            source_platform=self.source_platform,
            query=response.query,
            raw_ref=response.raw_ref,
            fetched_at=response.fetched_at,
            error_message=f"MCP tool {response.query.get('tool')} returned no data",
        )
