import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.assurance import run_preflight, validate_installed_target  # noqa: E402
from kyth_installer.context import InstallRequest  # noqa: E402
from kyth_installer.imagesrc import ImageSource  # noqa: E402


class InstallerAssuranceTests(unittest.TestCase):
    def test_verified_embedded_source_passes_without_network(self):
        source = ImageSource("oci:/image:latest", "example/image:latest", "embedded", "sha256:" + "a" * 64, True)
        with tempfile.TemporaryDirectory() as tmp:
            checks = run_preflight(source, power_root=Path(tmp) / "missing")
        self.assertEqual([check.name for check in checks], ["image", "power"])

    def test_low_discharging_battery_blocks_destructive_work(self):
        source = ImageSource("oci:/image:latest", "example/image:latest", "embedded", "sha256:" + "a" * 64, True)
        with tempfile.TemporaryDirectory() as tmp:
            battery = Path(tmp) / "BAT0"
            battery.mkdir()
            (battery / "type").write_text("Battery\n")
            (battery / "capacity").write_text("9\n")
            (battery / "status").write_text("Discharging\n")
            with self.assertRaisesRegex(RuntimeError, "Connect power"):
                run_preflight(source, power_root=Path(tmp))

    def test_installed_target_identity_and_account_are_verified(self):
        request = InstallRequest(hostname="kyth-box", username="alice")
        with tempfile.TemporaryDirectory() as tmp:
            etc = Path(tmp)
            (etc / "hostname").write_text("kyth-box\n")
            (etc / "passwd").write_text("root:x:0:0::/root:/bin/bash\nalice:x:1000:1000::/home/alice:/bin/bash\n")
            (etc / "fstab").write_text("# generated\n")
            checks = validate_installed_target(etc, request)
        self.assertEqual({check.name for check in checks}, {"hostname", "account", "filesystem"})

    def test_missing_installed_account_fails_closed(self):
        request = InstallRequest(hostname="kyth", username="alice")
        with tempfile.TemporaryDirectory() as tmp:
            etc = Path(tmp)
            (etc / "hostname").write_text("kyth\n")
            (etc / "passwd").write_text("root:x:0:0::/root:/bin/bash\n")
            (etc / "fstab").write_text("# generated\n")
            with self.assertRaisesRegex(RuntimeError, "was not created"):
                validate_installed_target(etc, request)


if __name__ == "__main__":
    unittest.main()
