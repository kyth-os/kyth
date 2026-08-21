import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.assurance import (  # noqa: E402
    AssuranceCheck,
    _battery_check,
    _encryption_check,
    run_preflight,
    validate_installed_target,
)
from kyth_installer.context import InstallRequest  # noqa: E402
from kyth_installer.imagesrc import ImageSource  # noqa: E402
import kyth_installer.disk  # noqa: E402, F401  # pylint: disable=unused-import
import kyth_installer.runner  # noqa: E402, F401  # pylint: disable=unused-import
import kyth_installer.system  # noqa: E402, F401  # pylint: disable=unused-import


class InstallerAssuranceCoverageTests(unittest.TestCase):
    def test_check_serializes_for_status_reporting(self):
        check = AssuranceCheck("image", "pass", "verified")
        self.assertEqual(check.as_dict(), {"name": "image", "status": "pass", "detail": "verified"})

    def test_battery_scan_ignores_invalid_entries_and_uses_lowest_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "AC"
            invalid.mkdir()
            (invalid / "type").write_text("Mains\n")
            malformed = root / "BAT-bad"
            malformed.mkdir()
            (malformed / "type").write_text("Battery\n")
            (malformed / "capacity").write_text("unknown\n")
            for name, capacity in (("BAT0", 90), ("BAT1", 35)):
                battery = root / name
                battery.mkdir()
                (battery / "type").write_text("Battery\n")
                (battery / "capacity").write_text(f"{capacity}\n")
                (battery / "status").write_text("Charging\n")
            check = _battery_check(root)
        self.assertEqual(check.detail, "Battery is 35% (charging)")

    def test_empty_battery_directory_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_battery_check(Path(tmp)).status, "pass")

    def test_snapshot_detects_direct_and_child_luks(self):
        direct = SimpleNamespace(partitions_by_name={"/dev/sda1": {"fstype": "crypto_LUKS"}})
        child = SimpleNamespace(partitions_by_name={"/dev/sda2": {"children": [{"fstype": "crypto_luks"}]}})
        self.assertIn("LUKS-encrypted", _encryption_check(snapshot=direct).detail)
        self.assertIn("LUKS-encrypted", _encryption_check(snapshot=child).detail)

    def test_snapshot_detects_in_use_ntfs_and_tolerates_bad_snapshot(self):
        snapshot = SimpleNamespace(partitions_by_name={"p1": {"name": "/dev/sda1", "fstype": "ntfs3", "in_use": True}})
        self.assertIn("BitLocker-locked", _encryption_check(snapshot=snapshot).detail)
        bad = SimpleNamespace(partitions_by_name=Mock())
        bad.partitions_by_name.items.side_effect = RuntimeError("probe failed")
        self.assertIsNone(_encryption_check(snapshot=bad))

    @patch("kyth_installer.disk.list_partitions")
    def test_disk_scan_detects_luks(self, list_partitions):
        list_partitions.return_value = [{"name": "/dev/sda2", "fstype": "crypto_luks"}]
        self.assertIn("LUKS-encrypted", _encryption_check("/dev/sda").detail)

    @patch("kyth_installer.system._as_root", side_effect=lambda argv: argv)
    @patch("kyth_installer.runner.run_command")
    @patch("kyth_installer.disk.list_partitions")
    def test_disk_scan_confirms_bitlocker(self, list_partitions, run_command, _as_root):
        list_partitions.return_value = [{"name": "/dev/sda3", "fstype": "ntfs", "in_use": True}]
        run_command.return_value = SimpleNamespace(stdout="BitLocker\n")
        check = _encryption_check("/dev/sda")
        self.assertIn("manage-bde -off", check.detail)
        run_command.assert_called_once()

    @patch("kyth_installer.disk.list_partitions", side_effect=OSError("probe failed"))
    def test_disk_probe_failure_is_nonfatal(self, _list_partitions):
        self.assertIsNone(_encryption_check("/dev/sda"))

    @patch("kyth_installer.disk.list_partitions")
    def test_preflight_surfaces_encryption_warning_when_a_disk_is_given(self, list_partitions):
        # run_preflight() previously always called _encryption_check(None),
        # so its own disk/LUKS/BitLocker scan branch (covered above via
        # direct _encryption_check() calls) was unreachable through the
        # preflight path — the comment claimed "infer disk from source
        # target" but nothing ever did. Now the caller's target disk is
        # threaded through.
        list_partitions.return_value = [{"name": "/dev/sda2", "fstype": "crypto_luks"}]
        source = ImageSource("oci:/local", "target", "local")
        with tempfile.TemporaryDirectory() as tmp:
            checks = run_preflight(source, power_root=Path(tmp) / "missing", disk="/dev/sda")
        encryption_checks = [c for c in checks if c.name == "encryption"]
        self.assertEqual(len(encryption_checks), 1)
        self.assertIn("LUKS-encrypted", encryption_checks[0].detail)

    def test_preflight_without_a_disk_omits_encryption_check(self):
        # No target selected yet (e.g. before a guided flow's first disk
        # pick) — must stay a clean no-op, not raise or probe anything.
        source = ImageSource("oci:/local", "target", "local")
        with tempfile.TemporaryDirectory() as tmp:
            checks = run_preflight(source, power_root=Path(tmp) / "missing")
        self.assertFalse([c for c in checks if c.name == "encryption"])

    def test_preflight_rejects_unverified_embedded_source(self):
        source = ImageSource("oci:/image", "target", "embedded")
        with self.assertRaisesRegex(RuntimeError, "could not be verified"):
            run_preflight(source)

    def test_preflight_describes_network_and_local_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            network = run_preflight(ImageSource("docker://registry/image", "target", "registry"), power_root=missing)
            local = run_preflight(ImageSource("oci:/local", "target", "local"), power_root=missing)
        self.assertIn("Registry", network[0].detail)
        self.assertIn("Local", local[0].detail)

    @patch("kyth_installer.assurance._encryption_check")
    def test_preflight_appends_encryption_warning(self, encryption_check):
        encryption_check.return_value = AssuranceCheck("encryption", "warn", "locked")
        source = ImageSource("oci:/local", "target", "local")
        with tempfile.TemporaryDirectory() as tmp:
            checks = run_preflight(source, power_root=Path(tmp) / "missing")
        self.assertEqual(checks[-1].name, "encryption")

    def test_installed_target_requires_etc_hostname_and_fstab(self):
        request = InstallRequest(hostname="kyth")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "no writable /etc"):
                validate_installed_target(root / "missing", request)
            with self.assertRaisesRegex(RuntimeError, "Could not verify installed hostname"):
                validate_installed_target(root, request)
            (root / "hostname").write_text("other\n")
            with self.assertRaisesRegex(RuntimeError, "expected 'kyth'"):
                validate_installed_target(root, request)
            (root / "hostname").write_text("kyth\n")
            with self.assertRaisesRegex(RuntimeError, "missing /etc/fstab"):
                validate_installed_target(root, request)

    def test_installed_target_reports_unreadable_passwd_and_allows_empty_username(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hostname").write_text("kyth\n")
            (root / "fstab").write_text("# generated\n")
            with self.assertRaisesRegex(RuntimeError, "Could not verify installed account"):
                validate_installed_target(root, InstallRequest(hostname="kyth", username="alice"))
            checks = validate_installed_target(root, InstallRequest(hostname="kyth", username=""))
        self.assertEqual([check.name for check in checks], ["hostname", "filesystem"])

    def test_installed_target_requires_bootloader_when_root_is_given(self):
        request = InstallRequest(hostname="kyth", username="")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etc").mkdir()
            # validate uses `etc` as the /etc tree, not root/etc
            etc = root / "etc"
            (etc / "hostname").write_text("kyth\n")
            (etc / "fstab").write_text("# generated\n")
            with self.assertRaisesRegex(RuntimeError, "no bootloader"):
                validate_installed_target(etc, request, root=root)
            deploy = root / "ostree" / "deploy" / "default"
            deploy.mkdir(parents=True)
            checks = validate_installed_target(etc, request, root=root)
        self.assertEqual(checks[-1].name, "bootloader")


if __name__ == "__main__":
    unittest.main()
