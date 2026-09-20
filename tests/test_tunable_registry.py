"""Tests for tunable registry (Slice 2)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kyth_shared.tunable import (
    TunableSpec,
    _import_module,
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

    def test_import_module_refuses_unknown_names(self):
        # A hostile tunables.toml entry must never reach importlib: only
        # builtin registry modules load.
        for bad in ("os", "subprocess", "kyth_shared.os", "../evil", "", "work-cache"):
            with self.subTest(module=bad):
                with self.assertRaises(ImportError):
                    _import_module(TunableSpec(name="evil", module=bad, kind="other", wrapper="kyth-evil"))
        # A legit builtin still loads.
        mod = _import_module(TunableSpec(name="work-cache", module="work_cache", kind="other", wrapper="kyth-work-cache"))
        self.assertTrue(hasattr(mod, "generate_work_cache"))

    def test_size_injection_never_reaches_shell_lines(self):
        # generate_* must normalize sizes against the allowlist even when
        # the dict never went through load_ (generic generate_tunable path).
        from kyth_shared import distrobox_cache, shader_tmpfs, work_cache
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            svc = tmpdir / "svc.service"
            tmpfiles = tmpdir / "t.conf"
            res = distrobox_cache.generate_distrobox_cache(
                {"enabled": True, "size": "1G; touch /tmp/pwned", "ccache_size": "10G; id"},
                tmpfiles=tmpfiles, service=svc,
            )
            self.assertIsNotNone(res)
            body = svc.read_text()
            self.assertNotIn("touch", body)
            self.assertNotIn("; id", body)
            self.assertIn("size=4G", body)
            self.assertIn("max-size=10G", body)
            res = work_cache.generate_work_cache(
                {"enabled": True, "size": "9G; touch /tmp/pwned"},
                tmpfiles=tmpdir / "w.conf", service=tmpdir / "w.service",
            )
            self.assertNotIn("touch", (tmpdir / "w.service").read_text())
            res = shader_tmpfs.generate_shader_tmpfs(
                {"enabled": True, "size": "9G; touch /tmp/pwned"},
                tmpfiles=tmpdir / "s.conf", service=tmpdir / "s.service",
                env_dropin=tmpdir / "s.env",
            )
            self.assertNotIn("touch", (tmpdir / "s.service").read_text())
            self.assertIn("MESA_SHADER_CACHE_PATH=/run/kyth-shader", (tmpdir / "s.env").read_text())

    def test_other_kind_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            # ananicy is other kind — still has load/save/generate
            cfg = load_tunable("ananicy", path=Path(tmp) / "ananicy.toml")
            self.assertIsInstance(cfg, dict)
            # ensure we can call status (may be balanced vs custom)
            try:
                st = tunable_status("ananicy")
            except Exception as exc:
                self.skipTest(f"tunable status unavailable in test env: {exc}")
            self.assertIsInstance(st, str)
