"""Cover vrr, window_snap, work_cache — off 0% to lift floor."""
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import vrr as vrr_mod
from kyth_shared import window_snap as snap_mod
from kyth_shared import work_cache as wc_mod


class VrrTests(unittest.TestCase):
    def test_load_default_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "vrr.toml"
            cfg = vrr_mod.load_vrr(p)
            self.assertEqual(cfg["night"]["temperature"], 4500)
            self.assertFalse(cfg["night"]["enabled"])

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "vrr.toml"
            cfg = {"outputs": {"HDMI-A-1": {"vrr": "always"}}, "night": {"enabled": True, "temperature": 5000}}
            vrr_mod.save_vrr(cfg, p)
            loaded = vrr_mod.load_vrr(p)
            self.assertEqual(loaded["outputs"]["HDMI-A-1"]["vrr"], "always")
            self.assertEqual(loaded["night"]["temperature"], 5000)

    def test_clamp_temperature(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "vrr.toml"
            p.write_text('[night]\nenabled=true\ntemperature=9999\n', encoding="utf-8")
            cfg = vrr_mod.load_vrr(p)
            self.assertEqual(cfg["night"]["temperature"], 6500)

    def test_invalid_vrr_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "vrr.toml"
            p.write_text('[outputs."DP-1"]\nvrr="bogus"\n', encoding="utf-8")
            cfg = vrr_mod.load_vrr(p)
            self.assertEqual(cfg["outputs"]["DP-1"]["vrr"], "adaptive")


class WindowSnapTests(unittest.TestCase):
    def test_load_default(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "snap.toml"
            cfg = snap_mod.load_snap(p)
            self.assertEqual(cfg["layout"], "2x2")
            self.assertTrue(cfg["win_z"])

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "snap.toml"
            cfg = {"layout": "3col", "win_z": False, "electric": False}
            snap_mod.save_snap(cfg, p)
            loaded = snap_mod.load_snap(p)
            self.assertEqual(loaded["layout"], "3col")
            self.assertFalse(loaded["win_z"])

    def test_apply_returns_list(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "snap.toml"
            cfg = {"layout": "2x2", "win_z": True, "electric": True}
            # avoid touching real kwinrc — mock run via patch of commands.run
            from unittest.mock import patch
            with patch.object(snap_mod, "run", return_value=None):
                applied = snap_mod.apply_snap(cfg)
                self.assertIsInstance(applied, list)


class WorkCacheTests(unittest.TestCase):
    def test_load_default(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "wc.toml"
            cfg = wc_mod.load_work_cache(p)
            self.assertFalse(cfg["enabled"])
            self.assertEqual(cfg["size"], "1G")

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "wc.toml"
            wc_mod.save_work_cache({"enabled": True, "size": "4G"}, p)
            cfg = wc_mod.load_work_cache(p)
            self.assertTrue(cfg["enabled"])
            self.assertEqual(cfg["size"], "4G")

    def test_generate_creates_service(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            svc = td / "svc.service"
            tmp = td / "tmp.conf"
            # disabled -> no file
            res = wc_mod.generate_work_cache({"enabled": False}, tmpfiles=tmp, service=svc)
            self.assertIsNone(res)
            self.assertFalse(svc.exists())
            # enabled -> file
            res = wc_mod.generate_work_cache({"enabled": True, "size": "2G"}, tmpfiles=tmp, service=svc)
            self.assertIsNotNone(res)
            self.assertTrue(svc.exists())
            self.assertIn("2G", svc.read_text())

    def test_status(self):
        with tempfile.TemporaryDirectory() as td:
            svc = Path(td) / "svc.service"
            self.assertEqual(wc_mod.work_cache_status(svc), "off")
            svc.write_text("x")
            self.assertEqual(wc_mod.work_cache_status(svc), "enabled")
