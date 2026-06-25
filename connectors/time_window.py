from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

from connectors.minishop_connector import MiniShopConnector


@dataclass(frozen=True)
class TimeWindow:
    since: str
    until: str
    source: str


def resolve_time_window(since: Optional[str] = None, until: Optional[str] = None) -> TimeWindow:
    if since and until:
        return TimeWindow(since=since, until=until, source="explicit")

    alert_ts = os.environ.get("AIOPS_INCIDENT_TS") or _read_alert_ts()
    before_minutes = _env_int("AIOPS_WINDOW_BEFORE_MINUTES", 30)
    after_minutes = _env_int("AIOPS_WINDOW_AFTER_MINUTES", 15)
    lookback_minutes = _env_int("AIOPS_DEFAULT_LOOKBACK_MINUTES", before_minutes + after_minutes)

    if alert_ts:
        center = _parse_ts(alert_ts)
        resolved_since = since or _iso(center - timedelta(minutes=before_minutes))
        resolved_until = until or _iso(center + timedelta(minutes=after_minutes))
        return TimeWindow(since=resolved_since, until=resolved_until, source="alert")

    now = datetime.now(timezone.utc)
    return TimeWindow(
        since=since or _iso(now - timedelta(minutes=lookback_minutes)),
        until=until or _iso(now),
        source="lookback",
    )


def apply_time_window(since: Optional[str] = None, until: Optional[str] = None) -> Tuple[str, str]:
    window = resolve_time_window(since=since or None, until=until or None)
    return window.since, window.until


def _read_alert_ts() -> Optional[str]:
    path = MiniShopConnector.resolve_data_dir() / "alert.json"
    if not Path(path).exists():
        return None
    try:
        import json

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload.get("ts")


def _parse_ts(value: str) -> datetime:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
