"""Phase C pure helpers: repair, sched, telem, wizard package surface."""
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import repair, sched, telem  # noqa: E402

class RepairServiceTests(unittest.TestCase):
    def test_command_builders(self):
        self.assertEqual(repair.session_snapshot_command()[0], "/usr/bin/kyth-session-snapshot")
        export = repair.setup_export_command("/tmp/out")  # noqa: S108 — fixture string, not a real path opened on disk
        self.assertEqual(export[1], "export")
        self.assertEqual(export[2], "/tmp/out")  # noqa: S108 — fixture string, not a real path opened on disk
        rollback = repair.rollback_command()
        self.assertIn("bootc", rollback)
        self.assertIn("rollback", rollback)
        reset = repair.reset_command()
        self.assertIn("reset", reset)

    def test_read_sys_text_missing(self):
        self.assertEqual(repair.read_sys_text("/nonexistent/kyth-path"), "")


class SchedServiceTests(unittest.TestCase):
    def test_list_schedulers_fallback(self):
        with patch("kyth_welcome.services.sched.subprocess.run", side_effect=FileNotFoundError):
            with patch("kyth_welcome.services.sched.glob.glob", return_value=[]):
                names = sched.list_schedulers()
        self.assertIn("scx_lavd", names)

    def test_read_sched_status_missing(self):
        with patch.object(sched, "status_file_path", return_value=pathlib.Path("/no/such/status.json")):
            self.assertEqual(sched.read_sched_status(), {})


class TelemServiceTests(unittest.TestCase):
    def test_recent_sessions_missing_db(self):
        with patch.object(telem, "telemetry_db_path", return_value=pathlib.Path("/no/such/telemetry.db")):
            self.assertEqual(telem.recent_sessions(), [])

    def test_session_row_labels(self):
        row = telem.SessionRow(
            game_name="Demo",
            started_at=1_700_000_000,
            duration_s=125,
            avg_fps=120.4,
            p1_low_fps=90.1,
            stutter_count=2,
            scheduler="scx_lavd",
        )
        self.assertEqual(row.duration_label, "2m 05s")
        self.assertIn("/", row.fps_label)
        self.assertNotEqual(row.date_label, "—")


class WizardPackageTests(unittest.TestCase):
    def test_wizard_package_layout(self):
        """Structure check without importing Qt pages (avoids suite import-order cycles)."""
        import ast

        wizard_dir = ROOT / "build_files" / "kyth-welcome" / "kyth_welcome" / "wizard"
        expected = {
            "window.py": "WizardWindow",
            "steps_welcome.py": "_WelcomeStepMixin",
            "steps_machine.py": "_MachineStepMixin",
            "steps_apps.py": "_AppsStepMixin",
            "steps_gaming.py": "_GamingStepMixin",
            "steps_finish.py": "_FinishStepMixin",
        }
        for filename, classname in expected.items():
            path = wizard_dir / filename
            self.assertTrue(path.is_file(), filename)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            classes = {
                node.name for node in tree.body if isinstance(node, ast.ClassDef)
            }
            self.assertIn(classname, classes, f"{filename} missing {classname}")

        window_src = (wizard_dir / "window.py").read_text(encoding="utf-8")
        for method in (
            "_make_welcome_step",
            "_make_machine_step",
            "_make_first_run_apps_step",
            "_make_gaming_step",
            "_make_finish_step",
        ):
            # Methods live on mixins or shell; package as a whole must define them.
            found = any(
                method in (wizard_dir / name).read_text(encoding="utf-8")
                for name in expected
            )
            self.assertTrue(found, method)
        self.assertIn("_WelcomeStepMixin", window_src)

if __name__ == "__main__":
    unittest.main()
