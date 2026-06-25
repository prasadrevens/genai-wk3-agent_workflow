from __future__ import annotations

import os
from typing import Dict, Optional

from connectors.base import BaseObservabilityConnector
from connectors.mcp_connector import McpConnector
from connectors.minishop_connector import MiniShopConnector
from connectors.schemas import ConnectorResponse
from connectors.splunk_api_connector import SplunkApiConnector
from connectors.splunk_o11y_connector import SplunkO11yConnector


SIGNALS = (
    "alert",
    "logs",
    "metrics",
    "traces",
    "changes",
    "business_metrics",
    "service_dependencies",
)


class HybridConnector(BaseObservabilityConnector):
    """Signal-type router for mixed observability backends.

    Sprint 4 routes logs and changes to Splunk Platform API while keeping the
    remaining signals on Mini Shop until the Splunk O11y connector lands.
    Agents still reason by signal type and never see platform routing details.
    """

    source_platform = "hybrid"

    def __init__(
        self,
        minishop: Optional[BaseObservabilityConnector] = None,
        splunk_api: Optional[BaseObservabilityConnector] = None,
        splunk_o11y: Optional[BaseObservabilityConnector] = None,
        mcp: Optional[BaseObservabilityConnector] = None,
        route_map: Optional[Dict[str, str]] = None,
    ):
        self.connectors = {
            "minishop": minishop or MiniShopConnector(),
            "splunk_api": splunk_api or SplunkApiConnector(),
            "splunk_o11y": splunk_o11y or SplunkO11yConnector(),
            "mcp": mcp or McpConnector(),
        }
        self.route_map = route_map or self._route_map_from_env()

    def capabilities(self) -> Dict[str, bool]:
        return {
            signal: self._connector_for(signal).capabilities().get(signal, False)
            for signal in SIGNALS
            if signal != "alert"
        }

    def get_alert(self) -> ConnectorResponse:
        return self._connector_for("alert").get_alert()

    def get_logs(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._connector_for("logs").get_logs(service=service, since=since, until=until)

    def get_metrics(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._connector_for("metrics").get_metrics(service=service, since=since, until=until)

    def get_traces(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._connector_for("traces").get_traces(service=service, since=since, until=until)

    def get_changes(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._connector_for("changes").get_changes(service=service, since=since, until=until)

    def get_business_metrics(
        self,
        workflow: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> ConnectorResponse:
        return self._connector_for("business_metrics").get_business_metrics(
            workflow=workflow,
            since=since,
            until=until,
        )

    def get_service_dependencies(self, service_or_workflow: Optional[str] = None) -> ConnectorResponse:
        return self._connector_for("service_dependencies").get_service_dependencies(
            service_or_workflow=service_or_workflow,
        )

    def route_for(self, signal: str) -> str:
        if signal not in SIGNALS:
            raise ValueError(f"Unsupported signal {signal!r}")
        return self.route_map.get(signal, "minishop")

    def _connector_for(self, signal: str) -> BaseObservabilityConnector:
        connector_name = self.route_for(signal)
        try:
            return self.connectors[connector_name]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported connector route {connector_name!r} for signal {signal!r}. "
                f"Supported connector routes are {sorted(self.connectors)}."
            ) from exc

    @staticmethod
    def _route_map_from_env() -> Dict[str, str]:
        defaults = {
            "alert": "minishop",
            "logs": "splunk_api",
            "metrics": "splunk_o11y",
            "traces": "splunk_o11y",
            "changes": "splunk_api",
            "business_metrics": "minishop",
            "service_dependencies": "splunk_o11y",
        }
        return {
            signal: os.environ.get(f"AIOPS_ROUTE_{signal.upper()}", default).strip().lower() or default
            for signal, default in defaults.items()
        }
