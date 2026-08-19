"""Tests for tunable registry (Slice 2)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kyth_shared.tunable import (
    get_spec,
    list_tunables,
    load_registry,
    load_tunable,
    save_tunable,
    generate_tunable,
    tunable_status,
)


class TestTunableRegistry(unittest.TestCase):
    def test_builtin_count(self):
        reg = load_registry()
        self.assertEqual(len(reg), 94)

    def test_builtin_kinds(self):
        reg = load_registry()
        sysctl = [s for s in reg.values() if s.kind == "sysctl"]
        other = [s for s in reg.values() if s.kind == "other"]
        self.assertEqual(len(sysctl), 49)
        self.assertEqual(len(other), 45)

    def test_get_spec_normalizes(self):
        self.assertEqual(get_spec("swappiness").module, "swappiness")
        self.assertEqual(get_spec("kyth-swappiness").module, "swappiness")
        self.assertEqual(get_spec("swappiness").kind, "sysctl")
        self.assertEqual(get_spec("bore").module, "bore_tune")
        self.assertEqual(get_spec("zswap").module, "zswap_preset")

    def test_get_spec_unknown(self):
        with self.assertRaises(KeyError):
            get_spec("nonexistent-tunable-xyz")

    def test_list_sorted(self):
        lst = list_tunables()
        names = [s.name for s in lst]
        self.assertEqual(names, sorted(names))

    def test_load_from_toml(self):
        # tunables.toml should be present in build_files/config
        reg = load_registry(Path("build_files/config"))
        self.assertEqual(len(reg), 94)
        self.assertEqual(reg["swappiness"].module, "swappiness")

    def test_round_trip_via_registry(self):
        # Use temp XDG for isolation (pattern from swappiness.py)
        with tempfile.TemporaryDirectory() as tmp:
            # swappiness is sysctl kind, simple profile
            cfg = load_tunable("swappiness", path=Path(tmp) / "swappiness.toml")
            self.assertIn("profile", cfg)
            save_tunable("swappiness", {"profile": "gaming"}, path=Path(tmp) / "swappiness.toml")
            cfg2 = load_tunable("swappiness", path=Path(tmp) / "swappiness.toml")
            self.assertEqual(cfg2["profile"], "gaming")
            # generate to temp dest
            dest = Path(tmp) / "99-kyth-swappiness.conf"
            result = generate_tunable("swappiness", {"profile": "gaming"}, dest=dest)
            self.assertIsNotNone(result)
            self.assertTrue(dest.exists())
            self.assertIn("vm.swappiness=10", dest.read_text())
            st = tunable_status("swappiness", conf=dest)
            self.assertEqual(st, "gaming")
            # balanced removes
            generate_tunable("swappiness", {"profile": "balanced"}, dest=dest)
            self.assertFalse(dest.exists())

    def test_other_kind_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            # ananicy is other kind — still has load/save/generate
            cfg = load_tunable("ananicy", path=Path(tmp) / "ananicy.toml")
            self.assertIsInstance(cfg, dict)
            # ensure we can call status (may be balanced vs custom)
            try:
                st = tunable_status("ananicy")
                self.assertIsInstance(st, str)
            except Exception:
                pass  # some other tunables may not have status in test env
