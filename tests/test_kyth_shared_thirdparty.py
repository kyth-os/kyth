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

import io
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock
from unittest.mock import patch, MagicMock
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.thirdparty import (
    download_file,
    fetch_widevine_version,
    find_latest_davinci_zip,
    install_widevine_cdm,
    prepare_davinci_resolve,
)


class FetchWidevineVersionTests(unittest.TestCase):
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.readline.return_value = b"4.10.2710.0\n"
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            self.assertEqual(fetch_widevine_version(), "4.10.2710.0")

    def test_empty_response_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.readline.return_value = b""
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            self.assertIsNone(fetch_widevine_version())

    def test_network_error_returns_none(self):
        with patch("urllib.request.urlopen", side_effect=OSError("no network")):
            self.assertIsNone(fetch_widevine_version())


class DownloadFileTests(unittest.TestCase):
    def test_success_writes_response_body(self):
        payload = b"widevine bytes"
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [payload, b""]
        mock_resp.__enter__.return_value = mock_resp
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            with patch("urllib.request.urlopen", return_value=mock_resp):
                self.assertTrue(download_file("https://example.invalid/x", dest))
            self.assertEqual(dest.read_bytes(), payload)

    def test_failure_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            with patch("urllib.request.urlopen", side_effect=OSError("boom")):
                self.assertFalse(download_file("https://example.invalid/x", dest))
            self.assertFalse(dest.exists())


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


class InstallWidevineCdmTests(unittest.TestCase):
    @staticmethod
    def _fake_widevine_zip_bytes() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("libwidevinecdm.so", b"fake-so")
            zf.writestr("manifest.json", b"{}")
        return buf.getvalue()

    def test_fails_when_version_lookup_fails(self):
        with patch("kyth_shared.thirdparty.fetch_widevine_version", return_value=None):
            self.assertEqual(install_widevine_cdm(), 1)

    def test_fails_when_download_fails(self):
        with patch("kyth_shared.thirdparty.fetch_widevine_version", return_value="1.2.3"), \
             patch("kyth_shared.thirdparty.download_file", return_value=False):
            self.assertEqual(install_widevine_cdm(), 1)

    def test_fails_when_zip_is_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            def fake_download(_url, dest):
                Path(dest).write_bytes(b"not a zip")
                return True

            with mock.patch.object(Path, "home", return_value=tmp_path), \
                 patch("kyth_shared.thirdparty.fetch_widevine_version", return_value="1.2.3"), \
                 patch("kyth_shared.thirdparty.download_file", side_effect=fake_download):
                self.assertEqual(install_widevine_cdm(), 1)

    def test_fails_when_required_files_missing_from_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("readme.txt", b"nothing useful here")

            def fake_download(_url, dest):
                Path(dest).write_bytes(buf.getvalue())
                return True

            with mock.patch.object(Path, "home", return_value=tmp_path), \
                 patch("kyth_shared.thirdparty.fetch_widevine_version", return_value="1.2.3"), \
                 patch("kyth_shared.thirdparty.download_file", side_effect=fake_download):
                self.assertEqual(install_widevine_cdm(), 1)

    def test_returns_nonzero_when_no_supported_browser_is_installed(self):
        # No ~/.var/app/<browser> directories exist, so nothing to install into.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            payload = self._fake_widevine_zip_bytes()

            def fake_download(_url, dest):
                Path(dest).write_bytes(payload)
                return True

            with mock.patch.object(Path, "home", return_value=tmp_path), \
                 patch("kyth_shared.thirdparty.fetch_widevine_version", return_value="1.2.3"), \
                 patch("kyth_shared.thirdparty.download_file", side_effect=fake_download):
                self.assertEqual(install_widevine_cdm(), 1)

    def test_installs_into_every_present_flatpak_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".var" / "app" / "org.mozilla.firefox").mkdir(parents=True)
            (tmp_path / ".var" / "app" / "org.chromium.Chromium").mkdir(parents=True)
            payload = self._fake_widevine_zip_bytes()

            def fake_download(_url, dest):
                Path(dest).write_bytes(payload)
                return True

            with mock.patch.object(Path, "home", return_value=tmp_path), \
                 patch("kyth_shared.thirdparty.fetch_widevine_version", return_value="1.2.3"), \
                 patch("kyth_shared.thirdparty.download_file", side_effect=fake_download):
                self.assertEqual(install_widevine_cdm(), 0)

            firefox_lib = (
                tmp_path / ".var" / "app" / "org.mozilla.firefox" / "config" / "google-chrome"
                / "WidevineCdm" / "1.2.3" / "_platform_specific" / "linux_x64" / "libwidevinecdm.so"
            )
            chromium_manifest = (
                tmp_path / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium"
                / "WidevineCdm" / "1.2.3" / "manifest.json"
            )
            self.assertTrue(firefox_lib.is_file())
            self.assertTrue(chromium_manifest.is_file())


if __name__ == "__main__":
    unittest.main()
