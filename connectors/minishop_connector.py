from __future__ import annotations

import json
import os
from dataclasses import asdict
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from connectors.base import BaseObservabilityConnector
from connectors.schemas import (
    AlertEvent,
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


class MiniShopConnector(BaseObservabilityConnector):
    source_platform = "minishop"

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or self.resolve_data_dir()
        self.identity = ServiceIdentityMapper()

    @staticmethod
    def resolve_data_dir() -> Path:
        env = os.environ.get("MINISHOP_DATA")
        if env:
            return Path(env).expanduser().resolve()
        return Path("mini_shop_with_ui/data").resolve()

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
        query: Dict[str, Any] = {}
        payload = self._read_json("alert.json", query)
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        raw = payload.data or {}
        payload.data = AlertEvent(
            source_platform=self.source_platform,
            query=query,
            raw_ref=payload.raw_ref,
            fetched_at=payload.fetched_at,
            incident_id=raw.get("incident_id"),
            ts=raw.get("ts"),
            severity=raw.get("severity"),
            service=self.identity.canonical(raw.get("service")),
            workflow=raw.get("workflow"),
            title=raw.get("title"),
            symptoms=raw.get("symptoms") or [],
            business_impact=raw.get("business_impact") or {},
            raw=raw,
        )
        return payload

    def get_logs(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        query = {"service": service, "since": since, "until": until}
        payload = self._read_json("logs.json", query, default=[])
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        rows = self._filter_by_service_and_time(payload.data or [], service, since, until)
        payload.data = [
            LogEvent(
                source_platform=self.source_platform,
                query=query,
                raw_ref=payload.raw_ref,
                fetched_at=payload.fetched_at,
                ts=row.get("ts"),
                level=row.get("level"),
                service=self.identity.canonical(row.get("service")),
                message=row.get("message"),
                error_type=row.get("error_type"),
                raw=row,
            )
            for row in rows
        ]
        return payload

    def get_metrics(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        query = {"service": service, "since": since, "until": until}
        payload = self._read_json("metrics.json", query, default=[])
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        rows = self._filter_by_service_and_time(payload.data or [], service, since, until)
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row.get("metric") or "unknown", []).append(row)
        payload.data = [
            MetricSeries(
                source_platform=self.source_platform,
                query={**query, "metric": metric},
                raw_ref=payload.raw_ref,
                fetched_at=payload.fetched_at,
                name=metric,
                service=self.identity.canonical(points[0].get("service") if points else service),
                unit=points[0].get("unit") if points else None,
                points=[{"ts": p.get("ts"), "value": p.get("value"), "tags": p.get("tags", {})} for p in points],
                aggregation="raw",
                raw=points,
            )
            for metric, points in grouped.items()
        ]
        return payload

    def get_traces(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        query = {"service": service, "since": since, "until": until}
        payload = self._read_json("traces.json", query, default=[])
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        rows = self._filter_by_time(payload.data or [], since, until)
        summaries = []
        for row in rows:
            spans = row.get("spans", []) or []
            if service and not any(span.get("service") == service for span in spans):
                continue
            bottleneck = max(spans, key=lambda span: span.get("duration_ms", 0)) if spans else {}
            summaries.append(
                TraceSummary(
                    source_platform=self.source_platform,
                    query=query,
                    raw_ref=payload.raw_ref,
                    fetched_at=payload.fetched_at,
                    trace_id=row.get("trace_id"),
                    ts=row.get("ts"),
                    endpoint=row.get("endpoint"),
                    status=row.get("status"),
                    total_duration_ms=row.get("total_duration_ms"),
                    spans=spans,
                    bottleneck_service=self.identity.canonical(bottleneck.get("service")),
                    bottleneck_operation=bottleneck.get("operation"),
                    bottleneck_ms=bottleneck.get("duration_ms"),
                    raw=row,
                )
            )
        payload.data = summaries
        return payload

    def get_changes(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        query = {"service": service, "since": since, "until": until}
        payload = self._read_json("changes.json", query, default=[])
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        rows = self._filter_by_service_and_time(payload.data or [], service, since, until)
        payload.data = sorted(
            [
                ChangeEvent(
                    source_platform=self.source_platform,
                    query=query,
                    raw_ref=payload.raw_ref,
                    fetched_at=payload.fetched_at,
                    ts=row.get("ts"),
                    service=self.identity.canonical(row.get("service")),
                    change_type=row.get("change_type"),
                    version=row.get("version"),
                    risk=row.get("risk"),
                    summary=row.get("summary"),
                    raw=row,
                )
                for row in rows
            ],
            key=lambda change: change.ts or "",
            reverse=True,
        )
        return payload

    def get_business_metrics(
        self,
        workflow: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> ConnectorResponse:
        query = {"workflow": workflow, "since": since, "until": until}
        payload = self._read_json("business_metrics.json", query, default={})
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        row = payload.data or {}
        if workflow and row.get("workflow") and row.get("workflow") != workflow:
            payload.status = ConnectorStatus.NO_DATA
            payload.data = None
            payload.error_message = f"No business metrics found for workflow {workflow!r}"
            return payload
        payload.data = BusinessMetric(
            source_platform=self.source_platform,
            query=query,
            raw_ref=payload.raw_ref,
            fetched_at=payload.fetched_at,
            workflow=row.get("workflow"),
            transactions_last_24h=row.get("transactions_last_24h"),
            transactions_same_period_last_week=row.get("transactions_same_period_last_week"),
            transaction_drop_percent=row.get("transaction_drop_percent"),
            failed_transactions_last_24h=row.get("failed_transactions_last_24h"),
            payment_success_rate_percent=row.get("payment_success_rate_percent"),
            revenue_last_24h=row.get("revenue_last_24h"),
            estimated_revenue_impact=row.get("estimated_revenue_impact"),
            summary=row.get("business_summary"),
            raw=row,
        )
        return payload

    def get_service_dependencies(self, service_or_workflow: Optional[str] = None) -> ConnectorResponse:
        query = {"service_or_workflow": service_or_workflow}
        payload = self._read_json("service_dependencies.json", query, default={})
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        raw = payload.data or {}
        workflow = service_or_workflow or "checkout"
        workflows = raw.get("business_workflows", {}) or {}
        if workflow not in workflows:
            workflow = "checkout" if "checkout" in workflows else workflow
        wf = workflows.get(workflow, {}) or {}
        payload.data = ServiceDependency(
            source_platform=self.source_platform,
            query=query,
            raw_ref=payload.raw_ref,
            fetched_at=payload.fetched_at,
            workflow=workflow,
            critical_path=self.identity.canonicalize_services(wf.get("critical_path", []) or []),
            business_kpis=wf.get("business_kpis", []) or [],
            services=self.identity.canonicalize_services(list((raw.get("services", {}) or {}).keys())),
            dependencies=self.identity.canonicalize_dependencies(raw.get("services", {}) or {}),
            raw=raw,
        )
        return payload

    def _read_json(self, fname: str, query: Dict[str, Any], default: Any = None) -> ConnectorResponse:
        path = self.data_dir / fname
        fetched_at = utc_now_iso()
        if not path.exists():
            return ConnectorResponse(
                status=ConnectorStatus.NO_DATA,
                data=default,
                source_platform=self.source_platform,
                query=query,
                raw_ref=str(path),
                fetched_at=fetched_at,
                error_message=f"{fname} not found in {self.data_dir} — run the Mini Shop demo flow first",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            return ConnectorResponse(
                status=ConnectorStatus.UNAVAILABLE,
                data=default,
                source_platform=self.source_platform,
                query=query,
                raw_ref=str(path),
                fetched_at=fetched_at,
                error_message=f"{fname} contains invalid JSON: {exc}",
            )
        except OSError as exc:
            return ConnectorResponse(
                status=ConnectorStatus.UNAVAILABLE,
                data=default,
                source_platform=self.source_platform,
                query=query,
                raw_ref=str(path),
                fetched_at=fetched_at,
                error_message=f"{fname} could not be read: {exc}",
            )
        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=data,
            source_platform=self.source_platform,
            query=query,
            raw_ref=str(path),
            fetched_at=fetched_at,
        )

    @staticmethod
    def _filter_by_service_and_time(
        rows: Iterable[Dict[str, Any]],
        service: Optional[str],
        since: Optional[str],
        until: Optional[str],
    ) -> List[Dict[str, Any]]:
        filtered = []
        mapper = ServiceIdentityMapper()
        canonical_service = mapper.canonical(service)
        for row in rows:
            if canonical_service and mapper.canonical(row.get("service")) != canonical_service:
                continue
            if not MiniShopConnector._within_time(row.get("ts"), since, until):
                continue
            filtered.append(row)
        return filtered

    @staticmethod
    def _filter_by_time(
        rows: Iterable[Dict[str, Any]],
        since: Optional[str],
        until: Optional[str],
    ) -> List[Dict[str, Any]]:
        return [row for row in rows if MiniShopConnector._within_time(row.get("ts"), since, until)]

    @staticmethod
    def _within_time(ts: Optional[str], since: Optional[str], until: Optional[str]) -> bool:
        if since and ts and ts < since:
            return False
        if until and ts and ts > until:
            return False
        return True


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    return value
