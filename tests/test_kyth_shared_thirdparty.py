"""Tests for kyth_shared.thirdparty module.

Written as unittest.TestCase subclasses (not bare pytest-style functions)
on purpose: this repo's suite runs under `python3 -m unittest discover`
(see `just test`), which never collects module-level `def test_...():`
functions — only TestCase methods. An earlier version of this file used
bare functions with pytest fixtures (`tmp_path`, `monkeypatch`); they
imported fine, so `just test` reported success, but none of their
assertions ever ran.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.thirdparty import (
    find_latest_davinci_zip,
    prepare_davinci_resolve,
)


class FindLatestDavinciZipTests(unittest.TestCase):
    def test_finds_a_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip1 = tmp_path / "DaVinci_Resolve_18_Linux.zip"
            zip1.write_bytes(b"dummy")
            self.assertEqual(find_latest_davinci_zip(download_dir=tmp_path), zip1)

    def test_no_candidates_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "not-a-davinci-file.txt").write_bytes(b"dummy")
            self.assertIsNone(find_latest_davinci_zip(download_dir=tmp_path))

    def test_missing_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            self.assertIsNone(find_latest_davinci_zip(download_dir=missing))


class PrepareDavinciResolveTests(unittest.TestCase):
    def test_studio_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "DaVinci_Resolve_Studio_18.6_Linux.zip"
            zip_path.write_bytes(b"dummy")
            meta = prepare_davinci_resolve(zip_path)
            self.assertEqual(meta["app_id"], "com.blackmagic.ResolveStudio")
            self.assertEqual(meta["manifest"], "com.blackmagic.ResolveStudio.yaml")
            self.assertEqual(meta["is_studio"], "true")

    def test_non_studio_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "DaVinci_Resolve_18.6_Linux.zip"
            zip_path.write_bytes(b"dummy")
            meta = prepare_davinci_resolve(zip_path)
            self.assertEqual(meta["app_id"], "com.blackmagic.Resolve")
            self.assertEqual(meta["manifest"], "com.blackmagic.Resolve.yaml")
            self.assertEqual(meta["is_studio"], "false")

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                prepare_davinci_resolve(Path(tmp) / "missing.zip")


class WidevineSupplyChainTests(unittest.TestCase):
    def test_legacy_unauthenticated_widevine_downloader_is_not_shipped(self):
        source = (ROOT / "build_files/kyth_shared/kyth_shared/thirdparty.py").read_text(
            encoding="utf-8"
        )
        branding = (
            ROOT / "build_files/scripts/branding/36-misc-utility-installs.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("widevine", source.lower())
        self.assertNotIn("kyth-widevine-install", branding)
        self.assertFalse((ROOT / "build_files/kyth-widevine-install").exists())


if __name__ == "__main__":
    unittest.main()
