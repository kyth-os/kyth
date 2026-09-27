import json
import stat
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.update_status import (  # noqa: E402
    UpdateSnapshot,
    read_update_snapshot,
    write_update_snapshot,
)


class UpdateSnapshotTests(unittest.TestCase):
    def test_state_uses_shared_digest_comparison(self):
        self.assertEqual(
            UpdateSnapshot(booted_digest="sha256:a", remote_digest="sha256:a").system_state,
            "uptodate",
        )
        self.assertEqual(
            UpdateSnapshot(booted_digest="sha256:a", remote_digest="sha256:b").system_state,
            "available",
        )
        self.assertEqual(
            UpdateSnapshot(staged_digest="sha256:b").system_state,
            "staged",
        )

    def test_atomic_roundtrip_and_freshness(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "status.json"
            expected = UpdateSnapshot(
                result="no_change",
                ts=1_000,
                flatpak_updates=2,
                booted_digest="sha256:a",
                remote_digest="sha256:a",
            )
            write_update_snapshot(expected, path)
            self.assertEqual(read_update_snapshot(path), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(read_update_snapshot(path, max_age=60, now=1_030), expected)
            self.assertIsNone(read_update_snapshot(path, max_age=60, now=1_061))

    def test_reads_legacy_watcher_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "status.json"
            path.write_text(json.dumps({"result": "skipped", "ts": 10}))
            snapshot = read_update_snapshot(path)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot.result, "skipped")
            self.assertEqual(snapshot.remote_digest, "")


if __name__ == "__main__":
    unittest.main()
