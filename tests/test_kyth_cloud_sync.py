"""Cloud sync pure helpers."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.cloud_sync import (  # noqa: E402
    extract_rclone_token,
    rclone_sync_command,
    rsync_copy_command,
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


if __name__ == "__main__":
    unittest.main()
