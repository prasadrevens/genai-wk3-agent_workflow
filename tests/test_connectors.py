import json
import os
import unittest
from unittest import mock

from connectors.cache import CachedConnector, ConnectorCache
from connectors.factory import get_connector
from connectors.hybrid_connector import HybridConnector
from connectors.minishop_connector import MiniShopConnector
from connectors.mcp_connector import McpConnector
from connectors.schemas import ConnectorResponse, ConnectorStatus, utc_now_iso
from connectors.service_identity import ServiceIdentityMapper
from connectors.splunk_api_connector import SplunkApiConnector
from connectors.splunk_o11y_connector import SplunkO11yConnector


class ConnectorFactoryTests(unittest.TestCase):
    def tearDown(self):
        get_connector.cache_clear()

    def test_factory_defaults_to_minishop(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            get_connector.cache_clear()

            connector = get_connector()

        self.assertIsInstance(connector, CachedConnector)
        self.assertIsInstance(connector.inner, MiniShopConnector)

    def test_factory_selects_splunk_api(self):
        with mock.patch.dict(os.environ, {"AIOPS_DATA_SOURCE": "splunk_api"}, clear=True):
            get_connector.cache_clear()

            connector = get_connector()

        self.assertIsInstance(connector, CachedConnector)
        self.assertIsInstance(connector.inner, SplunkApiConnector)
        self.assertEqual(
            connector.inner.capabilities(),
            {
                "logs": True,
                "metrics": False,
                "traces": False,
                "changes": True,
                "business_metrics": False,
                "service_dependencies": False,
            },
        )

    def test_factory_selects_hybrid(self):
        with mock.patch.dict(os.environ, {"AIOPS_DATA_SOURCE": "hybrid"}, clear=True):
            get_connector.cache_clear()

            connector = get_connector()

        self.assertIsInstance(connector, CachedConnector)
        self.assertIsInstance(connector.inner, HybridConnector)

    def test_factory_selects_splunk_o11y(self):
        with mock.patch.dict(os.environ, {"AIOPS_DATA_SOURCE": "splunk_o11y"}, clear=True):
            get_connector.cache_clear()

            connector = get_connector()

        self.assertIsInstance(connector, CachedConnector)
        self.assertIsInstance(connector.inner, SplunkO11yConnector)
        self.assertEqual(
            connector.inner.capabilities(),
            {
                "logs": False,
                "metrics": True,
                "traces": True,
                "changes": False,
                "business_metrics": False,
                "service_dependencies": True,
            },
        )

    def test_factory_selects_mcp(self):
        with mock.patch.dict(os.environ, {"AIOPS_DATA_SOURCE": "mcp"}, clear=True):
            get_connector.cache_clear()

            connector = get_connector()

        self.assertIsInstance(connector, CachedConnector)
        self.assertIsInstance(connector.inner, McpConnector)

    def test_factory_cache_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"AIOPS_CACHE_ENABLED": "false"}, clear=True):
            get_connector.cache_clear()

            connector = get_connector()

        self.assertIsInstance(connector, MiniShopConnector)


class SplunkApiConnectorTests(unittest.TestCase):
    def test_missing_config_returns_auth_failure(self):
        connector = SplunkApiConnector(base_url="", token="")

        response = connector.get_logs(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.AUTH_FAILURE)
        self.assertIn("SPLUNK_BASE_URL", response.error_message)

    def test_unsupported_signals_return_no_data(self):
        connector = SplunkApiConnector(base_url="https://splunk.example", token="token")

        response = connector.get_metrics(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.NO_DATA)
        self.assertIn("Sprint 2", response.error_message)

    def test_log_results_are_normalized(self):
        connector = StubSplunkApiConnector(
            [
                {
                    "_time": "2026-06-20T15:01:00Z",
                    "severity": "ERROR",
                    "service": "checkout-api",
                    "_raw": "payment timed out",
                    "error_type": "payment_timeout",
                }
            ]
        )

        response = connector.get_logs(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.SUCCESS)
        self.assertEqual(len(response.data), 1)
        log = response.data[0]
        self.assertEqual(log.ts, "2026-06-20T15:01:00Z")
        self.assertEqual(log.level, "ERROR")
        self.assertEqual(log.message, "payment timed out")
        self.assertEqual(log.error_type, "payment_timeout")
        self.assertEqual(log.source_platform, "splunk_api")

    def test_splunk_multivalue_fields_are_normalized_to_scalars(self):
        connector = StubSplunkApiConnector(
            [
                {
                    "_time": ["2026-06-20T15:01:00Z"],
                    "level": ["ERROR"],
                    "service": ["checkout-api"],
                    "message": ["payment timed out"],
                    "error_type": ["payment_timeout"],
                }
            ]
        )

        response = connector.get_logs(service="checkout-api")

        log = response.data[0]
        self.assertEqual(log.level, "ERROR")
        self.assertEqual(log.service, "checkout-api")
        self.assertEqual(log.message, "payment timed out")
        self.assertEqual(log.error_type, "payment_timeout")

    def test_change_results_are_normalized(self):
        connector = StubSplunkApiConnector(
            [
                {
                    "_time": "2026-06-20T15:02:00Z",
                    "service": "checkout-api",
                    "event_type": "deployment",
                    "version": "v2",
                    "risk": "high",
                    "message": "bad deployment",
                }
            ]
        )

        response = connector.get_changes(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.SUCCESS)
        change = response.data[0]
        self.assertEqual(change.ts, "2026-06-20T15:02:00Z")
        self.assertEqual(change.change_type, "deployment")
        self.assertEqual(change.summary, "bad deployment")
        self.assertEqual(change.source_platform, "splunk_api")


