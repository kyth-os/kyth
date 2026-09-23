"""Round 9 pins: irq fail-closed, kargs quoting, zswap allowlist, wine probe."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class IrqTuneFailClosedTests(unittest.TestCase):
    def test_generate_refuses_empty_and_poison_cpu_lists(self) -> None:
        from kyth_shared.irq_tune import generate_irq_conf

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "99-kyth.conf"
            with mock.patch("kyth_shared.performance.get_amd_ccd0_cpus", return_value=""), mock.patch(
                "kyth_shared.performance.get_intel_pcores", return_value=""
            ):
                with self.assertRaises(ValueError):
                    generate_irq_conf({"profile": "kyth", "isolated_cpus": ""}, dest)
            self.assertFalse(dest.exists())
            with self.assertRaises(ValueError):
                generate_irq_conf({"profile": "kyth", "isolated_cpus": "1; id"}, dest)
            self.assertFalse(dest.exists())
            out = generate_irq_conf({"profile": "kyth", "isolated_cpus": "0,2-3"}, dest)
            self.assertEqual(out, dest)
            text = dest.read_text(encoding="utf-8")
            self.assertIn("--banned-cpus=0,2-3", text)
            self.assertNotIn(";", text)


class IrqSaveSanitizesTests(unittest.TestCase):
    def test_save_drops_poison_isolated_cpus(self) -> None:
        from kyth_shared.irq_tune import load_irq, save_irq

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "irq.toml"
            save_irq({"profile": "kyth", "isolated_cpus": "1; id"}, path)
            loaded = load_irq(path)
            self.assertEqual(loaded["isolated_cpus"], "")


class KargsQuoteTests(unittest.TestCase):
    def test_save_kargs_round_trips_quoted_custom_add(self) -> None:
        from kyth_shared.kargs_preset import load_kargs, save_kargs

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kargs.toml"
            save_kargs(
                {
                    "profile": "gaming",
                    "custom_add": ['foo="bar"', r"path=C:\temp"],
                    "custom_remove": [],
                },
                path,
            )
            loaded = load_kargs(path)
            self.assertEqual(loaded["profile"], "gaming")
            self.assertEqual(loaded["custom_add"], ['foo="bar"', r"path=C:\temp"])


class ZswapAllowlistTests(unittest.TestCase):
    def test_generate_zswap_rejects_injected_compressor(self) -> None:
        from kyth_shared.zswap_preset import generate_zswap, save_zswap

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "zswap.toml"
            conf = Path(tmp) / "99-kyth-zswap.conf"
            mod = Path(tmp) / "zswap.conf"
            save_zswap({"profile": "kyth", "compressor": "zstd;id", "zpool": "zsmalloc"}, cfg_path)
            generate_zswap({"profile": "kyth", "compressor": "zstd;id", "zpool": "evil"}, conf, mod)
            text = conf.read_text(encoding="utf-8")
            self.assertIn("vm.zswap_compressor = zstd", text)
            self.assertIn("vm.zswap_zpool = zsmalloc", text)
            self.assertNotIn(";", text)
            self.assertNotIn("evil", text)


class WineSyncProbeTests(unittest.TestCase):
    def test_probe_uses_osrelease_not_proc_version_substring(self) -> None:
        from kyth_shared import wine_sync

        class FakePath:
            def __init__(self, value: str) -> None:
                self.value = value

            def exists(self) -> bool:
                return False

            def read_text(self, encoding: str = "utf-8") -> str:
                del encoding
                if self.value == "/proc/sys/kernel/osrelease":
                    return "5.15.0-100-generic\n"
                raise AssertionError(f"unexpected path {self.value}")

        with mock.patch.object(wine_sync, "Path", FakePath):
            probe = wine_sync.probe_wine_sync()
        self.assertFalse(probe["futex2"])


class SteamInputQuoteTests(unittest.TestCase):
    def test_save_quotes_poison_app_id(self) -> None:
        from kyth_shared.steam_input import load_steam_input, save_steam_input

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "steam-input.toml"
            save_steam_input(
                {
                    '570"]\nlayout = "hack': {"layout": 'gamepad"\ngyro = true', "gyro": False},
                    "570": {"layout": "gamepad", "gyro": True, "deadzone": 0.1},
                },
                path,
            )
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("layout = \"hack", text)
            loaded = load_steam_input(path)
            self.assertIn("570", loaded)
            self.assertTrue(loaded["570"]["gyro"])


class OverlayQuoteTests(unittest.TestCase):
    def test_save_quotes_poison_app_id(self) -> None:
        from kyth_shared.overlay_preset import load_overlay, save_overlay

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overlay.toml"
            save_overlay(
                {
                    '570"]\nvkbasalt = "cas': {"mangohud_layout": "fps", "vkbasalt": "off"},
                    "570": {"mangohud_layout": "fps+frametime", "vkbasalt": "cas"},
                },
                path,
            )
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('vkbasalt = "cas\n', text)
            loaded = load_overlay(path)
            self.assertEqual(loaded["570"]["vkbasalt"], "cas")


class IoTuneClampTests(unittest.TestCase):
    def test_generate_clamps_read_ahead(self) -> None:
        from kyth_shared.io_tune import generate_io_udev

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "61-kyth-io-tune.rules"
            generate_io_udev({"profile": "kyth", "read_ahead_kb": 999999}, dest)
            text = dest.read_text(encoding="utf-8")
            self.assertIn('ATTR{queue/read_ahead_kb}="4096"', text)
            self.assertNotIn("999999", text)


class AnanicyIoclassTests(unittest.TestCase):
    def test_generate_allowlists_ioclass(self) -> None:
        from kyth_shared.ananicy_preset import generate_ananicy

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "99-kyth-gaming.conf"
            generate_ananicy(
                {"profile": "kyth", "nice": -12, "ioclass": 'realtime","pwn":true'},
                dest,
            )
            text = dest.read_text(encoding="utf-8")
            self.assertIn('"ioclass":"realtime"', text)
            self.assertNotIn("pwn", text)


if __name__ == "__main__":
    unittest.main()
