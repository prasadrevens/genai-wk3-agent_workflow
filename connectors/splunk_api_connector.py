from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from connectors.base import BaseObservabilityConnector
from connectors.schemas import (
    ChangeEvent,
    ConnectorResponse,
    ConnectorStatus,
    LogEvent,
    utc_now_iso,
)
from connectors.service_identity import ServiceIdentityMapper


class SplunkApiConnector(BaseObservabilityConnector):
    """Splunk Enterprise/Cloud REST API connector for Sprint 2.

    Sprint 2 intentionally exposes only logs and changes. Metrics, traces,
    business metrics, and dependency maps remain unavailable until their
    platform-specific connectors are added in later sprints.
    """

    source_platform = "splunk_api"

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        index: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
        timeout_seconds: Optional[float] = None,
        auth_scheme: Optional[str] = None,
    ):
        self.base_url = (base_url if base_url is not None else os.environ.get("SPLUNK_BASE_URL", "")).strip()
        self.token = (token if token is not None else os.environ.get("SPLUNK_TOKEN", "")).strip()
        self.index = (index if index is not None else os.environ.get("SPLUNK_INDEX", "main")).strip() or "main"
        self.verify_ssl = verify_ssl if verify_ssl is not None else self._env_bool("SPLUNK_VERIFY_SSL", True)
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else self._env_float("SPLUNK_TIMEOUT_SECONDS", 10.0)
        )
        self.auth_scheme = (
            auth_scheme if auth_scheme is not None else os.environ.get("SPLUNK_AUTH_SCHEME", "Splunk")
        ).strip() or "Splunk"
        self.identity = ServiceIdentityMapper()

    def capabilities(self) -> Dict[str, bool]:
        return {
            "logs": True,
            "metrics": False,
            "traces": False,
            "changes": True,
            "business_metrics": False,
            "service_dependencies": False,
        }

    def get_alert(self) -> ConnectorResponse:
        return self._unsupported("alert", {})

    def get_logs(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        platform_service = self.identity.platform_service(service, self.source_platform)
        query = {"service": service, "platform_service": platform_service, "since": since, "until": until}
        search = (
            f'search index="{self._escape(self.index)}" service="{self._escape(platform_service)}" '
            '(level=* OR severity=* OR message=*) '
            "| spath | fields _time ts level severity service message error_type _raw"
        )
        payload = self._run_search(search, since=since, until=until, query=query)
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        payload.data = [
            LogEvent(
                source_platform=self.source_platform,
                query=query,
                raw_ref=payload.raw_ref,
                fetched_at=payload.fetched_at,
                ts=self._first(row.get("ts")) or self._first(row.get("_time")),
                level=self._first(row.get("level")) or self._first(row.get("severity")),
                service=self.identity.canonical(self._first(row.get("service")) or platform_service),
                message=self._first(row.get("message")) or self._first(row.get("_raw")),
                error_type=self._first(row.get("error_type")),
                raw=row,
            )
            for row in payload.data
        ]
        return payload

    def get_metrics(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._unsupported("metrics", {"service": service, "since": since, "until": until})

    def get_traces(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._unsupported("traces", {"service": service, "since": since, "until": until})

    def get_changes(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        platform_service = self.identity.platform_service(service, self.source_platform)
        query = {"service": service, "platform_service": platform_service, "since": since, "until": until}
        search = (
            f'search index="{self._escape(self.index)}" service="{self._escape(platform_service)}" '
            '(change_type=* OR event_type=deployment OR sourcetype=deployment OR sourcetype=changes) '
            "| spath | fields _time ts service change_type event_type version risk summary message _raw"
        )
        payload = self._run_search(search, since=since, until=until, query=query)
        if payload.status != ConnectorStatus.SUCCESS:
            return payload
        payload.data = [
            ChangeEvent(
                source_platform=self.source_platform,
                query=query,
                raw_ref=payload.raw_ref,
                fetched_at=payload.fetched_at,
                ts=self._first(row.get("ts")) or self._first(row.get("_time")),
                service=self.identity.canonical(self._first(row.get("service")) or platform_service),
                change_type=self._first(row.get("change_type")) or self._first(row.get("event_type")),
                version=self._first(row.get("version")),
                risk=self._first(row.get("risk")),
                summary=self._first(row.get("summary")) or self._first(row.get("message")) or self._first(row.get("_raw")),
                raw=row,
            )
            for row in payload.data
        ]
        return payload

    def get_business_metrics(
        self,
        workflow: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> ConnectorResponse:
        return self._unsupported("business_metrics", {"workflow": workflow, "since": since, "until": until})

    def get_service_dependencies(self, service_or_workflow: Optional[str] = None) -> ConnectorResponse:
        return self._unsupported("service_dependencies", {"service_or_workflow": service_or_workflow})

    def _run_search(
        self,
        search: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> ConnectorResponse:
        fetched_at = utc_now_iso()
        query_payload = {**(query or {}), "search": search, "since": since, "until": until}
        if not self.base_url or not self.token:
            return ConnectorResponse(
                status=ConnectorStatus.AUTH_FAILURE,
                data=[],
                source_platform=self.source_platform,
                query=query_payload,
                raw_ref=None,
                fetched_at=fetched_at,
                error_message="SPLUNK_BASE_URL and SPLUNK_TOKEN are required for AIOPS_DATA_SOURCE=splunk_api",
            )

        url = f"{self.base_url.rstrip('/')}/services/search/jobs/export"
        form = {
            "search": search if search.lstrip().startswith("search ") else f"search {search}",
            "output_mode": "json",
        }
        if since:
            form["earliest_time"] = since
        if until:
            form["latest_time"] = until
        body = urllib.parse.urlencode(form).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"{self.auth_scheme} {self.token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            context = None if self.verify_ssl else ssl._create_unverified_context()
            with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=context) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = ConnectorStatus.AUTH_FAILURE if exc.code in {401, 403} else ConnectorStatus.UNAVAILABLE
            return ConnectorResponse(
                status=status,
                data=[],
                source_platform=self.source_platform,
                query=query_payload,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"Splunk search HTTP {exc.code}: {exc.reason}",
            )
        except (TimeoutError, socket.timeout) as exc:
            return ConnectorResponse(
                status=ConnectorStatus.TIMEOUT,
                data=[],
                source_platform=self.source_platform,
                query=query_payload,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"Splunk search timed out: {exc}",
            )
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            status = ConnectorStatus.TIMEOUT if isinstance(reason, socket.timeout) else ConnectorStatus.UNAVAILABLE
            return ConnectorResponse(
                status=status,
                data=[],
                source_platform=self.source_platform,
                query=query_payload,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"Splunk search unavailable: {reason}",
            )
        except OSError as exc:
            return ConnectorResponse(
                status=ConnectorStatus.UNAVAILABLE,
                data=[],
                source_platform=self.source_platform,
                query=query_payload,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message=f"Splunk search unavailable: {exc}",
            )

        rows = self._parse_export_results(text)
        if not rows:
            return ConnectorResponse(
                status=ConnectorStatus.NO_DATA,
                data=[],
                source_platform=self.source_platform,
                query=query_payload,
                raw_ref=url,
                fetched_at=fetched_at,
                error_message="Splunk search returned no rows",
            )
        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=rows,
            source_platform=self.source_platform,
            query=query_payload,
            raw_ref=url,
            fetched_at=fetched_at,
        )

    def _unsupported(self, signal: str, query: Dict[str, Any]) -> ConnectorResponse:
        return ConnectorResponse(
            status=ConnectorStatus.NO_DATA,
            data=[],
            source_platform=self.source_platform,
            query=query,
            raw_ref=None,
            fetched_at=utc_now_iso(),
            error_message=f"Splunk API connector does not provide {signal} in Sprint 2",
        )

    @staticmethod
    def _parse_export_results(text: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            result = payload.get("result", payload)
            if isinstance(result, dict):
                rows.append(result)
        return rows

    @staticmethod
    def _escape(value: Optional[str]) -> str:
        return (value or "").replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _first(value: Any) -> Any:
        if isinstance(value, list):
            return value[0] if value else None
        return value

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
