from __future__ import annotations

import os
from functools import lru_cache

from connectors.base import BaseObservabilityConnector
from connectors.cache import CachedConnector, should_enable_cache
from connectors.hybrid_connector import HybridConnector
from connectors.mcp_connector import McpConnector
from connectors.minishop_connector import MiniShopConnector
from connectors.splunk_api_connector import SplunkApiConnector
from connectors.splunk_o11y_connector import SplunkO11yConnector


@lru_cache(maxsize=1)
def get_connector() -> BaseObservabilityConnector:
    data_source = os.environ.get("AIOPS_DATA_SOURCE", "minishop").strip().lower()
    if data_source == "minishop":
        return _maybe_cached(MiniShopConnector())
    if data_source == "splunk_api":
        return _maybe_cached(SplunkApiConnector())
    if data_source == "splunk_o11y":
        return _maybe_cached(SplunkO11yConnector())
    if data_source == "mcp":
        return _maybe_cached(McpConnector())
    if data_source == "hybrid":
        return _maybe_cached(HybridConnector())
    raise ValueError(
        f"Unsupported AIOPS_DATA_SOURCE={data_source!r}. "
        "Supported values are minishop, splunk_api, splunk_o11y, mcp, and hybrid."
    )


def _maybe_cached(connector: BaseObservabilityConnector) -> BaseObservabilityConnector:
    if should_enable_cache():
        return CachedConnector(connector)
    return connector
