from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IncidentMemoryRecord:
    event_type: str
    run_id: str
    incident_id: Optional[str]
    service: Optional[str]
    workflow: Optional[str]
    status: str
    created_at: str = field(default_factory=utc_now_iso)
    root_cause: Optional[str] = None
    confidence: Optional[str] = None
    business_impact: Optional[str] = None
    recommendation: Optional[str] = None
    decision: Optional[str] = None
    outcome: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IncidentMemoryStore:
    """Append-only incident memory store for demo/evaluation use."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: IncidentMemoryRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_clean(record.__dict__), sort_keys=True) + "\n")

    def list_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records[-limit:]

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def record_from_run(event_type: str, run: Dict[str, Any], alert: Dict[str, Any], **extra: Any) -> IncidentMemoryRecord:
    pause = run.get("pause") or {}
    return IncidentMemoryRecord(
        event_type=event_type,
        run_id=run.get("run_id", "unknown"),
        incident_id=alert.get("incident_id"),
        service=alert.get("service"),
        workflow=alert.get("workflow"),
        status=run.get("status", "unknown"),
        root_cause=pause.get("root_cause"),
        confidence=pause.get("confidence_band"),
        business_impact=pause.get("business_impact"),
        recommendation=pause.get("proposed_fix"),
        decision=run.get("decision_status"),
        outcome=run.get("final") or extra.get("outcome"),
        metadata={
            "thread_id": run.get("thread_id"),
            "timeline_events": len(run.get("timeline") or []),
            **{key: value for key, value in extra.items() if value is not None},
        },
    )


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value
