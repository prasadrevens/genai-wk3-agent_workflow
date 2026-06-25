from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional

from connectors.schemas import ConnectorResponse


class BaseObservabilityConnector(ABC):
    @abstractmethod
    def capabilities(self) -> Dict[str, bool]:
        """Return supported signal types for this data source."""

    @abstractmethod
    def get_alert(self) -> ConnectorResponse:
        """Fetch the current incident alert."""

    @abstractmethod
    def get_logs(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        """Fetch log events for a service."""

    @abstractmethod
    def get_metrics(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        """Fetch metric series for a service."""

    @abstractmethod
    def get_traces(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        """Fetch trace summaries for a service."""

    @abstractmethod
    def get_changes(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        """Fetch deployment or configuration changes for a service."""

    @abstractmethod
    def get_business_metrics(
        self,
        workflow: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> ConnectorResponse:
        """Fetch business metrics for a workflow."""

    @abstractmethod
    def get_service_dependencies(self, service_or_workflow: Optional[str] = None) -> ConnectorResponse:
        """Fetch service dependency information."""
