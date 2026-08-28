"""React Hub mutating actions must stay reachable and real.

The Phase 2 commits landed bootc upgrade/rollback/switch and Guardian
execute as Tauri commands with liveData.ts wrappers, but no component ever
called them — the backend was complete and the UI never followed, so
Updates/Channels/Guardian were read-only in the React Hub while the Qt Hub
could act. `bootc_switch_branch` was worse than unreachable: it validated
its input and returned "switch queued" prose without calling anything.

Nothing in the invoke chain catches either failure — an unused export is
valid TS, and a command that returns a success string looks successful.
These are static checks over the shipped sources for that reason.
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HUB_WEB = ROOT / "src" / "kyth-hub-web" / "src"
MAIN_RS = (ROOT / "src" / "kyth-hub-web" / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
LIVE_DATA = (HUB_WEB / "services" / "liveData.ts").read_text(encoding="utf-8")

# The mutating wrappers, and the section each one belongs to.
MUTATING_WRAPPERS = {
    "invokeBootcUpgrade": "UpdatesSection.tsx",
    "invokeBootcRollback": "UpdatesSection.tsx",
    "invokeBootcSwitchBranch": "ChannelsSection.tsx",
    "invokeGuardianExecute": "GuardianSection.tsx",
}


def _ui_sources() -> dict[str, str]:
    sources = {}
    for sub in ("components", "pages"):
        for path in (HUB_WEB / sub).rglob("*.tsx"):
            sources[path.name] = path.read_text(encoding="utf-8")
    return sources


class HubWebActionTests(unittest.TestCase):
    def test_every_mutating_wrapper_is_reachable_from_the_ui(self):
        sources = _ui_sources()
        for wrapper, expected_file in MUTATING_WRAPPERS.items():
            consumers = [name for name, text in sources.items() if re.search(rf"\b{wrapper}\b", text)]
            self.assertTrue(
                consumers,
                f"{wrapper} has no component consumer — the action is unreachable in the UI",
            )
            self.assertIn(expected_file, consumers, f"{wrapper} should be wired into {expected_file}")

    def test_switch_branch_actually_runs_the_recipe(self):
        body = re.search(
            r"fn bootc_switch_branch\(.*?\n\}", MAIN_RS, re.S
        )
        self.assertIsNotNone(body, "bootc_switch_branch not found")
        text = body.group(0)
        # It must delegate, not just format a reassuring string.
        self.assertIn("switch-channel", text)
        self.assertIn("Command::new", text)
        self.assertIn("switch_channel_arg", text)
        self.assertNotIn("queued — run bootc switch via polkit terminal", text)

    def test_switch_branch_does_not_pass_caller_input_to_argv(self):
        body = re.search(r"fn bootc_switch_branch\(.*?\n\}", MAIN_RS, re.S).group(0)
        # The allowlist returns a fixed literal; passing `branch` straight
        # to .arg() would put user-controlled text on the command line.
        self.assertNotRegex(body, r"\.arg\(\s*&?branch")

    def test_guardian_execute_is_gated_on_pending_recommendations(self):
        body = re.search(r"fn guardian_execute_recipe\(.*?\n\}", MAIN_RS, re.S)
        self.assertIsNotNone(body, "guardian_execute_recipe not found")
        self.assertIn("is_pending_recipe", body.group(0))

    def test_recipe_id_reaches_the_frontend_so_a_fix_can_be_run(self):
        # Without recipe_id in the snapshot response there is no id to pass
        # back to guardian_execute_recipe, so no "Run fix" button can exist.
        pending_struct = re.search(r"struct GuardianPendingResponse \{.*?\n\}", MAIN_RS, re.S)
        self.assertIsNotNone(pending_struct)
        self.assertIn("recipe_id", pending_struct.group(0))
        self.assertIn("recipe_id: string;", LIVE_DATA)
        self.assertIn("recipeId: string;", LIVE_DATA)
        self.assertIn("recipeId: item.recipe_id", LIVE_DATA)


if __name__ == "__main__":
    unittest.main()
