"""Contracts for kyth_shared.selinux_preset save/load.

The saver previously rendered the permissive list with Python-repr single
quotes, which TOML cannot parse back: any saved non-empty preset silently
reloaded as defaults. These tests pin valid-TOML output and the
load-side validation. Mirrors the native port's tests in
src/kyth-shared-rs/src/system/selinux_preset.rs.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth_shared"))

from kyth_shared.selinux_preset import load_selinux, save_selinux  # noqa: E402


class SelinuxPresetTests(unittest.TestCase):
    def test_save_round_trips_through_toml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selinux.toml"
            cfg = {
                "permissive": ["httpd_t", "dnsmasq_t"],
                "booleans": {"httpd_can_network_connect": True},
            }
            save_selinux(cfg, path)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("'", raw.split("#", 1)[1])
            self.assertEqual(load_selinux(path), cfg)

    def test_missing_or_malformed_file_loads_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.toml"
            self.assertEqual(
                load_selinux(missing), {"permissive": [], "booleans": {}}
            )
            bad = Path(directory) / "bad.toml"
            bad.write_text("permissive = [unquoted\n[booleans\n", encoding="utf-8")
            self.assertEqual(load_selinux(bad), {"permissive": [], "booleans": {}})

    def test_wrong_types_follow_python_truthiness(self) -> None:
        # load_selinux coerces with bool(v): document the exact contract the
        # native port must match rather than asserting stricter behavior.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "types.toml"
            path.write_text(
                'permissive = "nope"\n[booleans]\nflag = "maybe"\nempty = ""\nzero = 0\n',
                encoding="utf-8",
            )
            self.assertEqual(
                load_selinux(path),
                {
                    "permissive": [],
                    "booleans": {"flag": True, "empty": False, "zero": False},
                },
            )


if __name__ == "__main__":
    unittest.main()
