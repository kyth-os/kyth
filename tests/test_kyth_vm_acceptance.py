"""Static contract tests for unattended live/install/update/rollback gating."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUEST = ROOT / "build_files" / "kyth-vm-acceptance-guest"
HOST = ROOT / "build_files" / "scripts" / "vm-acceptance.sh"
UNIT = ROOT / "build_files" / "kyth-vm-acceptance.service"
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import vm_acceptance


class VmAcceptanceTests(unittest.TestCase):
    def test_launchers_parse(self):
        subprocess.run(["python3", "-m", "py_compile", str(GUEST)], check=True)
        subprocess.run(["bash", "-n", str(HOST)], check=True)

    def test_guest_is_firmware_gated_and_covers_lifecycle(self):
        text = pathlib.Path(vm_acceptance.__file__).read_text(encoding="utf-8")
        self.assertIn("/sys/firmware/qemu_fw_cfg/by_name/opt/com.kyth", text)
        self.assertIn("ExecCondition", UNIT.read_text(encoding="utf-8"))
        for phase in (
            "LIVE_READY", "INSTALL_COMPLETE", "INSTALLED_READY",
            "UPDATE_STAGED", "UPDATE_BOOTED", "ROLLBACK_STAGED",
            "ROLLBACK_BOOTED", "COMPLETE", "FAILED",
        ):
            self.assertIn(phase, text)
        self.assertIn("oci:/usr/share/kyth/image:latest", text)
        self.assertIn("virtio-KYTH_ACCEPT", text)

    def test_live_build_bundles_the_installer_image(self):
        build = (ROOT / "installer" / "build.sh").read_text(encoding="utf-8")
        containerfile = (ROOT / "installer" / "Containerfile").read_text(encoding="utf-8")

        self.assertIn('"oci:/usr/share/kyth/image:latest"', build)
        self.assertIn("skopeo copy --retry-times 3", build)
        self.assertIn("KYTH_SOURCE_IMAGE=oci:/usr/share/kyth/image:latest", build)
        self.assertIn("INSTALL_SOURCE_IMAGE", containerfile)

    def test_update_reference_policy(self):
        self.assertTrue(vm_acceptance.valid_update_ref("ghcr.io/example/kyth:testing"))
        self.assertTrue(vm_acceptance.valid_update_ref(""))
        self.assertFalse(vm_acceptance.valid_update_ref("image; poweroff"))

    def test_bootc_status_json_parsing(self):
        completed = subprocess.CompletedProcess(
            ["bootc"], 0,
            stdout='{"status":{"booted":{"image":{"imageDigest":"sha256:abc"}}}}',
            stderr="",
        )
        with mock.patch("kyth_shared.vm_acceptance.run_text", return_value=completed):
            self.assertEqual(vm_acceptance.booted_digest(), "sha256:abc")

    def test_host_uses_a_dedicated_disk_and_collects_evidence(self):
        text = HOST.read_text(encoding="utf-8")
        self.assertIn("qemu-img create", text)
        self.assertIn("serial=KYTH_ACCEPT", text)
        self.assertIn("live-desktop.ppm", text)
        self.assertIn("installed-login.ppm", text)
        self.assertIn("KYTH_ACCEPTANCE:FAILED", text)


if __name__ == "__main__":
    unittest.main()
