"""Cloud sync pure helpers."""
import importlib.util
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.cloud_sync import (  # noqa: E402
    extract_rclone_token,
    rclone_sync_command,
    rsync_copy_command,
)
HAS_QT = any(importlib.util.find_spec(binding) for binding in ("PySide6", "PyQt6"))
if HAS_QT:
    from kyth_welcome.services.workers.cloud_sync import (
        RcloneAuthorizeWorker,
        RcloneSyncWorker,
    )


class CloudSyncHelperTests(unittest.TestCase):
    def test_extract_token_paste_markers(self):
        text = """
Some noise
Paste the following into your remote machine --->
{"access_token":"abc","token_type":"Bearer"}
<---End paste
"""
        self.assertEqual(
            extract_rclone_token(text),
            '{"access_token":"abc","token_type":"Bearer"}',
        )

    def test_extract_token_json_regex(self):
        text = 'noise {"access_token":"xyz"} trailing'
        self.assertEqual(extract_rclone_token(text), '{"access_token":"xyz"}')

    def test_extract_token_missing(self):
        self.assertIsNone(extract_rclone_token("no token here"))

    def test_command_builders(self):
        sync = rclone_sync_command("gdrive", "/home/u/Drive")
        self.assertEqual(sync[:3], ["rclone", "sync", "gdrive:"])
        copy = rsync_copy_command("/src", "/dst")
        self.assertEqual(copy[0], "rsync")
        self.assertTrue(copy[-2].endswith("/"))
        self.assertTrue(copy[-1].endswith("/"))

    @unittest.skipUnless(HAS_QT, "PySide6/PyQt6 is not installed on this validation runner")
    def test_sync_worker_stop_terminates_retained_process(self):
        worker = RcloneSyncWorker("gdrive", "/tmp/drive")  # noqa: S108 — fixture string, not a real path opened on disk
        proc = MagicMock()
        proc.poll.return_value = None
        worker._proc = proc

        worker.stop()

        proc.terminate.assert_called_once_with()

    @unittest.skipUnless(HAS_QT, "PySide6/PyQt6 is not installed on this validation runner")
    def test_authorize_timeout_kills_and_reaps_process(self):
        proc = MagicMock()
        proc.communicate.side_effect = subprocess.TimeoutExpired("rclone", 300)
        with patch(
            "kyth_welcome.services.workers.cloud_sync.subprocess.Popen",
            return_value=proc,
        ):
            RcloneAuthorizeWorker("drive").run()

        proc.kill.assert_called_once_with()
        proc.wait.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
