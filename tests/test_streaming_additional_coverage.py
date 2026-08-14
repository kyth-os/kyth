import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.streaming import StreamingCommandRunner


class StreamingAdditionalCoverageTests(unittest.TestCase):
    def test_stdout_is_none_raises(self):
        """Covers 67-69: spawn returns proc with stdout None."""
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _e: None)
        fake_proc = mock.Mock()
        fake_proc.stdout = None
        fake_proc.kill = mock.Mock()
        fake_proc.wait = mock.Mock()
        with mock.patch("kyth_installer.streaming.spawn_command", return_value=fake_proc):
            with self.assertRaisesRegex(RuntimeError, "Could not capture"):
                runner.run([sys.executable, "-c", "print('hi')"], 0, 100, lambda m: None, lambda p: None)

    def test_duplicate_line_suppressed(self):
        """Covers 118: duplicate stripped == last_line early return."""
        logs = []
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _e: None)
        # Need layers needed parsing to hit 118 path; duplicate suppression
        # happens for any repeated stripped line. Send same log twice.
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            runner.run(
                [sys.executable, "-c", "print('hello'); print('hello'); print('hello')"],
                0, 100, logs.append, lambda p: None,
            )
        # logs includes "$ ..." plus one "hello", duplicates suppressed
        hello_logs = [l for l in logs if l == "hello"]
        self.assertEqual(hello_logs, ["hello"])

    def test_malformed_layers_needed_does_not_abort(self):
        """Covers 129-132: exception while parsing layers needed size."""
        logs = []
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _e: None)
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            # "layers needed:" without proper size format triggers exception path
            # but must not abort install
            runner.run(
                [sys.executable, "-c", "print('layers needed: 1 (not-a-size)', flush=True)"],
                0, 100, logs.append, lambda p: None,
                stall_timeout=5, absolute_timeout=5,
            )
        self.assertTrue(any("layers needed" in l for l in logs))

    def test_pending_without_newline_flushed_on_final(self):
        """Covers 144-146: pending text without trailing newline flushed at end."""
        logs = []
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _e: None)
        # Use python to write without newline directly to stdout
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            runner.run(
                [sys.executable, "-c", "import sys; sys.stdout.write('noprefix_no_newline'); sys.stdout.flush()"],
                0, 100, logs.append, lambda p: None,
            )
        self.assertTrue(any("noprefix_no_newline" in l for l in logs))

    def test_net_monitor_handles_zero_total(self):
        """Covers 88-89: net_monitor with total <=0 sets tracker None and continues."""
        logs = []
        pushed = []
        # Use a command that sleeps without emitting layers needed, so total stays 0
        # Monitor interval short so at least one tick sees total 0
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=pushed.append, monitor_interval=0.01)
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            runner.run(
                [sys.executable, "-c", "import time; time.sleep(0.3); print('done')"],
                0, 100, logs.append, lambda p: None,
                stall_timeout=5, absolute_timeout=5,
            )
        # No stats should be pushed when total is 0, but monitor must have run without error
        # and not crashed (would have stayed at 0 progress)
        self.assertTrue(any("done" in l for l in logs))

    def test_io_and_network_timeouts(self):
        """Covers 183,187: io_timeout and net_timeout raise RuntimeError."""
        # io timeout: command produces no output for longer than io_timeout
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _e: None)
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            with self.assertRaisesRegex(RuntimeError, "no output"):
                runner.run(
                    [sys.executable, "-c", "import time; time.sleep(2)"],
                    0, 100, lambda m: None, lambda p: None,
                    io_stall_timeout=1, stall_timeout=1, absolute_timeout=10,
                )
        # net timeout: layers needed sets total >0 but rx_bytes never advances
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            with self.assertRaisesRegex(RuntimeError, "no network"):
                runner.run(
                    [sys.executable, "-c", "print('layers needed: 1 (10 MB)', flush=True); import time; time.sleep(2)"],
                    0, 100, lambda m: None, lambda p: None,
                    net_stall_timeout=1, stall_timeout=10, absolute_timeout=10,
                )

    def test_rx_progress_updates_last_rx(self):
        """Covers 176-177: rx_now > last_rx updates last_rx_activity."""
        # rx_bytes increments -> triggers branch
        rx_val = [0]

        def rx():
            rx_val[0] += 1024
            return rx_val[0]

        logs = []
        runner = StreamingCommandRunner(rx_bytes=rx, publish=lambda _e: None, monitor_interval=0.05)
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            runner.run(
                [sys.executable, "-c", "print('layers needed: 1 (5 MB)', flush=True); import time; time.sleep(0.4); print('done')"],
                0, 100, logs.append, lambda p: None,
                stall_timeout=5, absolute_timeout=5,
            )
        self.assertTrue(any("done" in l for l in logs))

    def test_absolute_timeout(self):
        """Covers 179: absolute_timeout exceed."""
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _e: None)
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            with self.assertRaisesRegex(RuntimeError, "absolute timeout"):
                runner.run(
                    [sys.executable, "-c", "import time; time.sleep(2)"],
                    0, 100, lambda m: None, lambda p: None,
                    absolute_timeout=1, stall_timeout=10,
                )

    def test_error_factory_on_failure_covers_195_branch(self):
        """Covers 195: exception path kills proc then re-raises."""
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _e: None)
        with mock.patch("kyth_installer.runner._validate_executable", side_effect=lambda x: x):
            # Command exits non-zero; also test exception during wait path by forcing select error?
            # Here cover the generic except->kill branch
            with self.assertRaisesRegex(RuntimeError, "exit 2"):
                runner.run(
                    [sys.executable, "-c", "import sys; print('fail line'); sys.exit(2)"],
                    0, 100, lambda m: None, lambda p: None,
                )

    def test_cancel_with_terminate_and_kill_paths(self):
        """Covers 153-159: cancel_event triggers terminate, then kill on timeout."""
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _e: None)
        # Mock proc to simulate poll returning None then wait timing out
        fake_proc = mock.Mock()
        fake_stdout = mock.Mock()
        fake_stdout.fileno.return_value = 99
        fake_proc.stdout = fake_stdout
        fake_proc.poll.return_value = None
        fake_proc.terminate = mock.Mock()
        fake_proc.kill = mock.Mock()
        fake_proc.wait = mock.Mock(side_effect=[Exception("timeout"), None, None])
        fake_proc.returncode = 0
        # select will indicate ready once, then cancel path will be taken on next loop
        # Simplify: set cancel_event already set, so first loop iteration hits cancel
        cancelled = threading.Event()
        cancelled.set()
        with mock.patch("kyth_installer.streaming.spawn_command", return_value=fake_proc), \
             mock.patch("kyth_installer.streaming.select.select", return_value=([], [], [])), \
             mock.patch("kyth_installer.streaming.os.read", return_value=b""):
            from kyth_installer.execution import InstallCancelled
            with self.assertRaises(InstallCancelled):
                runner.run(
                    [sys.executable, "-c", "import time; time.sleep(10)"],
                    0, 100, lambda m: None, lambda p: None,
                    cancel_event=cancelled,
                )
