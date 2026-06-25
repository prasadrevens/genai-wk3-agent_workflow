from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConnectorStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NO_DATA = "NO_DATA"
    AUTH_FAILURE = "AUTH_FAILURE"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class ConnectorResponse:
    status: ConnectorStatus
    data: Any
    source_platform: str
    query: Dict[str, Any]
    raw_ref: Optional[str]
    fetched_at: str
    error_message: Optional[str] = None


@dataclass
class ProvenancedRecord:
    source_platform: str
    query: Dict[str, Any]
    raw_ref: Optional[str]
    fetched_at: str


@dataclass
class AlertEvent(ProvenancedRecord):
    incident_id: Optional[str]
    ts: Optional[str]
    severity: Optional[str]
    service: Optional[str]
    workflow: Optional[str]
    title: Optional[str]
    symptoms: List[str] = field(default_factory=list)
    business_impact: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogEvent(ProvenancedRecord):
    ts: Optional[str]
    level: Optional[str]
    service: Optional[str]
    message: Optional[str]
    error_type: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricSeries(ProvenancedRecord):
    name: Optional[str]
    service: Optional[str]
    unit: Optional[str]
    points: List[Dict[str, Any]] = field(default_factory=list)
    aggregation: Optional[str] = None
    raw: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TraceSummary(ProvenancedRecord):
    trace_id: Optional[str]
    ts: Optional[str]
    endpoint: Optional[str]
    status: Optional[str]
    total_duration_ms: Optional[float]
    spans: List[Dict[str, Any]] = field(default_factory=list)
    bottleneck_service: Optional[str] = None
    bottleneck_operation: Optional[str] = None
    bottleneck_ms: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangeEvent(ProvenancedRecord):
    ts: Optional[str]
    service: Optional[str]
    change_type: Optional[str]
    version: Optional[str]
    risk: Optional[str]
    summary: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BusinessMetric(ProvenancedRecord):
    workflow: Optional[str]
    transactions_last_24h: Optional[float]
    transactions_same_period_last_week: Optional[float]
    transaction_drop_percent: Optional[float]
    failed_transactions_last_24h: Optional[float]
    payment_success_rate_percent: Optional[float]
    revenue_last_24h: Optional[float]
    estimated_revenue_impact: Optional[float]
    summary: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceDependency(ProvenancedRecord):
    workflow: Optional[str]
    critical_path: List[str] = field(default_factory=list)
    business_kpis: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    agent: str
    summary: str
    signal: str
    confidence: float
    evidence_refs: List[str] = field(default_factory=list)
    available: bool = True
    source_platform: Optional[str] = None
    query: Dict[str, Any] = field(default_factory=dict)
    raw_ref: Optional[str] = None
    fetched_at: Optional[str] = None


@dataclass
class InvestigationSession:
    session_id: str
    alert: Optional[AlertEvent]
    findings: List[Finding] = field(default_factory=list)
    business_impact: Optional[BusinessMetric] = None
    rca: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
