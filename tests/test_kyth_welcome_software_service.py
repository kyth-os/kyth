import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import software  # noqa: E402


class SoftwareServiceTests(unittest.TestCase):
    def test_installed_flatpak_ids_returns_frozenset(self):
        stdout = "com.valvesoftware.Steam\nnet.lutris.Lutris\n"
        cmd_result = MagicMock(returncode=0, stdout=stdout)
        with patch("kyth_welcome.services.software._run_command", return_value=cmd_result):
            ids = software._installed_flatpak_ids()

        self.assertIsInstance(ids, frozenset)
        self.assertIn("com.valvesoftware.Steam", ids)
        self.assertIn("net.lutris.Lutris", ids)

    def test_list_installed_flatpak_apps_parses_columns(self):
        stdout = "com.valvesoftware.Steam\tSteam\tflathub\tsystem\n"
        proc_result = MagicMock(returncode=0, stdout=stdout)
        with (
            patch("shutil.which", return_value="/usr/bin/flatpak"),
            patch("subprocess.run", return_value=proc_result),
        ):
            apps = software.list_installed_flatpak_apps()

        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["app_id"], "com.valvesoftware.Steam")
        self.assertEqual(apps[0]["name"], "Steam")
        self.assertEqual(apps[0]["origin"], "flathub")

    def test_chromium_app_window_id_generates_correct_format(self):
        url = "https://web.whatsapp.com/"
        window_id = software._chromium_app_window_id("brave-browser", url)
        self.assertEqual(window_id, "brave-web.whatsapp.com__-Default")

    def test_chromium_app_window_cmd_finds_available_browser(self):
        with (
            patch("shutil.which", side_effect=lambda b: "/usr/bin/brave-browser" if b == "brave-browser" else None),
        ):
            cmd, app_id = software._chromium_app_window_cmd("https://example.com")

        self.assertEqual(cmd[0], "brave-browser")
        self.assertEqual(cmd[1], "--app=https://example.com")
        self.assertIn("brave-example.com__-Default", app_id)

    def test_flatpak_install_shell_command_quotes_appid(self):
        cmd = software.flatpak_install_shell_command("com.example.App", extra_cmd="echo done")
        self.assertIn("flatpak remote-add", cmd)
        self.assertIn("flatpak install -y --or-update flathub com.example.App", cmd)
        self.assertIn("&& echo done", cmd)

    def test_first_run_app_setup_state_ready_when_no_missing(self):
        with (
            patch("kyth_welcome.services.software._IS_LIVE", False),
            patch("kyth_welcome.services.software._is_flatpak_installed", return_value=True),
        ):
            state, msg, missing = software._first_run_app_setup_state()

        self.assertEqual(state, "ready")
        self.assertEqual(missing, [])

    def test_davinci_zip_candidates_finds_matches(self):
        with (
            patch("kyth_welcome.services.software._davinci_download_dir", return_value="/tmp/downloads"),  # noqa: S108 — test path mock
            patch("os.path.isdir", return_value=True),
            patch("glob.glob", side_effect=lambda p: ["/tmp/downloads/DaVinci_Resolve_19_Linux.zip"] if "DaVinci" in p else []),  # noqa: S108 — test path mock
            patch("os.path.isfile", return_value=True),
            patch("os.path.getmtime", return_value=100.0),
        ):
            candidates = software._davinci_zip_candidates()

        self.assertEqual(candidates, ["/tmp/downloads/DaVinci_Resolve_19_Linux.zip"])  # noqa: S108 — test path assertion


if __name__ == "__main__":
    unittest.main()
