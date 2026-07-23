"""Canonical account-database repair used by both install paths.

kyth_installer.system.ensure_system_accounts and
build_files/kyth-partition-install.sh's ensure_system_accounts both delegate
to kyth_shared.accounts now instead of independently reimplementing this
logic; these tests exercise the shared implementation directly.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import accounts  # noqa: E402


def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class EnsureSystemAccountsTests(unittest.TestCase):
    def test_merges_missing_records_and_locks_down_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root / "usr/lib/passwd",
                   "sddm:x:959:959:SDDM Greeter Account:/var/lib/sddm:/usr/sbin/nologin\n"
                   "foo:x:100:100::/home/foo:/sbin/nologin\n")
            _write(root / "usr/lib/group", "sddm:x:959:\nfoo:x:100:\n")
            _write(root / "etc/passwd", "root:x:0:0:root:/root:/bin/bash\n")
            _write(root / "etc/group", "root:x:0:\n")
            _write(root / "etc/shadow", "root:!locked:19700:0:99999:7:::\n")

            messages = []
            accounts.ensure_system_accounts(str(root), messages.append, run=accounts._default_run)

            shadow_path = root / "etc/shadow"
            self.assertEqual(shadow_path.stat().st_mode & 0o777, 0o000)
            try:
                # chmod 0o000 on our own file still blocks our own read() —
                # restore access to check content, matching the pattern used
                # for the same real-permission-lockdown behavior elsewhere.
                shadow_path.chmod(0o600)
                shadow = shadow_path.read_text()
            finally:
                shadow_path.chmod(0o000)

            passwd = (root / "etc/passwd").read_text()
            group = (root / "etc/group").read_text()
            self.assertIn("sddm:", passwd)
            self.assertIn("foo:", passwd)
            self.assertIn("sddm:", group)
            self.assertIn("foo:", group)
            self.assertIn("sddm:!*:19700:0:99999:7:::", shadow)
            self.assertIn("foo:!*:19700:0:99999:7:::", shadow)
            # root's existing shadow record must be untouched, not duplicated.
            self.assertEqual(shadow.count("root:!locked"), 1)

            self.assertEqual((root / "etc/passwd").stat().st_mode & 0o777, 0o644)
            self.assertEqual((root / "etc/group").stat().st_mode & 0o777, 0o644)
            self.assertTrue((root / "var/lib/sddm").is_dir())
            self.assertTrue(any("Repaired" in m for m in messages))

    def test_no_changes_still_re_locks_existing_shadow(self):
        """A shadow file that already has every account must still get chmod 0000
        even when nothing was appended (e.g. re-running after a partial repair
        left it readable)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root / "etc/passwd", "root:x:0:0:root:/root:/bin/bash\n")
            _write(root / "etc/group", "root:x:0:\n")
            shadow_path = root / "etc/shadow"
            _write(shadow_path, "root:!locked:19700:0:99999:7:::\n")
            shadow_path.chmod(0o600)

            accounts.ensure_system_accounts(str(root), lambda _msg: None, run=accounts._default_run)

            self.assertEqual(shadow_path.stat().st_mode & 0o777, 0o000)

    def test_sddm_home_chowned_by_target_uid_gid_not_literal_name(self):
        """The target tree's own sddm uid/gid must be used (not the string
        'sddm'), since the process's own /etc/passwd may not have that user
        or may allocate it a different id than the target image did."""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root / "etc/passwd",
                   "root:x:0:0:root:/root:/bin/bash\n"
                   "sddm:x:777:888:SDDM Greeter Account:/var/lib/sddm:/usr/sbin/nologin\n")
            _write(root / "etc/group", "root:x:0:\nsddm:x:888:\n")

            calls = []

            def fake_run(argv, **kwargs):
                calls.append(list(argv))
                if argv[0] == "cat":
                    path = pathlib.Path(argv[1])
                    if path.exists():
                        return subprocess.CompletedProcess(argv, 0, stdout=path.read_text(), stderr="")
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
                if argv[0] == "test":
                    exists = pathlib.Path(argv[2]).exists()
                    return subprocess.CompletedProcess(argv, 0 if exists else 1)
                if argv[0] == "mkdir":
                    pathlib.Path(argv[2]).mkdir(parents=True, exist_ok=True)
                    return subprocess.CompletedProcess(argv, 0)
                if argv[0] == "tee":
                    path = pathlib.Path(argv[1])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(kwargs.get("input", ""))
                    return subprocess.CompletedProcess(argv, 0)
                if argv[0] == "chmod":
                    pathlib.Path(argv[2]).chmod(int(argv[1], 8))
                    return subprocess.CompletedProcess(argv, 0)
                return subprocess.CompletedProcess(argv, 0)

            accounts.ensure_system_accounts(str(root), lambda _msg: None, run=fake_run)

            chown_calls = [c for c in calls if c[0] == "chown"]
            self.assertEqual(len(chown_calls), 1)
            self.assertEqual(chown_calls[0][1], "777:888")

    def test_cli_rejects_wrong_argument_count(self):
        self.assertEqual(accounts.main([]), 64)
        self.assertEqual(accounts.main(["a", "b"]), 64)

    def test_cli_repairs_target_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root / "usr/lib/passwd",
                   "sddm:x:959:959:SDDM Greeter Account:/var/lib/sddm:/usr/sbin/nologin\n")
            _write(root / "usr/lib/group", "sddm:x:959:\n")
            _write(root / "etc/passwd", "root:x:0:0:root:/root:/bin/bash\n")
            _write(root / "etc/group", "root:x:0:\n")

            self.assertEqual(accounts.main([str(root)]), 0)
            self.assertIn("sddm:", (root / "etc/passwd").read_text())


if __name__ == "__main__":
    unittest.main()
