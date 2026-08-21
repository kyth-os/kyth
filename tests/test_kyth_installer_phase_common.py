from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.phases import common  # noqa: E402
from kyth_installer.phases import run as phase_run  # noqa: E402
from kyth_installer.context import InstallerContext, InstallLifecycle  # noqa: E402


class _ImmediateThread:
    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.joined = None

    def start(self):
        self.started = True
        self.target()

    def join(self, timeout=None):
        self.joined = timeout


class _WatchEvent:
    def __init__(self):
        self.waits = 0
        self.set_called = False

    def is_set(self):
        return self.set_called

    def wait(self, _timeout):
        self.waits += 1
        return self.waits > 1

    def set(self):
        self.set_called = True


class PhaseCommonTests(unittest.TestCase):
    def test_push_publishes_event(self):
        context = SimpleNamespace(events=SimpleNamespace(publish=mock.Mock()))
        event = {"type": "progress", "value": 50}
        common._push(event, context)
        context.events.publish.assert_called_once_with(event)

    @mock.patch("kyth_installer.assurance._battery_check")
    def test_power_boundary_allows_nonfailure(self, battery):
        battery.return_value = SimpleNamespace(status="pass", detail="AC connected")
        common._assert_still_on_ac(mock.Mock())

    @mock.patch("kyth_installer.assurance._battery_check")
    def test_power_boundary_fails_closed_with_actionable_message(self, battery):
        battery.return_value = SimpleNamespace(status="fail", detail="Battery only")
        log = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "Plug in AC power"):
            common._assert_still_on_ac(log)
        self.assertIn("Power guard refused", log.call_args.args[0])

    @mock.patch("kyth_installer.phases.common.threading.Thread", _ImmediateThread)
    @mock.patch("kyth_installer.assurance._battery_check")
    def test_power_watch_cancels_and_publishes_when_ac_is_lost(self, battery):
        battery.return_value = SimpleNamespace(status="fail", detail="AC removed")
        event = _WatchEvent()
        context = SimpleNamespace(
            cancel_requested=SimpleNamespace(set=mock.Mock()),
            events=SimpleNamespace(publish=mock.Mock()),
        )
        log = mock.Mock()

        thread = common._start_power_watch(log, context, event)

        self.assertTrue(thread.started)
        self.assertIn("Power lost during install", context._power_failed)
        context.cancel_requested.set.assert_called_once_with()
        context.events.publish.assert_called_once_with(
            {"type": "log", "text": context._power_failed}
        )
        log.assert_called_once_with(context._power_failed)

    @mock.patch("kyth_installer.phases.common.threading.Thread", _ImmediateThread)
    @mock.patch("kyth_installer.assurance._battery_check", side_effect=RuntimeError("Battery is at 9%"))
    def test_power_watch_treats_battery_runtime_error_as_ac_yank(self, _battery):
        event = _WatchEvent()
        context = SimpleNamespace(
            cancel_requested=SimpleNamespace(set=mock.Mock()),
            events=SimpleNamespace(publish=mock.Mock()),
        )
        log = mock.Mock()
        common._start_power_watch(log, context, event)
        self.assertIn("Power lost during install", context._power_failed)
        self.assertIn("Battery is at 9%", context._power_failed)
        context.cancel_requested.set.assert_called_once_with()

    @mock.patch("kyth_installer.phases.common.threading.Thread", _ImmediateThread)
    @mock.patch("kyth_installer.assurance._battery_check", side_effect=OSError("probe failed"))
    def test_power_watch_ignores_transient_probe_failure(self, _battery):
        event = _WatchEvent()
        context = SimpleNamespace(
            cancel_requested=SimpleNamespace(set=mock.Mock()),
            events=SimpleNamespace(publish=mock.Mock()),
        )
        common._start_power_watch(mock.Mock(), context, event)
        context.cancel_requested.set.assert_not_called()
        context.events.publish.assert_not_called()

    def test_stop_power_watch_sets_event_and_joins(self):
        event = mock.Mock()
        thread = mock.Mock()
        common._stop_power_watch(thread, event)
        event.set.assert_called_once_with()
        thread.join.assert_called_once_with(timeout=2)

    def test_stop_power_watch_accepts_missing_resources(self):
        common._stop_power_watch(None, None)

    @mock.patch("kyth_installer.phases.common.os.close")
    @mock.patch("kyth_installer.phases.common.fcntl.flock")
    @mock.patch("kyth_installer.phases.common.os.open", return_value=31)
    def test_disk_image_hold_locks_and_releases(self, opened, flock, closed):
        log = mock.Mock()
        with common._disk_image_hold("/dev/sda", log):
            pass
        opened.assert_called_once_with("/dev/sda", mock.ANY)
        self.assertEqual(len(flock.call_args_list), 2)
        closed.assert_called_once_with(31)
        self.assertIn("shared lock", log.call_args.args[0])

    @mock.patch("kyth_installer.phases.common.os.open", side_effect=PermissionError("denied"))
    def test_disk_image_hold_warns_when_lock_is_unavailable(self, _opened):
        log = mock.Mock()
        entered = False
        with common._disk_image_hold("/dev/sda", log):
            entered = True
        self.assertTrue(entered)
        self.assertIn("could not flock", log.call_args.args[0])

    @mock.patch("kyth_installer.phases.common.os.close", side_effect=OSError("close failed"))
    @mock.patch("kyth_installer.phases.common.fcntl.flock")
    @mock.patch("kyth_installer.phases.common.os.open", return_value=32)
    def test_disk_image_cleanup_error_does_not_mask_body_error(self, _opened, flock, _closed):
        flock.side_effect = [None, OSError("unlock failed")]
        with self.assertRaisesRegex(ValueError, "body failed"):
            with common._disk_image_hold("/dev/sda", mock.Mock()):
                raise ValueError("body failed")

    @mock.patch("kyth_installer.phases.common.write_transaction_state")
    def test_record_transaction_passes_context_and_status(self, write):
        context = object()
        common._record_transaction(context, "started", message="installing")
        write.assert_called_once_with(
            common.TRANSACTION_FILE,
            context=context,
            status="started",
            message="installing",
        )

    @mock.patch(
        "kyth_installer.phases.common.write_transaction_state",
        side_effect=OSError("read-only filesystem"),
    )
    def test_record_transaction_failure_is_logged_and_nonfatal(self, _write):
        log = mock.Mock()
        common._record_transaction(object(), "failed", log=log)
        self.assertIn("could not update installer transaction report", log.call_args.args[0])

    @mock.patch(
        "kyth_installer.phases.common.write_transaction_state",
        side_effect=OSError("read-only filesystem"),
    )
    def test_record_transaction_failure_without_logger_is_nonfatal(self, _write):
        common._record_transaction(object(), "failed")

    @mock.patch("kyth_installer.phases.common.os.close")
    @mock.patch("kyth_installer.phases.common.os.fsync")
    @mock.patch("kyth_installer.phases.common.os.open", return_value=99)
    @mock.patch("kyth_installer.phases.common.write_transaction_state")
    def test_record_transaction_success_fsyncs_parent_dir(self, write, mock_open, mock_fsync, mock_close):
        context = object()
        common._record_transaction(context, "started")
        mock_open.assert_called_once_with(str(common.TRANSACTION_FILE.parent), mock.ANY)
        mock_fsync.assert_called_once_with(99)
        mock_close.assert_called_once_with(99)

    @mock.patch("kyth_installer.phases.common.os.open", side_effect=OSError("no dir"))
    @mock.patch("kyth_installer.phases.common.write_transaction_state")
    def test_record_transaction_inner_os_error_is_suppressed(self, write, mock_open):
        log = mock.Mock()
        common._record_transaction(object(), "started", log=log)
        log.assert_not_called()
        mock_open.assert_called_once()

    @mock.patch(
        "kyth_installer.phases.common.write_transaction_state",
        side_effect=RuntimeError("boom"),
    )
    def test_record_transaction_generic_exception_is_logged(self, _write):
        log = mock.Mock()
        common._record_transaction(object(), "failed", log=log)
        self.assertIn("could not update installer transaction report", log.call_args.args[0])

    @mock.patch(
        "kyth_installer.phases.common.write_transaction_state",
        side_effect=RuntimeError("boom"),
    )
    def test_record_transaction_generic_exception_without_logger_is_nonfatal(self, _write):
        common._record_transaction(object(), "failed")


