"""Contracts for boot-path timeouts, MOK retry, and /boot mutator caps."""
from __future__ import annotations

import pathlib
import re
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

    def test_zram_setup_does_not_wait_for_udev_device(self) -> None:
        """After switch-root, udevd is down until sysinit; sysinit After=swap.
        Requiring dev-zram0.device plus After=udevd is a 30s deadlock.
        """
        zram = (ROOT / "build_files/scripts/branding/51-zram.sh").read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/libexec/kyth-zram-ensure", zram)
        self.assertIn("mknod -m 0600 /dev/zram0", zram)
        self.assertIn("After=systemd-modules-load.service", zram)
        self.assertIn("Before=systemd-zram-setup@zram0.service swap.target", zram)
        self.assertNotIn("After=systemd-udevd.service", zram)
        self.assertIn("Requires=", zram)
        self.assertIn("BindsTo=", zram)
        self.assertIn("dev-zram0.swap.d/10-kyth-async.conf", zram)

    def test_memory_tune_applies_only_its_own_sysctl_file(self) -> None:
        body = (ROOT / "build_files/scripts/sysconfig/kernel/56-memory-tune.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("sysctl --load=/etc/sysctl.d/99-kyth-memory.conf", body)
        self.assertIn("ExecStartPost=-/usr/bin/sysctl --load=/etc/sysctl.d/99-kyth-memory.conf", body)
        self.assertNotIn("ExecStartPost=/usr/bin/sysctl --system", body)
        self.assertNotIn("sudo sysctl --system", body)
        self.assertIn("After=local-fs.target systemd-sysctl.service", body)
        self.assertNotRegex(body, r"^After=multi-user\.target$", re.M)

    def test_irqbalance_oneshot_does_not_fail_type_simple(self) -> None:
        body = (ROOT / "build_files/scripts/sysconfig/systemd/05-irqbalance-tuning.sh").read_text(
            encoding="utf-8"
        )
        late = (ROOT / "build_files/scripts/sysconfig/kernel/48-irqbalance-tuning.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("IRQBALANCE_ONESHOT=yes", body)
        self.assertIn("irqbalance.service.d/10-kyth-oneshot.conf", body)
        self.assertIn("Type=oneshot", body)
        self.assertIn("RemainAfterExit=yes", body)
        self.assertIn("--deepestcache=2", body)
        self.assertNotIn("write_config /etc/sysconfig/irqbalance", late)

    def test_dbus_runtime_dir_stays_active_after_mkdir(self) -> None:
        body = (
            ROOT / "build_files/scripts/sysconfig/desktop/09-autostart-log-noise-guards.sh"
        ).read_text(encoding="utf-8")
        dbus_unit = body.split("kyth-dbus-runtime-dir.service", 1)[1]
        self.assertIn("RemainAfterExit=yes", dbus_unit.split("DBUSRUNDIREOF", 1)[0])


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
