"""Static contract tests for unattended live/install/update/rollback gating."""
from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUEST = ROOT / "build_files" / "kyth-vm-acceptance-guest"
HOST = ROOT / "build_files" / "scripts" / "vm-acceptance.sh"
UNIT = ROOT / "build_files" / "kyth-vm-acceptance.service"
WORKFLOW = ROOT / ".github" / "workflows" / "build-live-iso.yml"


class VmAcceptanceTests(unittest.TestCase):
    def test_scripts_parse_as_bash(self):
        for script in (GUEST, HOST):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_guest_is_firmware_gated_and_covers_lifecycle(self):
        text = GUEST.read_text(encoding="utf-8")
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

    def test_host_uses_a_dedicated_disk_and_collects_evidence(self):
        text = HOST.read_text(encoding="utf-8")
        self.assertIn("qemu-img create", text)
        self.assertIn("serial=KYTH_ACCEPT", text)
        self.assertIn("live-desktop.ppm", text)
        self.assertIn("installed-login.ppm", text)
        self.assertIn("KYTH_ACCEPTANCE:FAILED", text)

    def test_workflow_gates_unsigned_iso_upload(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        acceptance = text.index("- name: Boot, install, update, and rollback acceptance")
        upload = text.index("- name: Upload unsigned ISO artifact")
        self.assertLess(acceptance, upload)
        self.assertIn("acceptance_update_ref", text)
        self.assertIn("Upload VM acceptance evidence", text)


if __name__ == "__main__":
    unittest.main()
