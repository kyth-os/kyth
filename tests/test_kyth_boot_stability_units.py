"""Contracts for boot-path timeouts, MOK retry, and /boot mutator caps."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
SELINUX_UNIT = (
    ROOT / "build_files/scripts/sysconfig/systemd"
    / "32-selinux-relabel-var-home-after-each-new-deployment.sh"
)
BOOT_SPLASH = ROOT / "build_files/scripts/branding/28-bootc-kernel-arguments-and-boot-splash.sh"
ENROLL_SCRIPT = ROOT / "build_files/tests/secureboot-enrollment.sh"


class BootStabilityUnitTests(unittest.TestCase):
    def test_selinux_home_relabel_is_capped_and_still_before_greeter(self) -> None:
        body = SELINUX_UNIT.read_text(encoding="utf-8")
        self.assertIn("Before=plasmalogin.service", body)
        self.assertIn("TimeoutStartSec=180", body)

    def test_boot_mutators_have_timeouts_and_path_trigger_limit(self) -> None:
        body = BOOT_SPLASH.read_text(encoding="utf-8")
        self.assertIn("kyth-boot-splash-kargs.service", body)
        self.assertIn("kyth-boot-branding.service", body)
        self.assertIn("kyth-boot-splash-initramfs.service", body)
        self.assertGreaterEqual(body.count("TimeoutStartSec=60"), 2)
        self.assertIn("TimeoutStartSec=300", body)
        self.assertIn("TriggerLimitIntervalSec=10", body)
        self.assertIn("TriggerLimitBurst=5", body)

    def test_secureboot_enrollment_does_not_stamp_flag_on_import_failure(self) -> None:
        result = subprocess.run(
            ["bash", str(ENROLL_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("secureboot enrollment tests passed", result.stdout)

    def test_sched_and_telem_install_as_user_units(self) -> None:
        body = (ROOT / "build_files/scripts/branding/27-performance-daemons.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("/usr/lib/systemd/user/kyth-sched.service", body)
        self.assertIn("/usr/lib/systemd/user/kyth-telem.service", body)
        self.assertNotIn("/usr/lib/systemd/system/kyth-sched.service", body)
        self.assertNotIn("/usr/lib/systemd/system/kyth-telem.service", body)

    def test_restart_limited_units_cap_start_burst(self) -> None:
        units = (
            ROOT / "build_files/kyth-batteryd.service",
            ROOT / "build_files/rclone@.service",
            ROOT / "build_files/kyth-telem.service",
            ROOT / "build_files/kyth-sched-arbiter.service",
        )
        for path in units:
            body = path.read_text(encoding="utf-8")
            with self.subTest(unit=path.name):
                self.assertIn("StartLimitIntervalSec=60", body)
                self.assertIn("StartLimitBurst=3", body)
                self.assertIn("RestartSec=", body)
        zram = (ROOT / "build_files/scripts/branding/51-zram.sh").read_text(encoding="utf-8")
        self.assertIn("StartLimitIntervalSec=60", zram)
        self.assertIn("StartLimitBurst=3", zram)


class InstallerMokFailClosedTests(unittest.TestCase):
    def test_failed_mok_staging_blocks_install_success(self) -> None:
        from kyth_installer.phases.run import _require_secure_boot_ready

        with self.assertRaisesRegex(RuntimeError, "could not stage MOK"):
            _require_secure_boot_ready("failed")

    def test_successful_mok_states_do_not_block_install(self) -> None:
        from kyth_installer.phases.run import _require_secure_boot_ready

        for state in ("skipped", "enrolled", "pending", "staged", {}):
            with self.subTest(state=state):
                _require_secure_boot_ready(state)


if __name__ == "__main__":
    unittest.main()
