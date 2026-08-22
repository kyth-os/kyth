"""Security contracts for privileged KythOS system services."""
from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PRIVILEGED_UNITS = (
    "kyth-update-watcher.service",
    "kyth-proton-cachyos-update.service",
    "kyth-hw-setup.service",
    "kyth-probe.service",
    "kyth-batteryd.service",
    "kyth-enroll-mok.service",
    "kyth-storage-maint.service",
)


# Units whose own code path shells out to `sudo` (directly, or transitively
# via kyth_shared.system.bootc_query's `sudo -n kyth-bootc-guard ...`) to
# reach real root. PrivateUsers=yes remaps root to an unprivileged UID
# outside the unit's private namespace, and NoNewPrivileges=yes blocks the
# kernel from ever honoring sudo's setuid bit at exec for a non-root caller —
# either one alone reproduces "unable to open /etc/sudoers: Invalid
# argument" on every invocation. Root-context units (already euid 0, so sudo
# never needs to *gain* privilege) only break via the PrivateUsers identity
# remap; per-user units escalating from a real unprivileged UID break via
# either directive, so both must be absent for those.
SUDO_ESCALATING_ROOT_UNITS = (
    "kyth-hw-setup.service",
    "kyth-probe.service",
)
SUDO_ESCALATING_USER_UNITS = (
    "kyth-guardian.service",
    "kyth-sched.service",
    "kyth-probe-user.service",
)


class SudoEscalationHardeningTests(unittest.TestCase):
    def test_root_context_sudo_units_have_no_private_user_namespace(self) -> None:
        for unit_name in SUDO_ESCALATING_ROOT_UNITS:
            body = (ROOT / "build_files" / unit_name).read_text(encoding="utf-8")
            with self.subTest(unit=unit_name):
                self.assertNotIn("PrivateUsers=yes", body)

    def test_user_context_sudo_units_allow_privilege_escalation(self) -> None:
        for unit_name in SUDO_ESCALATING_USER_UNITS:
            body = (ROOT / "build_files" / unit_name).read_text(encoding="utf-8")
            with self.subTest(unit=unit_name):
                self.assertNotIn("PrivateUsers=yes", body)
                self.assertNotIn("NoNewPrivileges=yes", body)


class SystemServiceHardeningTests(unittest.TestCase):
    def test_privileged_units_have_safe_process_baseline(self) -> None:
        required = (
            "UMask=0077",
            "NoNewPrivileges=yes",
            "PrivateTmp=yes",
            "ProtectClock=yes",
            "LockPersonality=yes",
            "RestrictRealtime=yes",
            "RestrictSUIDSGID=yes",
        )
        for unit_name in PRIVILEGED_UNITS:
            body = (ROOT / "build_files" / unit_name).read_text(encoding="utf-8")
            for directive in required:
                with self.subTest(unit=unit_name, directive=directive):
                    self.assertIn(directive, body)

    def test_guardian_user_unit_can_persist_state(self) -> None:
        body = (ROOT / "build_files/kyth-guardian.service").read_text(encoding="utf-8")
        self.assertIn("StateDirectory=kyth", body)
        self.assertIn("ProtectSystem=strict", body)
        self.assertIn("ReadWritePaths=-%h/.local/share/flatpak", body)
        proton = (ROOT / "build_files/kyth-proton-cachyos-update.service").read_text()
        probe = (ROOT / "build_files/kyth-probe.service").read_text()
        self.assertIn("ProtectSystem=strict", proton)
        self.assertIn("StateDirectory=kyth/proton-cachyos", proton)
        self.assertIn("CapabilityBoundingSet=\n", proton)
        self.assertIn("ProtectSystem=strict", probe)
        self.assertIn("CacheDirectory=kyth", probe)

    def test_device_writing_services_declare_narrow_writable_paths(self) -> None:
        battery = (ROOT / "build_files/kyth-batteryd.service").read_text()
        mok = (ROOT / "build_files/kyth-enroll-mok.service").read_text()
        hw = (ROOT / "build_files/kyth-hw-setup.service").read_text()
        self.assertIn("ReadWritePaths=/sys/class/power_supply", battery)
        self.assertIn("ReadWritePaths=/sys/firmware/efi/efivars", mok)
        # ProtectSystem=strict without these is EROFS on /etc/modprobe.d at boot.
        self.assertIn("StateDirectory=kyth", hw)
        self.assertIn("ReadWritePaths=/etc/modprobe.d", hw)
        self.assertIn("/etc/scx", hw)
        self.assertIn("/var/lib/akmods", hw)


# Units with no resource-limit directives at all before this — a bug/leak in
# any of them could compete with the interactive desktop session for cycles
# unbounded, the same class of problem that made pre-push validation freeze
# the desktop earlier (see .githooks/pre-push). kyth-guardian.service already
# had this; these bring the rest of the always-on/boot-time units in line.
LONG_RUNNING_DAEMON_UNITS = (
    "kyth-ai-perfd.service",
    "kyth-batteryd.service",
    "kyth-dynamic-lock.service",
    "kyth-sched.service",
    "kyth-telem.service",
)
ONESHOT_TASK_UNITS = (
    "kyth-browser-wallet-defaults.service",
    "kyth-enroll-mok.service",
    "kyth-flathub-setup.service",
    "kyth-local-bin-migrate.service",
    "kyth-mok-rotate.service",
    "kyth-power-arbiter.service",
    "kyth-sched-arbiter.service",
)


class ResourceLimitHardeningTests(unittest.TestCase):
    def test_long_running_daemons_are_deprioritized_and_memory_bounded(self) -> None:
        required = ("Nice=", "IOSchedulingClass=idle", "CPUQuota=", "MemoryHigh=", "MemoryMax=")
        for unit_name in LONG_RUNNING_DAEMON_UNITS:
            body = (ROOT / "build_files" / unit_name).read_text(encoding="utf-8")
            for directive in required:
                with self.subTest(unit=unit_name, directive=directive):
                    self.assertIn(directive, body)

    def test_oneshot_tasks_are_deprioritized_and_memory_bounded(self) -> None:
        required = ("Nice=", "IOSchedulingClass=idle", "MemoryMax=")
        for unit_name in ONESHOT_TASK_UNITS:
            body = (ROOT / "build_files" / unit_name).read_text(encoding="utf-8")
            for directive in required:
                with self.subTest(unit=unit_name, directive=directive):
                    self.assertIn(directive, body)

    def test_browser_wallet_skips_immutable_root_home(self) -> None:
        body = (ROOT / "build_files/kyth-browser-wallet-defaults.service").read_text()
        self.assertIn("ConditionUser=!root", body)
        self.assertIn("StateDirectory=kyth", body)
        self.assertIn("ExecStartPost=/usr/bin/touch %S/kyth/browser-wallet-defaults-v2", body)
        self.assertNotIn("mkdir -p", body)

    def test_scx_loader_gets_a_memory_ceiling_but_not_cpu_throttling(self) -> None:
        # It loads/manages the sched_ext scheduler itself — deliberately not
        # deprioritized like a monitor daemon would be, but still bounded
        # against a leak.
        body = (ROOT / "build_files/kyth-scx-loader.service").read_text(encoding="utf-8")
        self.assertIn("MemoryHigh=", body)
        self.assertIn("MemoryMax=", body)
        self.assertNotIn("CPUQuota=", body)
        self.assertNotIn("Nice=", body)


if __name__ == "__main__":
    unittest.main()
