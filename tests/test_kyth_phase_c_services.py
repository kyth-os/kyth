"""Pure service helpers retained while the Hub UI is migrated to Tauri."""
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
        export = repair.setup_export_command("/tmp/out")
        self.assertEqual(export[1:], ["export", "/tmp/out"])
        self.assertIn("bootc", repair.rollback_command())
        self.assertIn("rollback", repair.rollback_command())
        self.assertIn("reset", repair.reset_command())

    def test_read_sys_text_missing(self):
        self.assertEqual(repair.read_sys_text("/nonexistent/kyth-path"), "")

class SchedServiceTests(unittest.TestCase):
    def test_list_schedulers_fallback(self):
        with patch("kyth_welcome.services.sched.subprocess.run", side_effect=FileNotFoundError):
            with patch("kyth_welcome.services.sched.glob.glob", return_value=[]):
                self.assertIn("scx_rusty", sched.list_schedulers())

    def test_read_sched_status_missing(self):
        with patch.object(sched, "status_file_path", return_value=pathlib.Path("/no/such/status.json")):
            self.assertEqual(sched.read_sched_status(), {})

class TelemServiceTests(unittest.TestCase):
    def test_recent_sessions_missing_db(self):
        with patch.object(telem, "telemetry_db_path", return_value=pathlib.Path("/no/such/telemetry.db")):
            self.assertEqual(telem.recent_sessions(), [])

    def test_session_row_labels(self):
        row = telem.SessionRow(
            game_name="Demo", started_at=1_700_000_000, duration_s=125,
            avg_fps=120.4, p1_low_fps=90.1, stutter_count=2, scheduler="scx_rusty",
        )
        self.assertEqual(row.duration_label, "2m 05s")
        self.assertIn("/", row.fps_label)
        self.assertNotEqual(row.date_label, "—")

if __name__ == "__main__":
    unittest.main()
