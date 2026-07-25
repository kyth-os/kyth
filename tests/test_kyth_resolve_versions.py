"""Unit tests for resolve-versions.py."""
from __future__ import annotations

import io
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "scripts"))

# Import main and subcommands from resolve-versions
import importlib.util
spec = importlib.util.spec_from_file_location(
    "resolve_versions",
    str(ROOT / "build_files" / "scripts" / "resolve-versions.py")
)
resolve_versions = importlib.util.module_from_spec(spec)
sys.modules["resolve_versions"] = resolve_versions
spec.loader.exec_module(resolve_versions)


class ResolveVersionsTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_cmd_proton_cachyos(self, mock_stdout, mock_urlopen) -> None:
        mock_response = mock.Mock()
        mock_response.read.return_value = b'{"tag_name": "cachyos-11.0-20260602-slr"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        ret = resolve_versions.cmd_proton_cachyos()
        self.assertEqual(ret, 0)
        self.assertEqual(mock_stdout.getvalue().strip(), "cachyos-11.0-20260602-slr")

    @mock.patch("urllib.request.urlopen")
    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_cmd_thirdparty_versions(self, mock_stdout, mock_urlopen) -> None:
        mock_response = mock.Mock()
        mock_response.read.return_value = b'{"tag_name": "v1.2.3"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        ret = resolve_versions.cmd_thirdparty_versions()
        self.assertEqual(ret, 0)
        self.assertEqual(mock_stdout.getvalue().strip(), "v1.2.3")

    @mock.patch("urllib.request.urlopen")
    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_cmd_cachyos_kernel_success(self, mock_stdout, mock_urlopen) -> None:
        mock_response = mock.Mock()
        mock_response.read.return_value = b'{"builds": {"latest_succeeded": {"source_package": {"version": "6.9.3", "release": "1"}}}}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        ret = resolve_versions.cmd_cachyos_kernel()
        self.assertEqual(ret, 0)
        self.assertEqual(mock_stdout.getvalue().strip(), "6.9.3-1")

    @mock.patch("urllib.request.urlopen")
    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_cmd_cachyos_kernel_failure_fallback(self, mock_stdout, mock_urlopen) -> None:
        mock_urlopen.side_effect = Exception("API Down")

        ret = resolve_versions.cmd_cachyos_kernel()
        self.assertEqual(ret, 0)
        import datetime
        expected = datetime.date.today().isoformat()
        self.assertEqual(mock_stdout.getvalue().strip(), expected)


if __name__ == "__main__":
    unittest.main()
