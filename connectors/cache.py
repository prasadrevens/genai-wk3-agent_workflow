from __future__ import annotations

import copy
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from connectors.base import BaseObservabilityConnector
from connectors.schemas import ConnectorResponse, ConnectorStatus


@dataclass
class CacheEntry:
    response: ConnectorResponse
    expires_at: float


class ConnectorCache:
    def __init__(self, ttl_seconds: int = 30, max_entries: int = 256):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: Dict[Tuple[Any, ...], CacheEntry] = {}

    def get(self, key: Tuple[Any, ...]) -> Optional[ConnectorResponse]:
        entry = self._entries.get(key)
        if not entry:
            return None
        if entry.expires_at < time.time():
            self._entries.pop(key, None)
            return None
        return copy.deepcopy(entry.response)

    def set(self, key: Tuple[Any, ...], response: ConnectorResponse) -> None:
        if self.ttl_seconds <= 0:
            return
        if len(self._entries) >= self.max_entries:
            oldest_key = min(self._entries, key=lambda item: self._entries[item].expires_at)
            self._entries.pop(oldest_key, None)
        self._entries[key] = CacheEntry(
            response=copy.deepcopy(response),
            expires_at=time.time() + self.ttl_seconds,
        )

    def clear(self) -> None:
        self._entries.clear()


class CachedConnector(BaseObservabilityConnector):
    """TTL cache wrapper for connector reads.

    The cache is intentionally below aiops_tools.py and above platform
    connectors, so agents and tool return shapes remain unchanged.
    """

    source_platform = "cached"

    def __init__(self, inner: BaseObservabilityConnector, cache: Optional[ConnectorCache] = None):
        self.inner = inner
        self.cache = cache or ConnectorCache(
            ttl_seconds=_env_int("AIOPS_CACHE_TTL_SECONDS", 30),
            max_entries=_env_int("AIOPS_CACHE_MAX_ENTRIES", 256),
        )
        self.cache_success_only = _env_bool("AIOPS_CACHE_SUCCESS_ONLY", True)

    def capabilities(self) -> Dict[str, bool]:
        return self.inner.capabilities()

    def get_alert(self) -> ConnectorResponse:
        return self._cached("alert", self.inner.get_alert)

    def get_logs(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._cached("logs", self.inner.get_logs, service=service, since=since, until=until)

    def get_metrics(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._cached("metrics", self.inner.get_metrics, service=service, since=since, until=until)

    def get_traces(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._cached("traces", self.inner.get_traces, service=service, since=since, until=until)

    def get_changes(self, service: str, since: Optional[str] = None, until: Optional[str] = None) -> ConnectorResponse:
        return self._cached("changes", self.inner.get_changes, service=service, since=since, until=until)

    def get_business_metrics(
        self,
        workflow: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> ConnectorResponse:
        return self._cached(
            "business_metrics",
            self.inner.get_business_metrics,
            workflow=workflow,
            since=since,
            until=until,
        )

    def get_service_dependencies(self, service_or_workflow: Optional[str] = None) -> ConnectorResponse:
        return self._cached(
            "service_dependencies",
            self.inner.get_service_dependencies,
            service_or_workflow=service_or_workflow,
        )

    def _cached(self, signal: str, fn, **kwargs) -> ConnectorResponse:
        key = self._key(signal, kwargs)
        cached = self.cache.get(key)
        if cached:
            cached.query = {**cached.query, "cache": "hit"}
            return cached
        response = fn(**kwargs)
        response.query = {**response.query, "cache": "miss"}
        if not self.cache_success_only or response.status == ConnectorStatus.SUCCESS:
            self.cache.set(key, response)
        return copy.deepcopy(response)

    @staticmethod
    def _key(signal: str, kwargs: Dict[str, Any]) -> Tuple[Any, ...]:
        return (signal, tuple(sorted((key, _freeze(value)) for key, value in kwargs.items())))


def should_enable_cache() -> bool:
    return _env_bool("AIOPS_CACHE_ENABLED", True)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
