import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/runtime"
sys.path.insert(0, str(ROOT / "build_files/kyth_shared"))

from kyth_shared.runtime_output import (
    count_fwupd_updates,
    parse_findmnt_sources,
    parse_flatpak_apps,
    parse_json_object,
    parse_lsblk_devices,
    parse_ntfs_devices,
    parse_nvidia_smi,
    parse_secure_boot_state,
    parse_systemd_state,
)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class RuntimeFixtureTests(unittest.TestCase):
    def test_bootc_status_and_malformed_json(self):
        status = parse_json_object(fixture("bootc-status.json"))
        self.assertEqual(
            status["status"]["booted"]["image"]["reference"],
            "ghcr.io/mrtrick37/kyth:testing",
        )
        self.assertIsNone(parse_json_object("{changed output"))

    def test_lsblk_and_findmnt(self):
        self.assertEqual(len(parse_lsblk_devices(fixture("lsblk.json"))), 1)
        ntfs = parse_ntfs_devices(fixture("lsblk.json"))
        self.assertEqual([device["name"] for device in ntfs], ["nvme0n1p4"])
        self.assertEqual(parse_findmnt_sources(fixture("findmnt.txt"))[0], "/dev/nvme0n1p3")

    def test_flatpak_and_fwupd(self):
        apps = parse_flatpak_apps(fixture("flatpak-list.tsv"))
        self.assertEqual([app["app_id"] for app in apps], [
            "org.mozilla.firefox",
            "com.valvesoftware.Steam",
        ])
        self.assertEqual(count_fwupd_updates(fixture("fwupd-updates.txt")), 2)
        self.assertEqual(count_fwupd_updates("No updates available"), 0)

    def test_secure_boot_systemd_and_nvidia(self):
        self.assertEqual(parse_secure_boot_state(fixture("secure-boot.txt")), "enabled")
        self.assertEqual(parse_secure_boot_state("unexpected wording"), "unknown")
        self.assertEqual(parse_systemd_state(fixture("systemd-active.txt")), "active")
        self.assertEqual(parse_systemd_state("maintenance"), "unknown")
        self.assertEqual(
            parse_nvidia_smi(fixture("nvidia-smi.csv")),
            ("NVIDIA GeForce RTX 4070", "590.48.01"),
        )


if __name__ == "__main__":
    unittest.main()
