import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.cleanup import clear_secrets_and_orphan_mount, unmount_configuration  # noqa: E402
from kyth_installer.context import InstallLifecycle, InstallRequest, InstallerContext  # noqa: E402
from kyth_installer.execution import (  # noqa: E402
    InstallCancelled,
    check_cancelled,
    request_cancel,
    start_installation,
)
from kyth_installer.phases.preflight import _prepare_install_context  # noqa: E402


class ImmediateThread:
    def __init__(self, *, target, daemon):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class InstallerLifecycleCoverageTests(unittest.TestCase):
    def test_preflight_phase_delegates_to_install_implementation(self):
        context = InstallerContext()
        log = MagicMock()
        expected = object()
        with patch("kyth_installer.install._prepare_install_context", return_value=expected) as prepare:
            result = _prepare_install_context(log, context)
        self.assertIs(result, expected)
        prepare.assert_called_once_with(log, context)

    def test_alongside_cleanup_unmounts_nested_home_then_root(self):
        run = MagicMock()
        unmount_configuration("/unused", "/run/target", run=run)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[0].args[0][-1], "sync")
        self.assertEqual(
            run.call_args_list[1].args[0][-1],
            "/run/target/ostree/deploy/default/var/home",
        )
        self.assertEqual(run.call_args_list[2].args[0][-1], "/run/target")

    def test_secret_cleanup_without_orphan_only_clears_credentials(self):
        state = {"password_hash": "hash", "mok_password": "mok"}
        run = MagicMock()
        clear_secrets_and_orphan_mount(state, "", run=run)
        self.assertEqual(state, {"password_hash": "", "mok_password": ""})
        run.assert_not_called()

    @patch("kyth_installer.execution.threading.Thread", ImmediateThread)
    @patch("kyth_installer.recovery.write_failure_summary", side_effect=OSError("read-only"))
    def test_cancelled_worker_fails_closed_even_if_summary_write_fails(self, write_summary):
        context = InstallerContext()

        def cancel(_context):
            raise InstallCancelled("operator cancelled")

        self.assertTrue(start_installation(context, InstallRequest(), cancel))
        self.assertEqual(context.lifecycle, InstallLifecycle.FAILED)
        self.assertIn(
            {"type": "error", "message": "operator cancelled"},
            context.events.events,
        )
        write_summary.assert_called_once()
        self.assertFalse(context.install_lock.locked())
        self.assertFalse(context.cancel_requested.is_set())

    @patch("kyth_installer.execution.threading.Thread", ImmediateThread)
    @patch("kyth_installer.recovery.write_failure_summary")
    def test_cancel_reporting_survives_failed_lifecycle_transition(self, write_summary):
        context = MagicMock()
        context.install_lock = threading.Lock()
        context.cancel_requested = threading.Event()
        context.transition.side_effect = [None, None, RuntimeError("invalid transition")]

        def cancel(_context):
            raise InstallCancelled("operator cancelled")

        self.assertTrue(start_installation(context, InstallRequest(), cancel))
        context.events.publish.assert_called_once_with(
            {"type": "error", "message": "operator cancelled"}
        )
        write_summary.assert_called_once()
        self.assertFalse(context.install_lock.locked())

    def test_cancel_rejected_outside_cancellable_lifecycle(self):
        context = InstallerContext()
        context.install_lock.acquire()
        try:
            self.assertFalse(request_cancel(context))
            self.assertFalse(context.cancel_requested.is_set())
        finally:
            context.install_lock.release()

    def test_check_cancelled_is_noop_without_request(self):
        context = InstallerContext()
        self.assertIsNone(check_cancelled(context))


if __name__ == "__main__":
    unittest.main()
