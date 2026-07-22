"""Sysconfig domain fragments (demonolith build layout)."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "build_files" / "scripts"
FRAG_DIR = SCRIPTS / "sysconfig"
RUNNER = SCRIPTS / "sysconfig-static.sh"
SYSCTL_DATA = ROOT / "build_files" / "data" / "sysctl.d" / "99-kyth.conf"
BRANDING_FRAG_DIR = SCRIPTS / "branding"


class SysconfigFragmentTests(unittest.TestCase):
    def test_runner_exists_and_is_thin(self):
        self.assertTrue(RUNNER.is_file())
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("sysconfig", text)
        self.assertLess(len(text.splitlines()), 50)
        # Must not still embed the old monolith herdocs.
        self.assertNotIn("99-kyth.conf", text)

    def test_fragments_present_and_named(self):
        frags = sorted(FRAG_DIR.glob("*.sh"))
        self.assertGreaterEqual(len(frags), 20)
        for frag in frags:
            self.assertRegex(frag.name, r"^\d{2}-.+\.sh$")
            body = frag.read_text(encoding="utf-8")
            self.assertTrue(body.startswith("#!/bin/bash") or body.lstrip().startswith("#"))
            self.assertIn("set -euo pipefail", body)

    def test_kernel_sysctl_fragment(self):
        # The fragment copies the sysctl values from a data file (build_files/data/)
        # instead of embedding them in a heredoc — same pattern as every other
        # extracted config in this refactor. The values themselves are checked
        # against that data file, not the fragment script.
        path = FRAG_DIR / "01-kernel-sysctl-parameters.sh"
        self.assertTrue(path.is_file())
        body = path.read_text(encoding="utf-8")
        self.assertIn("99-kyth.conf", body)
        self.assertTrue(SYSCTL_DATA.is_file())
        self.assertIn("vm.swappiness", SYSCTL_DATA.read_text(encoding="utf-8"))

    def test_boot_log_regression_guards(self):
        guards = (FRAG_DIR / "09-autostart-log-noise-guards.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("groupadd --system plugdev", guards)
        self.assertIn("Before=dbus.socket", guards)
        self.assertIn("systemd-udevd.service", guards)
        self.assertIn("/etc/udev/rules.d/99-input-remapper.rules", guards)
        self.assertIn('TEST=="charge_control_start_threshold"', guards)
        self.assertNotIn('TEST{0002}!="/sys%p/charge_', guards)

    def test_openrgb_is_not_unconditionally_autostarted(self):
        body = (FRAG_DIR / "39-openrgb-rgb-peripheral-control.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("rm -f /etc/skel/.config/autostart/openrgb.desktop", body)
        self.assertNotIn("Exec=openrgb", body)

    def test_initramfs_includes_account_databases(self):
        setup = (SCRIPTS / "plymouth-setup.sh").read_text(encoding="utf-8")
        final = (SCRIPTS / "plymouth-initramfs.sh").read_text(encoding="utf-8")
        self.assertIn('install_items+=" /etc/passwd /etc/group "', setup)
        self.assertIn("etc/passwd etc/group", final)

    def test_late_plasma_splash_is_kyth_owned(self):
        fragment = (BRANDING_FRAG_DIR / "12-kyth-session-splash.sh").read_text(
            encoding="utf-8"
        )
        qml = (
            ROOT
            / "build_files"
            / "branding"
            / "plasma-splash"
            / "contents"
            / "splash"
            / "Splash.qml"
        ).read_text(encoding="utf-8")
        polish = (ROOT / "build_files" / "kyth-user-polish").read_text(
            encoding="utf-8"
        )
        self.assertIn("Theme=org.kythos.desktop", fragment)
        self.assertIn('source: "images/kyth-logo.svg"', qml)
        self.assertNotIn("fedora", qml.lower())
        self.assertIn("--key Theme org.kythos.desktop", polish)

    def test_antigravity_uses_desktop_safe_wrapper(self):
        body = (SCRIPTS / "packages" / "20-google-antigravity-ide.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("/usr/bin/antigravity", body)
        self.assertIn("kyth-ai-dev", body)

    def test_bootc_sudoers_allows_status_without_arguments(self):
        body = (ROOT / "build_files" / "kyth-bootc-sudo").read_text(
            encoding="utf-8"
        )
        self.assertIn("/usr/bin/bootc status,", body)
        self.assertIn("/usr/sbin/bootc status,", body)

    def test_firstboot_missing_apps_is_a_successful_status(self):
        body = (ROOT / "build_files" / "kyth-firstboot-app-status").read_text(
            encoding="utf-8"
        )
        self.assertTrue(body.rstrip().endswith("exit 0"))


if __name__ == "__main__":
    unittest.main()