class ServiceIdentityMapperTests(unittest.TestCase):
    def test_maps_platform_aliases_to_canonical_services(self):
        mapper = ServiceIdentityMapper(
            {
                "checkout-api": {
                    "splunk_api": ["checkout-api"],
                    "splunk_o11y": ["checkout"],
                    "minishop": ["checkout-api"],
                }
            }
        )

        self.assertEqual(mapper.canonical("checkout"), "checkout-api")
        self.assertEqual(mapper.platform_service("checkout-api", "splunk_o11y"), "checkout")
        self.assertEqual(mapper.platform_service("checkout", "splunk_api"), "checkout-api")

    def test_canonicalizes_dependencies(self):
        mapper = ServiceIdentityMapper(
            {
                "checkout-api": {"splunk_o11y": ["checkout"]},
                "payment-api": {"splunk_o11y": ["payment"]},
            }
        )

        deps = mapper.canonicalize_dependencies({"checkout": ["payment"]})

        self.assertEqual(deps, {"checkout-api": ["payment-api"]})


class HybridConnectorTests(unittest.TestCase):
    def test_default_routes_use_splunk_api_and_o11y_by_signal_type(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            connector = HybridConnector(
                minishop=StubConnector("minishop"),
                splunk_api=StubConnector("splunk_api"),
                splunk_o11y=StubConnector("splunk_o11y"),
            )

        self.assertEqual(connector.route_for("logs"), "splunk_api")
        self.assertEqual(connector.route_for("changes"), "splunk_api")
        self.assertEqual(connector.route_for("metrics"), "splunk_o11y")
        self.assertEqual(connector.route_for("traces"), "splunk_o11y")
        self.assertEqual(connector.route_for("business_metrics"), "minishop")
        self.assertEqual(connector.route_for("service_dependencies"), "splunk_o11y")

    def test_hybrid_routes_calls_by_signal_type(self):
        minishop = StubConnector("minishop")
        splunk_api = StubConnector("splunk_api")
        splunk_o11y = StubConnector("splunk_o11y")
        connector = HybridConnector(minishop=minishop, splunk_api=splunk_api, splunk_o11y=splunk_o11y)

        logs = connector.get_logs(service="checkout-api")
        metrics = connector.get_metrics(service="checkout-api")
        changes = connector.get_changes(service="checkout-api")
        business = connector.get_business_metrics(workflow="checkout")
        deps = connector.get_service_dependencies(service_or_workflow="checkout")

        self.assertEqual(logs.source_platform, "splunk_api")
        self.assertEqual(metrics.source_platform, "splunk_o11y")
        self.assertEqual(changes.source_platform, "splunk_api")
        self.assertEqual(business.source_platform, "minishop")
        self.assertEqual(deps.source_platform, "splunk_o11y")
        self.assertEqual(splunk_api.calls, ["logs", "changes"])
        self.assertEqual(splunk_o11y.calls, ["metrics", "service_dependencies"])
        self.assertEqual(minishop.calls, ["business_metrics"])

    def test_route_overrides_come_from_environment(self):
        with mock.patch.dict(os.environ, {"AIOPS_ROUTE_LOGS": "minishop"}, clear=True):
            connector = HybridConnector(
                minishop=StubConnector("minishop"),
                splunk_api=StubConnector("splunk_api"),
                splunk_o11y=StubConnector("splunk_o11y"),
            )

        response = connector.get_logs(service="checkout-api")

        self.assertEqual(connector.route_for("logs"), "minishop")
        self.assertEqual(response.source_platform, "minishop")

    def test_hybrid_can_route_signals_to_mcp(self):
        with mock.patch.dict(os.environ, {"AIOPS_ROUTE_LOGS": "mcp"}, clear=True):
            connector = HybridConnector(
                minishop=StubConnector("minishop"),
                splunk_api=StubConnector("splunk_api"),
                splunk_o11y=StubConnector("splunk_o11y"),
                mcp=StubConnector("mcp"),
            )

        response = connector.get_logs(service="checkout-api")

        self.assertEqual(connector.route_for("logs"), "mcp")
        self.assertEqual(response.source_platform, "mcp")


class ConnectorCacheTests(unittest.TestCase):
    def test_cached_connector_reuses_successful_response(self):
        inner = StubConnector("minishop")
        connector = CachedConnector(inner, cache=ConnectorCache(ttl_seconds=60))

        first = connector.get_logs(service="checkout-api")
        second = connector.get_logs(service="checkout-api")

        self.assertEqual(inner.calls, ["logs"])
        self.assertEqual(first.query["cache"], "miss")
        self.assertEqual(second.query["cache"], "hit")

    def test_cached_connector_deep_copies_responses(self):
        inner = StubConnector("minishop")
        connector = CachedConnector(inner, cache=ConnectorCache(ttl_seconds=60))

        first = connector.get_logs(service="checkout-api")
        first.data.append("mutated")
        second = connector.get_logs(service="checkout-api")

        self.assertEqual(second.data, [])

    def test_cache_key_includes_time_window(self):
        inner = StubConnector("minishop")
        connector = CachedConnector(inner, cache=ConnectorCache(ttl_seconds=60))

        connector.get_logs(service="checkout-api", since="a", until="b")
        connector.get_logs(service="checkout-api", since="c", until="d")

        self.assertEqual(inner.calls, ["logs", "logs"])


class SplunkO11yConnectorTests(unittest.TestCase):
    def test_missing_config_returns_auth_failure(self):
        connector = SplunkO11yConnector(realm="", access_token="")

        response = connector.get_metrics(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.AUTH_FAILURE)
        self.assertIn("SPLUNK_O11Y_REALM", response.error_message)

    def test_o11y_metric_rows_are_normalized(self):
        connector = StubSplunkO11yConnector(
            metric_rows=[
                {"metric": "checkout.latency", "value": 250, "timestamp": "2026-06-20T15:01:00Z"},
                {"metric": "checkout.failure", "value": 2, "timestamp": "2026-06-20T15:01:00Z"},
            ]
        )

        response = connector.get_metrics(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.SUCCESS)
        names = sorted(series.name for series in response.data)
        self.assertEqual(names, ["checkout.failure", "checkout.latency"])
        self.assertEqual(response.data[0].source_platform, "splunk_o11y")

    def test_o11y_queries_platform_alias_and_returns_canonical_service(self):
        with mock.patch.dict(
            os.environ,
            {
                "AIOPS_SERVICE_IDENTITY_MAP": json.dumps(
                    {
                        "checkout-api": {
                            "minishop": ["checkout-api"],
                            "splunk_api": ["checkout-api"],
                            "splunk_o11y": ["checkout"],
                        }
                    }
                )
            },
            clear=True,
        ):
            connector = StubSplunkO11yConnector(
                metric_rows=[
                    {"metric": "checkout.latency", "value": 250, "timestamp": "2026-06-20T15:01:00Z"},
                ]
            )

        response = connector.get_metrics(service="checkout-api")

        self.assertIn('"checkout"', response.query["program"])
        self.assertEqual(response.data[0].service, "checkout-api")

    def test_o11y_trace_rows_are_normalized(self):
        connector = StubSplunkO11yConnector(
            trace_payload={
                "traces": [
                    {
                        "traceId": "abc",
                        "timestamp": "2026-06-20T15:01:00Z",
                        "rootOperation": "GET /checkout",
                        "duration": 500,
                        "spans": [{"service": "checkout-api", "operation": "GET /checkout", "duration": 500}],
                    }
                ]
            }
        )

        response = connector.get_traces(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.SUCCESS)
        self.assertEqual(response.data[0].trace_id, "abc")
        self.assertEqual(response.data[0].bottleneck_service, "checkout-api")

    def test_o11y_dependency_payload_is_normalized(self):
        connector = StubSplunkO11yConnector(
            dependency_payload={
                "nodes": [{"name": "checkout-api"}, {"name": "payment-api"}],
                "edges": [{"source": "checkout-api", "target": "payment-api"}],
            }
        )

        response = connector.get_service_dependencies(service_or_workflow="checkout")

        self.assertEqual(response.status, ConnectorStatus.SUCCESS)
        self.assertEqual(response.data.services, ["checkout-api", "payment-api"])
        self.assertEqual(response.data.dependencies, {"checkout-api": ["payment-api"]})


class McpConnectorTests(unittest.TestCase):
    def test_missing_bridge_config_returns_auth_failure(self):
        connector = McpConnector(base_url="", token="")

        response = connector.get_logs(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.AUTH_FAILURE)
        self.assertIn("MCP_BRIDGE_URL", response.error_message)

    def test_capabilities_default_to_all_signals_enabled(self):
        connector = McpConnector(base_url="http://mcp.example", token="token")

        self.assertEqual(
            connector.capabilities(),
            {
                "logs": True,
                "metrics": True,
                "traces": True,
                "changes": True,
                "business_metrics": True,
                "service_dependencies": True,
            },
        )

    def test_mcp_log_payload_is_normalized(self):
        connector = StubMcpConnector(
            {
                "data": [
                    {
                        "ts": "2026-06-20T15:01:00Z",
                        "level": "ERROR",
                        "service": "checkout-api",
                        "message": "payment timeout",
                        "error_type": "payment_timeout",
                    }
                ]
            }
        )

        response = connector.get_logs(service="checkout-api", since="a", until="b")

        self.assertEqual(response.status, ConnectorStatus.SUCCESS)
        self.assertEqual(response.query["tool"], "get_logs")
        self.assertEqual(response.query["arguments"]["service"], "checkout-api")
        self.assertEqual(response.data[0].message, "payment timeout")
        self.assertEqual(response.data[0].source_platform, "mcp")

    def test_mcp_empty_payload_returns_no_data(self):
        connector = StubMcpConnector({"data": []})

        response = connector.get_changes(service="checkout-api")

        self.assertEqual(response.status, ConnectorStatus.NO_DATA)
        self.assertIn("returned no data", response.error_message)


class StubSplunkApiConnector(SplunkApiConnector):
    def __init__(self, rows):
        super().__init__(base_url="https://splunk.example", token="token")
        self.rows = rows

    def _run_search(self, search, since=None, until=None, query=None):
        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=self.rows,
            source_platform=self.source_platform,
            query=query or {},
            raw_ref="stub://splunk-search",
            fetched_at="2026-06-20T00:00:00+00:00",
        )