class InstallRunEntryPointTests(unittest.TestCase):
    def test_setup_failure_transitions_to_failed_and_publishes_error(self):
        context = InstallerContext()
        with mock.patch("kyth_installer.install.require_root", side_effect=PermissionError("root required")):
            phase_run._run_install(context)

        self.assertIs(context.lifecycle, InstallLifecycle.FAILED)
        errors = [event for event in context.events.events if event.get("type") == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("root required", errors[0]["message"])

    def test_successful_setup_creates_private_log_and_delegates_worker(self):
        context = InstallerContext()
        context.events.publish({"type": "stale"})
        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "installer.log"

            def worker(log, progress, alongside_mount, worker_context):
                self.assertEqual(alongside_mount, "")
                self.assertIs(worker_context, context)
                log("worker started")
                progress(17)

            with (
                mock.patch.object(phase_run, "LOG_FILE", log_path),
                mock.patch("kyth_installer.install.require_root"),
                mock.patch.object(phase_run, "_record_transaction") as record,
                mock.patch.object(phase_run, "_run_install_worker", side_effect=worker) as delegated,
            ):
                phase_run._run_install(context)

            delegated.assert_called_once()
            record.assert_called_once_with(context, "started")
            self.assertEqual(log_path.read_text(encoding="utf-8"), "worker started\n")
            self.assertEqual(log_path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn({"type": "stale"}, context.events.events)
            self.assertIn({"type": "log", "text": "worker started"}, context.events.events)
            self.assertIn({"type": "progress", "value": 17}, context.events.events)

    def test_log_write_failure_is_reported_over_event_stream(self):
        context = InstallerContext()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "installer.log"

            def worker(log, _progress, _alongside_mount, _context):
                log_path.unlink()
                log_path.mkdir()
                log("cannot persist")

            with (
                mock.patch.object(phase_run, "LOG_FILE", log_path),
                mock.patch("kyth_installer.install.require_root"),
                mock.patch.object(phase_run, "_record_transaction"),
                mock.patch.object(phase_run, "_run_install_worker", side_effect=worker),
            ):
                phase_run._run_install(context)

        logs = [event["text"] for event in context.events.events if event.get("type") == "log"]
        self.assertIn("cannot persist", logs)
        self.assertTrue(any("installer log write failed" in text for text in logs))


if __name__ == "__main__":
    unittest.main()
