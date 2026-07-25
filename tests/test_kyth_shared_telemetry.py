import unittest
import tempfile
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.telemetry import recent_sessions, SessionRow


class TestKythSharedTelemetry(unittest.TestCase):
    def test_session_row_labels(self):
        # average case
        row = SessionRow(
            game_name="Cyberpunk",
            started_at=1700000000.0,
            duration_s=3665.0,
            avg_fps=59.4,
            p1_low_fps=45.1,
            stutter_count=5,
            scheduler="scx_rusty",
        )
        self.assertEqual(row.duration_label, "61m 05s")
        self.assertEqual(row.fps_label, "59 / 45 1%")
        self.assertTrue(len(row.date_label) > 0)

        # None values
        row_none = SessionRow(
            game_name="Unknown",
            started_at=None,
            duration_s=None,
            avg_fps=None,
            p1_low_fps=None,
            stutter_count=0,
            scheduler="",
        )
        self.assertEqual(row_none.date_label, "—")
        self.assertEqual(row_none.duration_label, "—")
        self.assertEqual(row_none.fps_label, "—")

    def test_recent_sessions_db_query(self):
        # Create temp DB
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_db.close()
        
        try:
            conn = sqlite3.connect(temp_db.name)
            conn.execute(
                "CREATE TABLE sessions (game_name TEXT, started_at REAL, "
                "duration_s REAL, avg_fps REAL, p1_low_fps REAL, "
                "stutter_count INTEGER, scheduler TEXT)"
            )
            conn.execute(
                "INSERT INTO sessions VALUES ('Doom', 1700000000.0, 120.0, 144.0, 120.0, 0, 'scx_rusty')"
            )
            conn.commit()
            conn.close()

            with patch("kyth_shared.telemetry.telemetry_db_path", return_value=Path(temp_db.name)):
                sessions = recent_sessions(limit=5)
                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0].game_name, "Doom")
                self.assertEqual(sessions[0].avg_fps, 144.0)
        finally:
            os.remove(temp_db.name)


if __name__ == "__main__":
    unittest.main()
