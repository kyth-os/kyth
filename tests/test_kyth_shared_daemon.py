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
    def __init__(self, *, abort_on_start=False, **kwargs):
        super().__init__("mock-daemon", **kwargs)
        self.abort_on_start = abort_on_start
        self.start_called = False
        self.poll_called = False
        self.stop_called = False

    def on_start(self):
        self.start_called = True
        if self.abort_on_start:
            # e.g. a privilege check that must prevent poll() from ever
            # running, not just make it a no-op.
            self._exit_code = 1
            self.running = False

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

    @mock.patch("signal.signal")
    def test_on_start_can_abort_before_poll_runs(self, mock_signal):
        # run() must not reset self.running = True after on_start() returns —
        # otherwise a subclass's on_start() can never actually prevent poll()
        # from executing once, only reduce it to a no-op via other state.
        daemon = MockDaemon(oneshot=True, abort_on_start=True)
        exit_code = daemon.run()

        self.assertEqual(exit_code, 1)
        self.assertTrue(daemon.start_called)
        self.assertFalse(daemon.poll_called)
        self.assertTrue(daemon.stop_called)

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

    def test_non_finite_or_out_of_range_poll_interval_is_sanitized(self):
        # TOML parses inf/nan; they used to escape run() as OverflowError /
        # ValueError from int(interval * 2) and kill the daemon.
        cases = {
            float("inf"): 10.0,
            float("-inf"): 10.0,
            float("nan"): 10.0,
            0: 10.0,
            -5: 10.0,
            0.01: BaseDaemon.MIN_POLL_INTERVAL,
            1e12: BaseDaemon.MAX_POLL_INTERVAL,
        }
        for raw, expected in cases.items():
            daemon = MockDaemon(
                default_config={"poll_interval": raw},
                poll_interval_key="poll_interval",
                default_poll_interval=10.0,
            )
            daemon.load_config()
            got = daemon.get_poll_interval()
            self.assertEqual(got, expected, f"raw={raw!r}")
            int(got * 2)  # the loop's own conversion must not raise

    @mock.patch("signal.signal")
    @mock.patch("time.sleep")
    def test_run_survives_a_loop_tick_with_infinite_interval(self, _sleep, _signal):
        daemon = MockDaemon(
            default_config={"poll_interval": float("inf")},
            poll_interval_key="poll_interval",
            default_poll_interval=1.0,
        )
        polls = []

        def poll_once():
            polls.append(1)
            if len(polls) >= 2:
                daemon.running = False

        daemon.poll = poll_once
        self.assertEqual(daemon.run(), 0)
        self.assertEqual(len(polls), 2)


if __name__ == "__main__":
    unittest.main()
