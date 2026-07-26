"""Unit tests for the shared updater module."""
from __future__ import annotations

import hashlib
import io
import pathlib
import sys
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.system.updater import (
    download_file,
    extract_archive,
    fetch_github_latest_release,
    get_github_headers,
    find_release_asset,
    prune_installations,
    release_assets,
    validate_version,
    verify_checksum_file,
)


class UpdaterTests(unittest.TestCase):
    def test_release_assets_normalizes_and_filters_metadata(self) -> None:
        assets = release_assets({"assets": [
            {"name": "tool.tar.xz", "browser_download_url": "https://example/tool"},
            {"name": "missing-url"},
        ]})
        self.assertEqual(len(assets), 1)
        self.assertEqual(find_release_asset(assets, lambda name: name.endswith(".xz")).name, "tool.tar.xz")

    def test_validate_version_rejects_untrusted_value(self) -> None:
        self.assertEqual(validate_version("v1.2.3", r"v[0-9]+\.[0-9]+\.[0-9]+", "tool"), "v1.2.3")
        with self.assertRaisesRegex(ValueError, "Unexpected tool"):
            validate_version("../../tmp", r"v[0-9.]+", "tool")

    def test_prune_installations_keeps_two_newest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            paths = [root / f"tool-{n}" for n in range(3)]
            for index, path in enumerate(paths):
                path.mkdir()
                path.touch()
                path.chmod(0o755)
                import os
                os.utime(path, (index, index))
            removed = prune_installations(root, "tool-*", keep=2)
            self.assertEqual(removed, (paths[0],))
            self.assertFalse(paths[0].exists())

    @mock.patch("pathlib.Path.is_file")
    @mock.patch("pathlib.Path.read_text")
    def test_get_github_headers_with_secret(self, mock_read, mock_is_file) -> None:
        mock_is_file.return_value = True
        mock_read.return_value = "dummy-secret-token\n"
        headers = get_github_headers()
        self.assertEqual(headers["Authorization"], "token dummy-secret-token")

    @mock.patch("urllib.request.urlopen")
    def test_fetch_github_latest_release(self, mock_urlopen) -> None:
        mock_response = mock.Mock()
        mock_response.read.return_value = b'{"tag_name": "v1.2.3", "assets": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        data = fetch_github_latest_release("owner/repo")
        self.assertEqual(data["tag_name"], "v1.2.3")

    @mock.patch("urllib.request.urlopen")
    def test_download_file(self, mock_urlopen) -> None:
        mock_response = io.BytesIO(b"file content")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = pathlib.Path(tmpdir) / "test.txt"
            download_file("https://example.com/test.txt", dest)
            self.assertEqual(dest.read_bytes(), b"file content")

    def test_verify_checksum_file_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = pathlib.Path(tmpdir)
            f1 = td / "f1.txt"
            f1.write_bytes(b"hello")
            h1 = hashlib.sha256(b"hello").hexdigest()

            f2 = td / "f2.txt"
            f2.write_bytes(b"world")
            h2 = hashlib.sha256(b"world").hexdigest()

            checksums = td / "SHA256SUMS"
            checksums.write_text(f"{h1}  f1.txt\n{h2}  *f2.txt\n", encoding="utf-8")

            # Should succeed silently
            self.assertTrue(verify_checksum_file(checksums, td))

    def test_verify_checksum_file_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = pathlib.Path(tmpdir)
            f1 = td / "f1.txt"
            f1.write_bytes(b"hello")
            h1 = hashlib.sha256(b"corrupted").hexdigest()

            checksums = td / "SHA256SUMS"
            checksums.write_text(f"{h1}  f1.txt\n", encoding="utf-8")

            with self.assertRaises(ValueError) as context:
                verify_checksum_file(checksums, td)
            self.assertIn("Checksum mismatch", str(context.exception))

    def test_extract_archive_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = pathlib.Path(tmpdir)
            zip_path = td / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr("test.txt", "inside zip")

            dest = td / "extracted"
            extract_archive(zip_path, dest)
            self.assertEqual((dest / "test.txt").read_text(), "inside zip")

    def test_extract_archive_tar_xz(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = pathlib.Path(tmpdir)
            tar_path = td / "test.tar.xz"
            with tarfile.open(tar_path, "w:xz") as tar:
                # Add a file in tar
                info = tarfile.TarInfo(name="test.txt")
                content = b"inside tar"
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))

            dest = td / "extracted"
            extract_archive(tar_path, dest)
            self.assertEqual((dest / "test.txt").read_text(), "inside tar")

    def test_extract_archive_tar_xz_traversal_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = pathlib.Path(tmpdir)
            tar_path = td / "test.tar.xz"
            with tarfile.open(tar_path, "w:xz") as tar:
                info = tarfile.TarInfo(name="../escape.txt")
                content = b"escape"
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))

            dest = td / "extracted"
            with self.assertRaises(ValueError) as context:
                extract_archive(tar_path, dest)
            self.assertIn("Directory traversal attempt", str(context.exception))


if __name__ == "__main__":
    unittest.main()
