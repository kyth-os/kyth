"""Regression guards for the System Hub privilege boundary."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import network_share_helper as shares  # noqa: E402
from kyth_welcome.services.privileged import (  # noqa: E402
    AuthFrontend,
    PrivilegedActionError,
    bootc_action,
    helper_action,
    openconnect_action,
    scheduler_action,
    systemctl_action,
)


class PrivilegedActionTests(unittest.TestCase):
    def test_bootc_policy_rejects_shell_data(self):
        self.assertEqual(
            bootc_action("switch", "ghcr.io/example/kyth:testing").command(),
            ["sudo", "-A", "bootc", "switch", "ghcr.io/example/kyth:testing"],
        )
        with self.assertRaises(PrivilegedActionError):
            bootc_action("switch", "image; reboot")
        with self.assertRaises(PrivilegedActionError):
            bootc_action("install")

    def test_systemctl_policy_is_allowlisted(self):
        action = systemctl_action(
            "enable", "kyth-update-watcher.timer", now=True,
            frontend=AuthFrontend.PKEXEC,
        )
        self.assertEqual(action.command()[0], "pkexec")
        self.assertEqual(action.command()[-3:], ["enable", "--now", "kyth-update-watcher.timer"])
        with self.assertRaises(PrivilegedActionError):
            systemctl_action("restart", "sshd.service")
        with self.assertRaises(PrivilegedActionError):
            systemctl_action("start", "bad;unit.mount")

    def test_fixed_helpers_validate_arguments(self):
        self.assertEqual(helper_action("sleep-mode", "deep").command()[-2:], [
            "/usr/libexec/kyth-set-sleep-mode", "deep",
        ])
        with self.assertRaises(PrivilegedActionError):
            helper_action("sleep-mode", "s2idle")
        with self.assertRaises(PrivilegedActionError):
            helper_action("network-share", "add; reboot")

    def test_vpn_and_scheduler_reject_control_data(self):
        action = openconnect_action(
            gateway="https://[2001:db8::1]/vpn",
            protocol="anyconnect",
            os_emulation="linux",
            username="user",
            password_stdin=True,
        )
        self.assertIn("--passwd-on-stdin", action.command())
        with self.assertRaises(PrivilegedActionError):
            openconnect_action(
                gateway="vpn.example; reboot", protocol="gp", os_emulation="linux"
            )
        with self.assertRaises(PrivilegedActionError):
            scheduler_action("scx_rusty; reboot")


class NetworkShareHelperTests(unittest.TestCase):
    def test_add_share_keeps_secret_out_of_process_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            mount = root / "mounts" / "games"
            calls = []

            def fake_run(argv, **kwargs):
                calls.append(list(argv))
                return type("Result", (), {"stdout": "mnt-games.mount\n"})()

            payload = {
                "name": "games",
                "server": "nas.example",
                "share_path": "Games",
                "username": "player",
                "password": "not-on-the-command-line",
                "domain": "",
                "mount_point": str(mount),
                "auto_mount": True,
                "mount_now": True,
                "uid": 1000,
                "gid": 1000,
            }
            with (
                patch.object(shares, "CREDS_DIR", root / "creds"),
                patch.object(shares, "UNIT_DIR", root / "units"),
                patch.object(shares, "_SAFE_MOUNT_PREFIXES", (str(root) + "/",)),
                patch.object(shares.subprocess, "run", side_effect=fake_run),
            ):
                shares.add_share(payload)

            credential = root / "creds" / "games"
            self.assertEqual(credential.stat().st_mode & 0o777, 0o600)
            self.assertIn("not-on-the-command-line", credential.read_text(encoding="utf-8"))
            self.assertNotIn("not-on-the-command-line", repr(calls))

    def test_control_characters_and_symlink_mounts_are_rejected(self):
        with self.assertRaises(ValueError):
            shares._plain("bad\tvalue", "password")
        with self.assertRaises(ValueError):
            shares._mount_point("/mnt/%n")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                shares._ensure_mount_path_safe(str(link / "share"))


class NetworkSharesPageMountValidationTests(unittest.TestCase):
    """page_network_shares.py can't be imported in this sandbox (no PySide6),
    so this checks source directly for the property that matters: form
    validation must call the same _mount_point the root helper enforces, not
    re-derive its own copy of the safe-prefix list, which is what let the two
    drift before (the page only checked prefixes; the helper also rejected
    unsafe characters, so bad input could pass the page's check and only fail
    late, inside the root-escalated helper, with a worse error message).

    That validation now lives in services/network.py's validate_share_form
    (the page just calls it), so the import/call assertions check that
    module; the page itself is only checked for not reintroducing a local
    copy of the prefix list."""

    def test_validator_uses_shared_mount_point_check(self):
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "build_files" / "kyth-welcome" / "kyth_welcome" / "services" / "network.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from .network_share_helper import _mount_point", source)
        self.assertIn("_mount_point(mount_pt)", source)
        self.assertNotIn("_SAFE_MOUNT_PREFIXES", source)

    def test_page_does_not_reintroduce_local_mount_validation(self):
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "build_files" / "kyth-welcome" / "kyth_welcome" / "page_network_shares.py"
        ).read_text(encoding="utf-8")
        self.assertIn("validate_share_form", source)
        self.assertNotIn("_SAFE_MOUNT_PREFIXES", source)
        self.assertNotIn("_mount_point", source)


if __name__ == "__main__":
    unittest.main()
