"""Regression: ASUS TUF AMD vs Intel+NVIDIA vs AMD desktop cross-vendor quirk isolation.

Ensures bulletproofing from the TUF hardening (asustuf quirk, PSR 15be/164e,
kargs drop, BORE/SCX) does not leak to non-TUF Intel/NVIDIA/AMD hosts.
Mirrors the live verification in the last production review.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import hardware_policy as hp
import kyth_shared.kargs_preset as kargs_preset
import kyth_shared.bore_tune as bore_tune

POLICY_PATH = ROOT / "build_files/config/hardware-profiles.toml"


def load_policy():
    return hp.load_policy(POLICY_PATH)


def inv_tuf_amd():
    # TUF A16 Phoenix 15be 780M + Cachy
    return hp.Inventory(
        "AuthenticAMD",
        "ASUSTeK COMPUTER INC.",
        "TUF Gaming A16",
        "Board",
        (hp.Device("pci", "1002", "15be", "0300", "amdgpu"),),
        (),
    )


def inv_intel_nvidia():
    return hp.Inventory(
        "GenuineIntel",
        "Dell Inc.",
        "XPS 15",
        "Board",
        (
            hp.Device("pci", "8086", "1234", "0300", "i915"),
            hp.Device("pci", "10de", "2786", "0300", "nvidia"),
            hp.Device("pci", "8086", "2725", "0280", "iwlwifi"),
        ),
        (hp.Device("usb", "8087", "0026", "", "btusb"),),
    )


def inv_amd_desktop():
    return hp.Inventory(
        "AuthenticAMD",
        "ASUSTeK COMPUTER INC.",
        "ROG STRIX",
        "Board",
        (hp.Device("pci", "1002", "7480", "0300", "amdgpu"),),
        (),
    )


class TufCrossVendorTests(unittest.TestCase):
    def test_tuf_gets_tuf_quirk_and_conservative_gtt(self):
        data, digest = load_policy()
        ev = hp.evaluate(data, digest, inv_tuf_amd())
        ids = [q["id"] for q in ev.quirks]
        self.assertIn("amdgpu-gaming-memory", ids)
        self.assertIn("asus-tuf-amd-cachy-stability", ids)
        self.assertIn("amdgpu-psr-disable", ids)
        # TUF's conservative gttsize 2048 must win over gaming-memory 4096 (last-wins)
        # Simulate modprobe generation order: asus-tuf after gaming-memory
        # Check TOML order: gaming-memory (4096) before asus-tuf (2048)
        toml_text = POLICY_PATH.read_text()
        self.assertLess(toml_text.index("amdgpu-gaming-memory"), toml_text.index("asus-tuf-amd-cachy-stability"))

    def test_intel_nvidia_gets_no_amdgpu_quirks(self):
        data, digest = load_policy()
        ev = hp.evaluate(data, digest, inv_intel_nvidia())
        ids = [q["id"] for q in ev.quirks]
        self.assertIn("intel-i915-media-firmware", ids)
        self.assertIn("nvidia-wayland-suspend", ids)
        self.assertNotIn("amdgpu-gaming-memory", ids)
        self.assertNotIn("asus-tuf-amd-cachy-stability", ids)
        self.assertNotIn("amdgpu-psr-disable", ids)

    def test_amd_desktop_gets_gaming_no_tuf(self):
        data, digest = load_policy()
        ev = hp.evaluate(data, digest, inv_amd_desktop())
        ids = [q["id"] for q in ev.quirks]
        self.assertIn("amdgpu-gaming-memory", ids)
        self.assertIn("amdgpu-psr-disable", ids)
        self.assertNotIn("asus-tuf-amd-cachy-stability", ids)

    def test_kargs_tuf_cachy_drops_mitigations(self):
        with mock.patch.object(kargs_preset, "_is_tuf_amd_cachy", return_value=True):
            gaming = kargs_preset.desired_kargs({"profile": "gaming"})
            self.assertNotIn("mitigations=off", gaming)
            self.assertNotIn("preempt=full", gaming)
            self.assertIn("amd_pstate=active", gaming)
        with mock.patch.object(kargs_preset, "_is_tuf_amd_cachy", return_value=False):
            gaming = kargs_preset.desired_kargs({"profile": "gaming"})
            self.assertIn("mitigations=off", gaming)
            self.assertIn("preempt=full", gaming)

    def test_bore_bails_on_scx(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cfg = {"profile": "gaming"}
            with mock.patch("kyth_shared.sched_arbiter.detect_scx_active", return_value=True):
                dest = td / "bore-active.conf"
                res = bore_tune.generate_bore(cfg, dest=dest)
                self.assertIsNone(res)
                self.assertFalse(dest.exists())
            with mock.patch("kyth_shared.sched_arbiter.detect_scx_active", return_value=False):
                dest2 = td / "bore-inactive.conf"
                res2 = bore_tune.generate_bore(cfg, dest=dest2)
                self.assertIsNotNone(res2)
                self.assertTrue(dest2.exists())

    def test_psr_devices_include_phoenix(self):
        data, _ = load_policy()
        psr = next(q for q in data["quirks"] if q["id"] == "amdgpu-psr-disable")
        devs = set()
        for sel in psr["match"]["pci"]:
            devs.update(sel.get("devices", []))
        for want in ("15be", "164e", "15bf", "15b9", "7480", "1681"):
            self.assertIn(want, devs)
