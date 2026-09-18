"""Network preset round-trip: the Hub VPN opt-ins must survive Python load/save."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import network_preset as preset_mod  # noqa: E402


class NetworkPresetRoundTripTests(unittest.TestCase):
    def test_vpn_flags_round_trip_through_save_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "network.toml"
            cfg = {
                "dns": "cloudflare",
                "doh": False,
                "firewall_zone": "work",
                "dns_strict": True,
                "vpn_dns_exclusive": True,
                "vpn_fail_closed": True,
            }
            preset_mod.save_network_preset(cfg, path)
            reloaded = preset_mod.load_network_preset(path)
            for key, value in cfg.items():
                self.assertEqual(reloaded[key], value, key)

    def test_absent_flags_default_off_and_never_trusting(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "network.toml"
            path.write_text('dns = "quad9"\n', encoding="utf-8")
            reloaded = preset_mod.load_network_preset(path)
            self.assertFalse(reloaded["dns_strict"])
            self.assertFalse(reloaded["vpn_dns_exclusive"])
            self.assertFalse(reloaded["vpn_fail_closed"])

    def test_firewall_zone_round_trips_block_and_defaults_public(self):
        # `block` is the VPN lockdown target: it must survive a load/save
        # round-trip, never downgraded to a trusting zone.
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "network.toml"
            path.write_text('firewall_zone = "block"\n', encoding="utf-8")
            reloaded = preset_mod.load_network_preset(path)
            self.assertEqual(reloaded["firewall_zone"], "block")
            preset_mod.save_network_preset(reloaded, path)
            self.assertEqual(
                preset_mod.load_network_preset(path)["firewall_zone"], "block"
            )
        # Missing files and unknown zones fail closed to `public`, mirroring
        # the Rust preset default — never to trusting `home`.
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "absent.toml"
            self.assertEqual(
                preset_mod.load_network_preset(missing)["firewall_zone"], "public"
            )
            evil = Path(td) / "evil.toml"
            evil.write_text('firewall_zone = "dmz"\n', encoding="utf-8")
            self.assertEqual(
                preset_mod.load_network_preset(evil)["firewall_zone"], "public"
            )

    def test_strict_dot_survives_apply(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            preset_mod.apply_network_preset(
                {"dns": "quad9", "doh": True, "dns_strict": True}, root=root
            )
            conf = (
                root / "etc/systemd/resolved.conf.d/50-kyth.conf"
            ).read_text(encoding="utf-8")
            self.assertIn("DNSOverTLS=strict", conf)
            preset_mod.apply_network_preset(
                {"dns": "quad9", "doh": True}, root=root
            )
            conf = (
                root / "etc/systemd/resolved.conf.d/50-kyth.conf"
            ).read_text(encoding="utf-8")
            self.assertIn("DNSOverTLS=opportunistic", conf)


if __name__ == "__main__":
    unittest.main()
