"""Shared journal validation cases for the Rust and Python implementations."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import partition_ops_journal as journal_mod  # noqa: E402


FIXTURE = ROOT / "src" / "kyth-installer-web" / "src-tauri" / "testdata" / "journal_cases.json"


class InstallerJournalParityTests(unittest.TestCase):
    def test_python_journal_matches_shared_validation_cases(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                journal = journal_mod.Journal.__new__(journal_mod.Journal)
                journal.disk = "/dev/sda"
                journal.ops = []
                journal._committed = False
                journal._root_partition = None
                for operation in case["ops"]:
                    journal.add_op(operation["kind"], operation["params"])

                with mock.patch.object(journal_mod, "list_partitions", return_value=case["partitions"]), \
                     mock.patch.object(journal_mod, "list_disks", return_value=[{
                         "name": "/dev/sda",
                         "size_bytes": case["disk_size_bytes"],
                         "partition_table": case["table_type"],
                     }]), \
                     mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"), \
                     mock.patch.object(journal_mod, "_normal_device_path", side_effect=lambda value: value):
                    errors = journal.validate()

                for expected in case["expected_errors"]:
                    self.assertTrue(any(expected in error for error in errors), (case["name"], errors))
                if case["name"] == "single-btrfs-root":
                    self.assertEqual(errors, [])

    def test_installed_rust_validator_is_authoritative(self):
        journal = journal_mod.Journal.__new__(journal_mod.Journal)
        journal.disk = "/dev/sda"
        journal.ops = [{
            "kind": "set_mountpoint",
            "params": {"partition": "/dev/sda2", "mountpoint": "/"},
            "index": 0,
        }]
        journal._committed = False
        journal._root_partition = None
        journal.irreversible_completed = False
        with (
            mock.patch.object(journal_mod.shutil, "which", return_value="/usr/bin/kyth-installer-exec"),
            mock.patch(
                "kyth_installer.runner.run_command",
                side_effect=OSError("helper unavailable"),
            ),
        ):
            errors = journal._rust_validate([], "gpt", 128 * 1024**3)
        self.assertEqual(
            errors,
            ["Rust journal validation failed; refusing to commit partition changes."],
        )

    def test_rust_validator_rejects_inconsistent_response(self):
        journal = journal_mod.Journal.__new__(journal_mod.Journal)
        journal.disk = "/dev/sda"
        journal.ops = []
        journal._committed = False
        journal._root_partition = None
        journal.irreversible_completed = False
        completed = mock.Mock(stdout=json.dumps({"valid": True, "errors": ["bad"]}))
        with (
            mock.patch.object(journal_mod.shutil, "which", return_value="/usr/bin/kyth-installer-exec"),
            mock.patch("kyth_installer.runner.run_command", return_value=completed),
        ):
            errors = journal._rust_validate([], "gpt", 128 * 1024**3)
        self.assertEqual(
            errors,
            ["Rust journal validation failed; refusing to commit partition changes."],
        )


if __name__ == "__main__":
    unittest.main()
