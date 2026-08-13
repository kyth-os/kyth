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

    def test_network_installer_and_read_only_probe_use_strict_filesystems(self) -> None:
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
        self.assertIn("ReadWritePaths=/sys/class/power_supply", battery)
        self.assertIn("ReadWritePaths=/sys/firmware/efi/efivars", mok)


if __name__ == "__main__":
    unittest.main()
