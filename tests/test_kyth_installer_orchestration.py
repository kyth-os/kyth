from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.assurance import _battery_check  # noqa: E402
from kyth_installer.context import InstallLifecycle, InstallPhase, InstallerContext  # noqa: E402
from kyth_installer.execution import InstallCancelled, check_cancelled  # noqa: E402
from kyth_installer.phases.common import _record_transaction  # noqa: E402
from kyth_installer import orchestration  # noqa: E402


class InstallerOrchestrationTests(unittest.TestCase):
    @patch("kyth_installer.orchestration._which", return_value="/usr/bin/kyth-installer-exec")
    @patch("kyth_installer.orchestration._as_root", side_effect=lambda command: command)
    @patch("kyth_installer.orchestration.run_command")
    def test_native_operation_requires_a_typed_json_object(self, run_command, _as_root, _which):
        run_command.return_value = SimpleNamespace(stdout=json.dumps({"status": "pass"}))
        self.assertEqual(
            orchestration.native_operation("power-check", {}),
            {"status": "pass"},
        )
        run_command.return_value = SimpleNamespace(stdout="[]")
        with self.assertRaisesRegex(RuntimeError, "non-object"):
            orchestration.native_operation("power-check", {})

    @patch("kyth_installer.orchestration.decision")
    def test_context_uses_native_lifecycle_and_phase_decisions(self, decision):
        decision.side_effect = [
            {"accepted": True, "lifecycle": "validated", "phase": "prepare"},
            {"accepted": True, "lifecycle": "validated", "phase": "storage"},
        ]
        context = InstallerContext()
        context.transition(InstallLifecycle.VALIDATED)
        context.lifecycle = InstallLifecycle.INSTALLING
        context.enter_phase(InstallPhase.STORAGE)
        self.assertEqual(context.phase, InstallPhase.STORAGE)
        self.assertEqual(decision.call_args_list[0].args[0], "transition")
        self.assertEqual(decision.call_args_list[1].args[0], "phase")

    @patch("kyth_installer.orchestration.decision", return_value=None)
    def test_missing_native_helper_keeps_compatibility_state_machine(self, _decision):
        context = InstallerContext()
        context.transition(InstallLifecycle.VALIDATED)
        with self.assertRaisesRegex(RuntimeError, "Invalid installer lifecycle transition"):
            context.transition(InstallLifecycle.DONE)

    @patch("kyth_installer.orchestration.decision")
    def test_native_cancellation_preserves_destructive_warning(self, decision):
        decision.return_value = {
            "accepted": True,
            "cancelled": True,
            "cancel_message": "Installation cancelled by user. Disk changes may have already started.",
        }
        context = InstallerContext()
        context.lifecycle = InstallLifecycle.INSTALLING
        context.phase = InstallPhase.IMAGE
        context.cancel_requested.set()
        with self.assertRaisesRegex(InstallCancelled, "Disk changes may have already started"):
            check_cancelled(context)

    @patch("kyth_installer.orchestration.power_check")
    def test_native_power_probe_is_used_for_default_power_root(self, power_check):
        power_check.return_value = {"status": "pass", "detail": "Battery is 88% (charging)"}
        result = _battery_check()
        self.assertEqual(result.detail, "Battery is 88% (charging)")

    @patch("kyth_installer.orchestration.decision", return_value=None)
    @patch("kyth_installer.phases.common.write_transaction_state")
    def test_compatibility_transaction_updates_status_after_validation(self, write, _decision):
        context = InstallerContext()
        _record_transaction(context, "started")
        self.assertEqual(context.transaction_status, "started")
        write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
