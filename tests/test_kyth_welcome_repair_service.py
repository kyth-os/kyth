import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import repair  # noqa: E402


class RepairServiceTests(unittest.TestCase):
    def test_setup_transfer_helper_returns_path(self):
        path = repair.setup_transfer_helper()
        self.assertTrue(path.endswith("kyth-setup-transfer"))

    def test_command_builders_generate_expected_argv(self):
        self.assertEqual(repair.session_snapshot_command(), ["/usr/bin/kyth-session-snapshot"])
        self.assertIn("export", repair.setup_export_command("/tmp/dest"))  # noqa: S108 — fixture string
        self.assertIn("restore", repair.setup_restore_command("/tmp/archive.tar"))  # noqa: S108 — fixture string
        self.assertIn("summary", repair.setup_summary_command("/tmp/archive.tar"))  # noqa: S108 — fixture string

    def test_force_deep_sleep_success_and_failure(self):
        ok_res = MagicMock(returncode=0)
        fail_res = MagicMock(returncode=1, stderr="Operation not permitted")

        with patch("kyth_welcome.services.process.run_command", return_value=ok_res):
            ok, err = repair.force_deep_sleep()
            self.assertTrue(ok)
            self.assertEqual(err, "")

        with patch("kyth_welcome.services.process.run_command", return_value=fail_res):
            ok, err = repair.force_deep_sleep()
            self.assertFalse(ok)
            self.assertEqual(err, "Operation not permitted")

    def test_set_exe_mime_defaults_invokes_xdg_mime(self):
        with patch("kyth_welcome.services.process.run_command") as run_mock:
            repair.set_exe_mime_defaults("custom.desktop")

        self.assertEqual(run_mock.call_count, 3)
        self.assertIn("custom.desktop", run_mock.call_args_list[0].args[0])

    def test_task_manager_commands_returns_lists(self):
        with patch("shutil.which", return_value="/usr/bin/plasma-systemmonitor"):
            cmds = repair.task_manager_commands()

        self.assertGreaterEqual(len(cmds), 1)
        self.assertIn(["plasma-systemmonitor"], cmds)

    def test_sleep_mode_label(self):
        self.assertEqual(
            repair.sleep_mode_label("s2idle [deep]"), "S3 deep (good)"
        )
        self.assertEqual(
            repair.sleep_mode_label("[s2idle] deep"),
            "s2idle (modern standby — may wake early)",
        )
        self.assertEqual(repair.sleep_mode_label("freeze"), "freeze")
        self.assertEqual(repair.sleep_mode_label(""), "unknown")


if __name__ == "__main__":
    unittest.main()
