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
from kyth_welcome.services.gaming.compat_data import CompatGame  # noqa: E402


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
        named_cmd = gaming.scx_scheduler_command("scx_rusty")

        self.assertIsInstance(default_cmd, list)
        self.assertIsInstance(named_cmd, list)
        self.assertNotEqual(default_cmd, named_cmd)
        self.assertIn("scx_rusty", named_cmd)

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


def _compat_game(**overrides) -> CompatGame:
    base = dict(
        name="Test Game", anticheat="None", status="proton",
        note="Runs well.", checked="2026-01-01", source="ProtonDB",
        source_url="https://www.protondb.com/app/123",
    )
    base.update(overrides)
    return CompatGame(**base)


class GameRowStatusViewTests(unittest.TestCase):
    """page_gaming_library.py's My Games row status is driven by this
    decision tree — no Qt, so it's testable directly without a display."""

    def test_unmatched_game_is_dim_and_unknown(self):
        view = gaming.game_row_status_view(None)
        self.assertEqual(view.status, "dim")
        self.assertEqual(view.status_text, "Unknown")

    def test_native_and_proton_are_ok(self):
        self.assertEqual(gaming.game_row_status_view(_compat_game(status="native")).status, "ok")
        self.assertEqual(gaming.game_row_status_view(_compat_game(status="proton")).status, "ok")

    def test_tweaks_is_warn(self):
        view = gaming.game_row_status_view(_compat_game(status="tweaks"))
        self.assertEqual(view.status, "warn")
        self.assertEqual(view.status_text, "Tweaks")

    def test_blocked_is_err(self):
        view = gaming.game_row_status_view(_compat_game(status="blocked"))
        self.assertEqual(view.status, "err")
        self.assertEqual(view.status_text, "Blocked")

    def test_summary_includes_note_and_source(self):
        game = _compat_game(note="Needs a tweak.", checked="2026-03-01", source="Wiki")
        view = gaming.game_row_status_view(game)
        self.assertEqual(view.summary, "Needs a tweak. Checked 2026-03-01 via Wiki.")


class LibrarySummaryTextTests(unittest.TestCase):
    def test_empty_library(self):
        text = gaming.library_summary_text([], [])
        self.assertIn("Detected 0 installed item(s)", text)
        self.assertIn("0 matched", text)

    def test_counts_matches_and_groups_by_launcher(self):
        compat_games = [_compat_game(name="Portal 2")]
        games = [
            {"name": "Portal 2", "launcher": "Steam"},
            {"name": "Baldur's Gate 3", "launcher": "Steam"},
            {"name": "Hades", "launcher": "Heroic"},
        ]
        text = gaming.library_summary_text(games, compat_games)
        self.assertIn("Detected 3 installed item(s)", text)
        self.assertIn("1 matched", text)
        self.assertIn("Heroic: 1", text)
        self.assertIn("Steam: 2", text)


class ReadinessResultTextTests(unittest.TestCase):
    def test_working_game_recommends_ludusavi_backup(self):
        text = gaming.readiness_result_text(_compat_game(status="proton"))
        self.assertIn("Works via Proton", text)
        self.assertIn("Back up saves with Ludusavi", text)

    def test_blocked_game_warns_against_migrating_saves(self):
        text = gaming.readiness_result_text(_compat_game(status="blocked", anticheat="EAC"))
        self.assertIn("Blocked by publisher/anti-cheat", text)
        self.assertIn("Do not migrate saves", text)
        self.assertIn("Modding is irrelevant", text)
        self.assertIn("EAC", text)


class GamingReadinessViewTests(unittest.TestCase):
    """page_gaming_setup.py's readiness panel is driven by this decision
    tree — no Qt, so it's testable directly without a display."""

    def _view(self, **overrides):
        base = dict(
            steam_ok=True, pc_ver="10.0-1", vulkan_ok=True, ntsync_ok=True,
            gamescope_ok=True, mangohud_ok=True,
        )
        base.update(overrides)
        return gaming.gaming_readiness_view(**base)

    def test_all_ready_has_no_issues_or_warnings(self):
        view = self._view()
        self.assertEqual(view.ok_count, 6)
        self.assertEqual(view.issue_count, 0)
        self.assertEqual(view.warn_count, 0)
        self.assertEqual(view.score_style, "ready-score")
        self.assertIn("important pieces are in place", view.summary_text)

    def test_missing_proton_is_an_issue(self):
        view = self._view(pc_ver=None)
        self.assertEqual(view.issue_count, 1)
        self.assertEqual(view.score_style, "ready-score-err")
        self.assertIn("need attention", view.summary_text)

    def test_missing_optional_tool_is_a_warning(self):
        view = self._view(gamescope_ok=False)
        self.assertEqual(view.issue_count, 0)
        self.assertEqual(view.warn_count, 1)
        self.assertEqual(view.score_style, "ready-score-warn")
        self.assertIn("close", view.summary_text)

    def test_issue_takes_priority_over_warning_in_score_style(self):
        view = self._view(pc_ver=None, gamescope_ok=False)
        self.assertEqual(view.score_style, "ready-score-err")

    def test_ready_status_prefix_maps_known_and_unknown_statuses(self):
        self.assertEqual(gaming.ready_status_prefix("ok"), "Ready")
        self.assertEqual(gaming.ready_status_prefix("warn"), "Check")
        self.assertEqual(gaming.ready_status_prefix("err"), "Fix")
        self.assertEqual(gaming.ready_status_prefix("dim"), "Optional")
        self.assertEqual(gaming.ready_status_prefix("weird"), "Info")


if __name__ == "__main__":
    unittest.main()
