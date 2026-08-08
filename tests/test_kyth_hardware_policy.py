"""Contracts for declarative, device-scoped KythOS hardware policy."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import hardware_policy as hp  # noqa: E402

POLICY_PATH = ROOT / "build_files/config/hardware-profiles.toml"


def device(
    bus: str,
    vendor: str,
    device_id: str,
    *,
    class_code: str = "",
    driver: str = "",
) -> hp.Device:
    return hp.Device(bus, vendor, device_id, class_code, driver)


def inventory(*, pci: tuple[hp.Device, ...] = (), usb: tuple[hp.Device, ...] = ()) -> hp.Inventory:
    return hp.Inventory("AuthenticAMD", "Example", "Desktop", "Board", pci, usb)


class HardwareInventoryTests(unittest.TestCase):
    def test_collects_sysfs_ids_driver_and_dmi_without_lspci_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pci_node = root / "pci/0000:03:00.0"
            usb_node = root / "usb/1-1"
            dmi = root / "dmi"
            drivers = root / "drivers"
            for path in (pci_node, usb_node, dmi, drivers / "amdgpu", drivers / "btusb"):
                path.mkdir(parents=True, exist_ok=True)
            (pci_node / "vendor").write_text("0x1002\n")
            (pci_node / "device").write_text("0x744c\n")
            (pci_node / "class").write_text("0x030000\n")
            (pci_node / "driver").symlink_to(drivers / "amdgpu")
            (usb_node / "idVendor").write_text("0x054c\n")
            (usb_node / "idProduct").write_text("0x0ce6\n")
            (usb_node / "product").write_text("DualSense Wireless Controller\n")
            (usb_node / "driver").symlink_to(drivers / "btusb")
            (dmi / "sys_vendor").write_text("Valve\n")
            (dmi / "product_name").write_text("Galileo\n")
            (dmi / "board_name").write_text("Jupiter\n")
            cpuinfo = root / "cpuinfo"
            cpuinfo.write_text("vendor_id\t: AuthenticAMD\n")

            result = hp.collect_inventory(
                pci_root=root / "pci",
                usb_root=root / "usb",
                dmi_root=dmi,
                cpuinfo_path=cpuinfo,
            )

        self.assertEqual(result.pci[0].vendor, "1002")
        self.assertEqual(result.pci[0].class_code, "030000")
        self.assertEqual(result.pci[0].driver, "amdgpu")
        self.assertEqual(result.usb[0].driver, "btusb")
        self.assertEqual(result.dmi_product, "Galileo")
        self.assertEqual(result.cpu_vendor, "AuthenticAMD")

    def test_inventory_digest_is_stable_and_changes_with_hardware(self):
        base = inventory(pci=(device("pci", "1002", "744c"),))
        same = inventory(pci=(device("pci", "1002", "744c"),))
        changed = inventory(pci=(device("pci", "10de", "2684"),))
        self.assertEqual(base.digest(), same.digest())
        self.assertNotEqual(base.digest(), changed.digest())


class HardwareMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy, cls.digest = hp.load_policy(POLICY_PATH)

    def profile_ids(self, current: hp.Inventory) -> set[str]:
        return {
            profile["id"]
            for profile in hp.evaluate(self.policy, self.digest, current).profiles
        }

    def test_vendor_and_class_must_match_the_same_device(self):
        current = inventory(pci=(
            device("pci", "1002", "744c", class_code="030000", driver="amdgpu"),
            device("pci", "8086", "2725", class_code="028000", driver="iwlwifi"),
        ))
        matched = self.profile_ids(current)
        self.assertIn("amd-graphics", matched)
        self.assertNotIn("intel-graphics", matched)

    def test_hybrid_profile_requires_both_display_devices(self):
        amd_only = inventory(pci=(
            device("pci", "1002", "744c", class_code="030000", driver="amdgpu"),
        ))
        hybrid = inventory(pci=(
            *amd_only.pci,
            device("pci", "10de", "2684", class_code="030200", driver="nvidia"),
        ))
        self.assertNotIn("amd-nvidia-hybrid", self.profile_ids(amd_only))
        self.assertIn("amd-nvidia-hybrid", self.profile_ids(hybrid))

    def test_driver_scoped_quirks_do_not_apply_to_nearby_vendor_devices(self):
        xe_intel = inventory(pci=(
            device("pci", "8086", "7d55", class_code="030000", driver="xe"),
        ))
        i915_intel = inventory(pci=(
            device("pci", "8086", "9a49", class_code="030000", driver="i915"),
        ))
        xe_quirks = {item["id"] for item in hp.evaluate(self.policy, self.digest, xe_intel).quirks}
        i915_quirks = {item["id"] for item in hp.evaluate(self.policy, self.digest, i915_intel).quirks}
        self.assertNotIn("intel-i915-media-firmware", xe_quirks)
        self.assertIn("intel-i915-media-firmware", i915_quirks)

    def test_dmi_handheld_profile_is_explicit(self):
        deck = hp.Inventory("AuthenticAMD", "Valve", "Galileo", "Jupiter", (), ())
        generic = hp.Inventory("AuthenticAMD", "Valve", "Desktop", "Jupiter", (), ())
        self.assertIn("valve-handheld", self.profile_ids(deck))
        self.assertNotIn("valve-handheld", self.profile_ids(generic))

    def test_expired_quirk_warns_but_remains_active(self):
        current = inventory(pci=(
            device("pci", "1002", "744c", class_code="030000", driver="amdgpu"),
        ))
        result = hp.evaluate(self.policy, self.digest, current, today=date(2028, 1, 1))
        self.assertIn("amdgpu-gaming-memory", {item["id"] for item in result.quirks})
        self.assertTrue(any("expired" in warning for warning in result.warnings))


class HardwarePolicySafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy, cls.digest = hp.load_policy(POLICY_PATH)

    def test_rejects_command_like_scheduler_value(self):
        unsafe = copy.deepcopy(self.policy)
        unsafe["profiles"][0]["policy"]["scheduler_candidates"] = ["scx_rusty\nExecStart=/bin/sh"]
        with self.assertRaises(hp.PolicyError):
            hp.validate_policy(unsafe)

    def test_rejects_unknown_match_key_instead_of_matching_broadly(self):
        unsafe = copy.deepcopy(self.policy)
        unsafe["profiles"][1]["match"]["pci_vendor"] = "1002"
        with self.assertRaises(hp.PolicyError):
            hp.validate_policy(unsafe)

    def test_rejects_modprobe_value_with_whitespace(self):
        unsafe = copy.deepcopy(self.policy)
        unsafe["quirks"][0]["actions"][0]["options"]["gttsize"] = "4096\ninstall evil"
        with self.assertRaises(hp.PolicyError):
            hp.validate_policy(unsafe)

    def test_render_contains_only_matched_driver_quirks(self):
        current = inventory(pci=(
            device("pci", "1002", "744c", class_code="030000", driver="amdgpu"),
        ))
        evaluation = hp.evaluate(self.policy, self.digest, current)
        rendered = hp.render_modprobe_config(evaluation)
        self.assertIn("options amdgpu", rendered)
        self.assertNotIn("options i915", rendered)
        self.assertNotIn("options nvidia", rendered)

    def test_booted_image_identity_uses_exact_bootc_deployment(self):
        status = {
            "status": {
                "booted": {
                    "image": {
                        "reference": "ghcr.io/example/kyth:testing",
                        "imageDigest": "sha256:" + "b" * 64,
                    }
                }
            }
        }
        with patch(
            "kyth_shared.system.bootc.fetch_bootc_status_data_uncached",
            return_value=status,
        ):
            self.assertEqual(
                hp.booted_image_identity(),
                ("ghcr.io/example/kyth:testing", "sha256:" + "b" * 64),
            )

    def test_apply_is_atomic_and_skips_unchanged_identity(self):
        current = inventory(pci=(
            device("pci", "1002", "744c", class_code="030000", driver="amdgpu"),
        ))
        evaluation = hp.evaluate(self.policy, self.digest, current)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state.json"
            report = root / "report.json"
            modprobe = root / "policy.conf"
            with (
                patch.object(hp.os, "geteuid", return_value=0),
                patch.object(hp, "evaluate_system", return_value=evaluation),
                patch.object(hp, "MANAGED_MODPROBE_PATH", modprobe),
                patch.object(hp, "run_text", return_value=SimpleNamespace(stdout="6.18.1\n")),
                patch.object(hp, "booted_image_identity", return_value=("ghcr.io/example/kyth:testing", "sha256:" + "a" * 64)),
                patch.object(hp, "_configure_scheduler", return_value="scx_rusty") as scheduler,
                patch.object(hp, "_configure_nvidia", return_value="unused") as nvidia,
                patch.object(hp, "_clear_nvidia_policy", return_value="not-required") as clear_nvidia,
            ):
                first = hp.apply_system(state_path=state, report_path=report)
                second = hp.apply_system(state_path=state, report_path=report)

            self.assertEqual(first["status"], "applied")
            self.assertEqual(second, first)
            self.assertEqual(scheduler.call_count, 1)
            nvidia.assert_not_called()
            self.assertEqual(clear_nvidia.call_count, 1)
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(report.read_text())["evaluation"]["policy_revision"], "2026.08.1")

    def test_generated_support_matrix_is_current(self):
        expected = (ROOT / "docs/hardware-support-matrix.md").read_text()
        self.assertEqual(hp.support_matrix(self.policy), expected)

    def test_image_installs_policy_and_service_has_no_permanent_done_marker(self):
        install = (ROOT / "build_files/scripts/branding/26-dolphin-new-document-templates.sh").read_text()
        service = (ROOT / "build_files/kyth-hw-setup.service").read_text()
        retry = (ROOT / "build_files/kyth-retry-hardware-setup").read_text()
        self.assertIn("hardware-profiles.toml", install)
        self.assertNotIn("hw-setup-done", service)
        self.assertIn("kyth-hardware-policy apply --force", retry)

    def test_blanket_power_and_driver_options_are_removed(self):
        migration = (ROOT / "build_files/scripts/branding/28-bootc-kernel-arguments-and-boot-splash.sh").read_text()
        self.assertEqual(migration.count("pcie_aspm=performance"), 1)
        self.assertIn('--remove-args="console=tty0 console=ttyS0,115200 amdgpu.ppfeaturemask', migration)
        for relative in (
            "build_files/scripts/sysconfig/gpu/10-amd-gpu-kernel-module-options.sh",
            "build_files/scripts/sysconfig/gpu/11-nvidia-kernel-module-options.sh",
            "build_files/scripts/sysconfig/gpu/12-intel-gpu-kernel-module-options.sh",
        ):
            self.assertNotIn("write_config", (ROOT / relative).read_text())


if __name__ == "__main__":
    unittest.main()