class StubConnector:
    def __init__(self, source_platform):
        self.source_platform = source_platform
        self.calls = []

    def capabilities(self):
        return {
            "logs": True,
            "metrics": True,
            "traces": True,
            "changes": True,
            "business_metrics": True,
            "service_dependencies": True,
        }

    def get_alert(self):
        self.calls.append("alert")
        return self._response("alert")

    def get_logs(self, service, since=None, until=None):
        self.calls.append("logs")
        return self._response("logs")

    def get_metrics(self, service, since=None, until=None):
        self.calls.append("metrics")
        return self._response("metrics")

    def get_traces(self, service, since=None, until=None):
        self.calls.append("traces")
        return self._response("traces")

    def get_changes(self, service, since=None, until=None):
        self.calls.append("changes")
        return self._response("changes")

    def get_business_metrics(self, workflow=None, since=None, until=None):
        self.calls.append("business_metrics")
        return self._response("business_metrics")

    def get_service_dependencies(self, service_or_workflow=None):
        self.calls.append("service_dependencies")
        return self._response("service_dependencies")

    def _response(self, signal):
        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=[],
            source_platform=self.source_platform,
            query={"signal": signal},
            raw_ref=f"stub://{self.source_platform}/{signal}",
            fetched_at=utc_now_iso(),
        )


