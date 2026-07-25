"""Unit tests for the shared daemon module."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.daemon import BaseDaemon


class MockDaemon(BaseDaemon):
    def __init__(self, **kwargs):
        super().__init__("mock-daemon", **kwargs)
        self.start_called = False
        self.poll_called = False
        self.stop_called = False

    def on_start(self):
        self.start_called = True

    def poll(self):
        self.poll_called = True

    def on_stop(self):
        self.stop_called = True


class DaemonTests(unittest.TestCase):
    @mock.patch("signal.signal")
    def test_daemon_lifecycle_oneshot(self, mock_signal):
        daemon = MockDaemon(oneshot=True)
        exit_code = daemon.run()

        self.assertEqual(exit_code, 0)
        self.assertTrue(daemon.start_called)
        self.assertTrue(daemon.poll_called)
        self.assertTrue(daemon.stop_called)
        self.assertFalse(daemon.running)

    def test_daemon_get_poll_interval(self):
        daemon = MockDaemon(
            default_config={"poll_interval": 15},
            poll_interval_key="poll_interval",
            default_poll_interval=10.0,
        )
        daemon.load_config()
        self.assertEqual(daemon.get_poll_interval(), 15.0)

        daemon2 = MockDaemon(
            default_config={"poll_interval": "invalid"},
            poll_interval_key="poll_interval",
            default_poll_interval=10.0,
        )
        daemon2.load_config()
        self.assertEqual(daemon2.get_poll_interval(), 10.0)


if __name__ == "__main__":
    unittest.main()
