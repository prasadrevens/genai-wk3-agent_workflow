import os
import unittest
from unittest import mock

from connectors.time_window import resolve_time_window


class TimeWindowTests(unittest.TestCase):
    def test_explicit_window_is_preserved(self):
        window = resolve_time_window(
            since="2026-06-21T01:00:00+00:00",
            until="2026-06-21T02:00:00+00:00",
        )

        self.assertEqual(window.source, "explicit")
        self.assertEqual(window.since, "2026-06-21T01:00:00+00:00")
        self.assertEqual(window.until, "2026-06-21T02:00:00+00:00")

    def test_alert_timestamp_centers_window(self):
        with mock.patch.dict(
            os.environ,
            {
                "AIOPS_INCIDENT_TS": "2026-06-21T03:00:00+00:00",
                "AIOPS_WINDOW_BEFORE_MINUTES": "10",
                "AIOPS_WINDOW_AFTER_MINUTES": "5",
            },
            clear=True,
        ):
            window = resolve_time_window()

        self.assertEqual(window.source, "alert")
        self.assertEqual(window.since, "2026-06-21T02:50:00+00:00")
        self.assertEqual(window.until, "2026-06-21T03:05:00+00:00")

    def test_partial_explicit_window_keeps_explicit_bound(self):
        with mock.patch.dict(
            os.environ,
            {
                "AIOPS_INCIDENT_TS": "2026-06-21T03:00:00+00:00",
                "AIOPS_WINDOW_AFTER_MINUTES": "5",
            },
            clear=True,
        ):
            window = resolve_time_window(since="2026-06-21T02:00:00+00:00")

        self.assertEqual(window.source, "alert")
        self.assertEqual(window.since, "2026-06-21T02:00:00+00:00")
        self.assertEqual(window.until, "2026-06-21T03:05:00+00:00")


if __name__ == "__main__":
    unittest.main()