class StubSplunkO11yConnector(SplunkO11yConnector):
    def __init__(self, metric_rows=None, trace_payload=None, dependency_payload=None):
        super().__init__(realm="us0", access_token="token")
        self.metric_rows = metric_rows if metric_rows is not None else []
        self.trace_payload = trace_payload if trace_payload is not None else []
        self.dependency_payload = dependency_payload if dependency_payload is not None else {}

    def _execute_signalflow(self, program, since=None, until=None, query=None):
        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=self.metric_rows,
            source_platform=self.source_platform,
            query={**(query or {}), "program": program},
            raw_ref="stub://o11y/signalflow",
            fetched_at="2026-06-20T00:00:00+00:00",
        )

    def _request_json(self, method, url, query, default):
        if "service-map" in url:
            data = self.dependency_payload
            raw_ref = "stub://o11y/service-map"
        else:
            data = self.trace_payload
            raw_ref = "stub://o11y/traces"
        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=data,
            source_platform=self.source_platform,
            query=query or {},
            raw_ref=raw_ref,
            fetched_at="2026-06-20T00:00:00+00:00",
        )


class StubMcpConnector(McpConnector):
    def __init__(self, payload):
        super().__init__(base_url="http://mcp.example", token="token")
        self.payload = payload

    def _call_tool(self, tool, arguments):
        return ConnectorResponse(
            status=ConnectorStatus.SUCCESS,
            data=self.payload,
            source_platform=self.source_platform,
            query={"tool": tool, "arguments": arguments},
            raw_ref="stub://mcp/tool",
            fetched_at="2026-06-20T00:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
