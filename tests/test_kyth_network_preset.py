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

    def test_save_escapes_toml_injection_and_writes_atomically(self):
        # A hostile saver dict (quote + newline + section) must round-trip
        # as data, never as injected TOML the root daemon would parse.
        # dns itself is enum-clamped, so exercise the escaper on the
        # free-text cloud/backup savers sharing the same helper.
        from kyth_shared import backup_preset, cloud_preset
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cloud.toml"
            cloud_preset.save_cloud(
                {"gdrive": {"remote": 'r"\n[evil2]\nkey = "y'}},
                path,
            )
            body = path.read_text(encoding="utf-8")
            # No real newline-section injection: the literal text "[evil2]"
            # survives only inside an escaped string value.
            self.assertNotIn("\n[evil2]", body)
            import tomllib
            reparsed = tomllib.loads(body)
            self.assertEqual(
                reparsed["drives"]["gdrive"]["remote"], 'r"\n[evil2]\nkey = "y'
            )
            # Drive names become section headers: hostile ones are refused,
            # not escaped.
            with self.assertRaises(ValueError):
                cloud_preset.save_cloud(
                    {'gdrive"\n[evil]\nremote = "x': {"remote": "r"}}, path
                )
            self.assertNotIn("[evil]", path.read_text(encoding="utf-8"))
            bpath = Path(td) / "backup.toml"
            backup_preset.save_backup({"repo": '/x"\n[evil3]\n', "remote": "r"}, bpath)
            bbody = bpath.read_text(encoding="utf-8")
            self.assertNotIn("\n[evil3]", bbody)
        # Symlink at the target: atomic_write_text refuses instead of
        # writing through to an arbitrary file.
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "network.toml"
            link = Path(td) / "link.toml"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                preset_mod.save_network_preset({"dns": "quad9"}, link)
            self.assertFalse(target.exists())

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
