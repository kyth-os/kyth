"""Tests for actions.py's widget-aware helpers (needs Qt)."""
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

try:
    from kyth_welcome.actions import _open_chromium_webapp
except ImportError:
    raise unittest.SkipTest("PyQt6/PySide6 required by kyth_welcome.actions -> qt imports") from None


class OpenChromiumWebappTests(unittest.TestCase):
    def test_launches_found_browser(self):
        owner = MagicMock()
        with patch("kyth_welcome.actions._chromium_app_window_cmd", return_value=(["firefox", "--new-window", "https://x"], "firefox")), \
             patch("kyth_welcome.actions.popen") as mock_popen, \
             patch("kyth_welcome.actions.QMessageBox") as mock_box:
            _open_chromium_webapp(owner, "https://x")
        mock_popen.assert_called_once_with(["firefox", "--new-window", "https://x"])
        mock_box.warning.assert_not_called()

    def test_warns_when_no_browser_found(self):
        owner = MagicMock()
        with patch("kyth_welcome.actions._chromium_app_window_cmd", return_value=None), \
             patch("kyth_welcome.actions.popen") as mock_popen, \
             patch("kyth_welcome.actions.QMessageBox") as mock_box:
            _open_chromium_webapp(owner, "https://x", extra_hint="Try the Flatpak tab.")
        mock_popen.assert_not_called()
        args = mock_box.warning.call_args[0]
        self.assertEqual(args[0], owner)
        self.assertEqual(args[1], "No browser found")
        self.assertIn("Try the Flatpak tab.", args[2])

    def test_warns_on_launch_failure(self):
        owner = MagicMock()
        with patch("kyth_welcome.actions._chromium_app_window_cmd", return_value=(["firefox"], "firefox")), \
             patch("kyth_welcome.actions.popen", side_effect=OSError("nope")), \
             patch("kyth_welcome.actions.QMessageBox") as mock_box:
            _open_chromium_webapp(owner, "https://x")
        args = mock_box.warning.call_args[0]
        self.assertEqual(args[1], "Could not open web app")
        self.assertIn("nope", args[2])


if __name__ == "__main__":
    unittest.main()
