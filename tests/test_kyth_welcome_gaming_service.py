import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import gaming  # noqa: E402
from kyth_welcome.services.gaming import gamenight  # noqa: E402


class GamingServiceTests(unittest.TestCase):
    def setUp(self):
        gaming.GameNightManager._started = False
        gaming.GameNightManager._inhibit_proc = None
        gaming.GameNightManager._action_procs.clear()

    def tearDown(self):
        gaming.GameNightManager._started = False
        gaming.GameNightManager._inhibit_proc = None
        gaming.GameNightManager._action_procs.clear()

    def test_game_night_cleanup_is_inert_until_started(self):
        with patch.object(gamenight.subprocess, "Popen") as popen:
            gaming._cleanup_game_night()

        popen.assert_not_called()

    def test_game_night_retains_and_reaps_helper_processes(self):
        processes = [MagicMock(), MagicMock(), MagicMock()]
        for proc in processes:
            proc.poll.return_value = None
        with (
            patch.object(gamenight.subprocess, "Popen", side_effect=processes) as popen,
            patch.object(gamenight.shutil, "which", return_value=None),
        ):
            self.assertTrue(gaming.GameNightManager.start())
            self.assertFalse(gaming.GameNightManager.start())
            gaming._cleanup_game_night()

        self.assertEqual(popen.call_count, 3)
        self.assertIn("restore", popen.call_args_list[-1].args[0])
        for proc in processes:
            proc.wait.assert_called_once_with(timeout=15)

    def test_gaming_tools_are_static_tool_definitions(self):
        self.assertGreaterEqual(len(gaming.GAMING_TOOLS), 10)
        for tool in gaming.GAMING_TOOLS:
            self.assertIn("name", tool)
            self.assertIn("desc", tool)
            self.assertTrue(
                any(key in tool for key in ("flatpak", "ujust", "launch")),
                tool,
            )

    def test_command_details_formats_process_output(self):
        result = subprocess.CompletedProcess(
            args=["flatpak", "run", "com.example.App"],
            returncode=1,
            stdout=b"stdout text\n",
            stderr=b"stderr text\n",
        )

        details = gaming.command_details(
            ["flatpak", "run", "com.example.App"],
            result,
            None,
        )

        self.assertIn("Command:", details)
        self.assertIn("flatpak run com.example.App", details)
        self.assertIn("stdout:", details)
        self.assertIn("stdout text", details)
        self.assertIn("stderr:", details)
        self.assertIn("stderr text", details)

    def test_scheduler_command_handles_default_and_named_scheduler(self):
        default_cmd = gaming.scx_scheduler_command("default")
        named_cmd = gaming.scx_scheduler_command("scx_lavd")

        self.assertIsInstance(default_cmd, list)
        self.assertIsInstance(named_cmd, list)
        self.assertNotEqual(default_cmd, named_cmd)
        self.assertIn("scx_lavd", named_cmd)

    def test_command_builders_preserve_runtime_arguments(self):
        opticscaler_cmd = gaming.opticscaler_deploy_command("/games/Test Game")
        lutris_cmd = gaming.lutris_installer_command("/tmp/installer.exe")  # noqa: S108 — fixture string, not a real path opened on disk

        self.assertIn("/games/Test Game", opticscaler_cmd)
        self.assertIn("/tmp/installer.exe", lutris_cmd)  # noqa: S108 — fixture string, not a real path opened on disk
        self.assertTrue(gaming.heroic_epic_launcher_command())
        self.assertTrue(gaming.discord_screenshare_fix_command())
        self.assertTrue(gaming.obs_pipewire_fix_command())

    def test_recommendations_are_data_driven(self):
        epic_game = SimpleNamespace(name="Fortnite", status="blocked")
        competitive_game = SimpleNamespace(
            name="Apex Legends",
            status="playable",
            anticheat="supported",
        )

        self.assertIsInstance(gaming.recommended_launcher_for_game(epic_game), str)
        self.assertIsInstance(
            gaming.recommended_profile_for_game(competitive_game),
            str,
        )
        compat_games = [
            SimpleNamespace(
                name="Known Game",
                status="blocked",
                source_url="https://example.test/app/123",
            ),
        ]

        self.assertEqual(
            gaming.find_compat_game(compat_games, "known game"),
            compat_games[0],
        )
        self.assertIsNone(gaming.find_compat_game(compat_games, "absent title"))


if __name__ == "__main__":
    unittest.main()
