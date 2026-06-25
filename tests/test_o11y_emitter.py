import json
import os
import unittest
from unittest import mock

from mini_shop_with_ui.o11y import SplunkO11yEmitter


class SplunkO11yEmitterTests(unittest.TestCase):
    def test_emitter_is_disabled_without_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("urllib.request.urlopen") as urlopen:
            emitter = SplunkO11yEmitter()

            emitter.emit_metric("checkout.latency", 123, "ms", "checkout-api", {})
            emitter.emit_trace("/checkout", [{"service": "checkout-api", "operation": "checkout", "duration_ms": 1}], "ok", "abc")

        self.assertFalse(emitter.enabled)
        urlopen.assert_not_called()

    def test_metric_payload_uses_splunk_datapoint_shape(self):
        with mock.patch.dict(
            os.environ,
            {"SPLUNK_O11Y_REALM": "us1", "SPLUNK_O11Y_ACCESS_TOKEN": "token"},
            clear=True,
        ), mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b"{}"
            emitter = SplunkO11yEmitter()

            emitter.emit_metric("checkout.latency", 250, "ms", "checkout-api", {"mode": "bad"})

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://ingest.us1.signalfx.com/v2/datapoint")
        self.assertEqual(request.headers["X-sf-token"], "token")
        self.assertEqual(payload["gauge"][0]["metric"], "checkout.latency")
        self.assertEqual(payload["gauge"][0]["dimensions"]["sf_service"], "checkout-api")
        self.assertEqual(payload["gauge"][0]["dimensions"]["mode"], "bad")
        self.assertEqual(emitter.metrics_sent, 1)

    def test_trace_payload_uses_zipkin_span_shape(self):
        with mock.patch.dict(
            os.environ,
            {"SPLUNK_O11Y_REALM": "us1", "SPLUNK_O11Y_ACCESS_TOKEN": "token"},
            clear=True,
        ), mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b"{}"
            emitter = SplunkO11yEmitter()

            emitter.emit_trace(
                "/checkout",
                [{"service": "checkout-api", "operation": "POST /checkout", "duration_ms": 25}],
                "ok",
                "00000000-0000-0000-0000-000000000001",
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://ingest.us1.signalfx.com/v2/trace")
        self.assertEqual(payload[0]["name"], "POST /checkout")
        self.assertEqual(payload[0]["localEndpoint"]["serviceName"], "checkout-api")
        self.assertEqual(payload[0]["tags"]["http.route"], "/checkout")
        self.assertEqual(emitter.traces_sent, 1)


if __name__ == "__main__":
    unittest.main()
