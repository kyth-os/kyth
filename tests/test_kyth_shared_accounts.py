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
from unittest import mock

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
                    # lgtm[py/clear-text-storage-sensitive-data]
                    # This fake `run` stands in for the real root-escalated
                    # `tee` used to write /etc/shadow itself, whose whole job
                    # is storing password hashes in a plain (permission-
                    # locked, not encrypted) file, matching real Unix shadow
                    # file semantics — not a credential-handling bug, and the
                    # data here is a synthetic test fixture, never a real
                    # secret.
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


def _fake_useradd_run(useradd_uid_gid="1000:1000"):
    """A fake run() simulating enough of useradd/cat/tee/mkdir/chown/chmod/cp
    to exercise create_installer_user's own logic without needing real root
    privileges (useradd --root and chown to an arbitrary uid both do)."""
    uid, gid = useradd_uid_gid.split(":")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[0] == "useradd":
            root = pathlib.Path(argv[2])
            username = argv[-1]
            with (root / "etc/passwd").open("a") as f:
                f.write(f"{username}:x:{uid}:{gid}::/home/{username}:/bin/bash\n")
            with (root / "etc/shadow").open("a") as f:
                f.write(f"{username}:!:19700:0:99999:7:::\n")
            return subprocess.CompletedProcess(argv, 0)
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
            # lgtm[py/clear-text-storage-sensitive-data]
            # Stands in for the real root-escalated `tee` writing
            # /etc/shadow, whose job is storing password hashes in a plain
            # (permission-locked, not encrypted) file — real Unix shadow
            # file semantics, not a credential-handling bug. The hash here
            # ("$6$fakehash" etc.) is a synthetic test fixture.
            path.write_text(kwargs.get("input", ""))
            return subprocess.CompletedProcess(argv, 0)
        if argv[0] == "chmod":
            pathlib.Path(argv[2]).chmod(int(argv[1], 8))
            return subprocess.CompletedProcess(argv, 0)
        if argv[0] == "chown":
            return subprocess.CompletedProcess(argv, 0)
        if argv[0] == "cp":
            import shutil as _shutil
            _shutil.copytree(argv[2], argv[3], dirs_exist_ok=True)
            return subprocess.CompletedProcess(argv, 0)
        if argv[0] == "restorecon":
            return subprocess.CompletedProcess(argv, 0)
        raise AssertionError(f"unexpected command: {argv}")

    return fake_run, calls


class CreateInstallerUserTests(unittest.TestCase):
    def test_creates_user_sets_password_hash_and_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root / "etc/passwd", "root:x:0:0:root:/root:/bin/bash\n")
            _write(root / "etc/shadow", "root:!locked:19700:0:99999:7:::\n")

            fake_run, calls = _fake_useradd_run("1000:1000")
            accounts.create_installer_user(
                str(root), str(root), "alice", "$6$fakehash", lambda _msg: None, run=fake_run,
            )

            passwd = (root / "etc/passwd").read_text()
            shadow = (root / "etc/shadow").read_text()
            self.assertIn("alice:x:1000:1000:", passwd)
            self.assertIn("alice:$6$fakehash:", shadow)
            self.assertEqual(shadow.count("root:!locked"), 1)

            var_home = root / "ostree/deploy/default/var/home/alice"
            self.assertTrue(var_home.is_dir())
            self.assertEqual(var_home.stat().st_mode & 0o777, 0o700)

            useradd_calls = [c for c in calls if c[0] == "useradd"]
            self.assertEqual(useradd_calls[0][2], str(root))
            self.assertIn("wheel,video,audio,render", useradd_calls[0])

    def test_copies_skel_into_new_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root / "etc/passwd", "root:x:0:0:root:/root:/bin/bash\n")
            _write(root / "etc/shadow", "root:!locked:19700:0:99999:7:::\n")
            _write(root / "etc/skel/.bashrc", "# skel bashrc\n")

            fake_run, _ = _fake_useradd_run("1000:1000")
            accounts.create_installer_user(
                str(root), str(root), "bob", "$6$hash", lambda _msg: None, run=fake_run,
            )

            copied = root / "ostree/deploy/default/var/home/bob/.bashrc"
            self.assertTrue(copied.is_file())
            self.assertEqual(copied.read_text(), "# skel bashrc\n")

    def test_raises_if_user_missing_from_shadow_after_useradd(self):
        # Simulates a broken/mocked useradd that didn't actually add a shadow
        # entry — must fail loudly rather than silently leave no password set.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write(root / "etc/passwd", "root:x:0:0:root:/root:/bin/bash\n")
            _write(root / "etc/shadow", "root:!locked:19700:0:99999:7:::\n")

            def fake_run(argv, **kwargs):
                if argv[0] == "useradd":
                    return subprocess.CompletedProcess(argv, 0)
                if argv[0] == "cat":
                    path = pathlib.Path(argv[1])
                    return subprocess.CompletedProcess(
                        argv, 0, stdout=path.read_text() if path.exists() else "", stderr="",
                    )
                return subprocess.CompletedProcess(argv, 0)

            with self.assertRaises(RuntimeError):
                accounts.create_installer_user(
                    str(root), str(root), "carol", "$6$hash", lambda _msg: None, run=fake_run,
                )

    def test_cli_dispatches_create_user_with_parsed_arguments(self):
        # useradd --root needs real root, so this checks main()'s own
        # argument parsing/dispatch rather than re-testing create_installer_user.
        with mock.patch.object(accounts, "create_installer_user") as mocked:
            rc = accounts.main(["create-user", "/deploy", "/target", "dave", "$6$h"])
        self.assertEqual(rc, 0)
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[:4], ("/deploy", "/target", "dave", "$6$h"))
        self.assertIs(kwargs["run"], accounts._default_run)


if __name__ == "__main__":
    unittest.main()
