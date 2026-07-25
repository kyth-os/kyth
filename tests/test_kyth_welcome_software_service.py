import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import (  # noqa: E402
    browser_apps,
    creator,
    first_run,
    flatpak,
    software,
)


class SoftwareServiceTests(unittest.TestCase):
    def test_installed_flatpak_ids_returns_frozenset(self):
        stdout = "com.valvesoftware.Steam\nnet.lutris.Lutris\n"
        cmd_result = MagicMock(returncode=0, stdout=stdout)
        with (
            patch("kyth_welcome.services.flatpak._probe_cached", side_effect=lambda _key, _ttl, fetch: fetch()),
            patch("kyth_welcome.services.flatpak._run_command", return_value=cmd_result),
        ):
            ids = flatpak.installed_app_ids()

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
            apps = flatpak.list_installed_apps()

        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["app_id"], "com.valvesoftware.Steam")
        self.assertEqual(apps[0]["name"], "Steam")
        self.assertEqual(apps[0]["origin"], "flathub")

    def test_chromium_app_window_id_generates_correct_format(self):
        url = "https://web.whatsapp.com/"
        window_id = browser_apps.chromium_app_window_id("brave-browser", url)
        self.assertEqual(window_id, "brave-web.whatsapp.com__-Default")

    def test_chromium_app_window_cmd_finds_available_browser(self):
        with (
            patch("shutil.which", side_effect=lambda b: "/usr/bin/brave-browser" if b == "brave-browser" else None),
        ):
            cmd, app_id = browser_apps.chromium_app_window_command("https://example.com")

        self.assertEqual(cmd[0], "brave-browser")
        self.assertEqual(cmd[1], "--app=https://example.com")
        self.assertIn("brave-example.com__-Default", app_id)

    def test_flatpak_install_shell_command_quotes_appid(self):
        cmd = flatpak.install_shell_command("com.example.App", extra_cmd="echo done")
        self.assertIn("flatpak remote-add", cmd)
        self.assertIn("flatpak install -y --or-update flathub com.example.App", cmd)
        self.assertIn("&& echo done", cmd)

    def test_first_run_app_setup_state_ready_when_no_missing(self):
        with (
            patch("kyth_welcome.services.first_run._is_live_session", return_value=False),
            patch("kyth_welcome.services.first_run.is_installed", return_value=True),
        ):
            state, _msg, missing = first_run.app_setup_state()

        self.assertEqual(state, "ready")
        self.assertEqual(missing, [])

    def test_first_run_ignores_malformed_status_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            status_path = Path(tmp) / "first-run-apps.status"
            status_path.write_text("state='unterminated\n", encoding="utf-8")
            with (
                patch("kyth_welcome.services.first_run._is_live_session", return_value=False),
                patch("kyth_welcome.services.first_run.is_installed", return_value=False),
                patch("kyth_welcome.services.first_run.os.path.expanduser", return_value=str(status_path)),
                patch(
                    "kyth_welcome.services.first_run._run_command",
                    return_value=MagicMock(stdout="inactive"),
                ),
            ):
                state, _msg, missing = first_run.app_setup_state()

        self.assertEqual(state, "pending")
        self.assertTrue(missing)

    def test_davinci_zip_candidates_finds_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            older = Path(tmp) / "DaVinci_Resolve_19_Linux.zip"
            newer = Path(tmp) / "DaVinci_Resolve_20_Linux.zip"
            older.touch()
            newer.touch()
            os.utime(older, (100, 100))
            os.utime(newer, (200, 200))
            with patch("kyth_welcome.services.creator.davinci_download_dir", return_value=tmp):
                candidates = creator.davinci_zip_candidates()

        self.assertEqual(candidates, [str(newer), str(older)])

    def test_software_facade_uses_split_service_implementations(self):
        self.assertIs(software._installed_flatpak_ids, flatpak.installed_app_ids)
        self.assertIs(
            software._chromium_app_window_cmd,
            browser_apps.chromium_app_window_command,
        )
        self.assertIs(software._davinci_zip_candidates, creator.davinci_zip_candidates)
        self.assertIs(software._first_run_app_setup_state, first_run.app_setup_state)


if __name__ == "__main__":
    unittest.main()
