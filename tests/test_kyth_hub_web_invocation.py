"""The React Hub must invoke `just` the way the installed system needs.

Three commits hardened how `just --list` output is *parsed*; none covered
how `just` is *invoked*, and that is where the bug was. Bare `just` resolves
a justfile by walking up from the process working directory. The Hub shell's
working directory is whatever the .desktop launcher gives it, so on a real
install `just --list` returned "error: no justfile found" and every recipe
button spawned a process that exited immediately — while the UI reported it
as running. Kyth's recipes live in ublue's justfile, which is what `ujust`
exists to point `just` at:

    JUST_JUSTFILE="/usr/share/ublue-os/justfile" /usr/bin/just "${@}"

The same class of gap sat between the bridge and the frontend: liveData.ts
declared a `params` field that `JustRecipeResponse` never serialized, so the
"do not button a parameterized recipe" guard read `undefined` and buttoned
every row. A TS interface is not a contract with Rust, so it is checked here.
"""
from __future__ import annotations

import ast
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHARED_RS = ROOT / "src" / "kyth-shared-rs" / "src"
HUB_WEB = ROOT / "src" / "kyth-hub-web" / "src"
JUST_RS = (SHARED_RS / "system" / "just.rs").read_text(encoding="utf-8")
GUARDIAN_RS = (SHARED_RS / "guardian.rs").read_text(encoding="utf-8")
MAIN_RS = (ROOT / "src" / "kyth-hub-web" / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
LIVE_DATA = (HUB_WEB / "services" / "liveData.ts").read_text(encoding="utf-8")
SECTION_ACTIONS = (HUB_WEB / "components" / "SectionActions.tsx").read_text(encoding="utf-8")
GUARDIAN_SECTION = (HUB_WEB / "components" / "GuardianSection.tsx").read_text(encoding="utf-8")
UJUST_RECIPES = (ROOT / "build_files" / "scripts" / "branding" / "31-ujust-recipes.sh").read_text(encoding="utf-8")
GUARDIAN_PY = ROOT / "build_files" / "kyth_shared" / "kyth_shared" / "guardian.py"
GUARDIAN_ACTIONS_PY = ROOT / "build_files" / "kyth_shared" / "kyth_shared" / "guardian_actions.py"

UBLUE_JUSTFILE = "/usr/share/ublue-os/justfile"


def python_recipe_commands() -> dict[str, list[str]]:
    """The `command` tuple of every `Recipe(...)` in guardian.py, by id."""
    commands: dict[str, list[str]] = {}
    for node in ast.walk(ast.parse(GUARDIAN_PY.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call) or getattr(node.func, "id", "") != "Recipe":
            continue
        argv = node.args[3]
        commands[node.args[0].value] = (
            [element.value for element in argv.elts] if isinstance(argv, ast.Tuple) else []
        )
    return commands


def rust_recipe_commands() -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {}
    for entry in re.finditer(r'Recipe \{ id: "([^"]+)".*?command: &\[([^\]]*)\]', GUARDIAN_RS):
        commands[entry.group(1)] = re.findall(r'"([^"]*)"', entry.group(2))
    return commands


class JustInvocationTests(unittest.TestCase):
    def test_just_runs_against_the_justfile_ujust_points_at(self):
        self.assertIn("JUST_JUSTFILE", JUST_RS)
        self.assertIn(UBLUE_JUSTFILE, JUST_RS)

    def test_branding_installs_the_recipes_into_that_same_justfile(self):
        # If the build ever moves the import target, the Hub's constant has
        # to move with it — this is the only thing that ties the two files.
        self.assertRegex(UJUST_RECIPES, rf">>{re.escape(UBLUE_JUSTFILE)}\b")
        self.assertIn("cp /ctx/just/kyth.just", UJUST_RECIPES)

    def test_nothing_spawns_just_without_that_resolution(self):
        # One module owns the invocation; a raw Command::new("just") anywhere
        # else is the bug this file exists for.
        offenders = [
            path.relative_to(ROOT)
            for path in list(SHARED_RS.rglob("*.rs"))
            + list((ROOT / "src" / "kyth-hub-web" / "src-tauri" / "src").rglob("*.rs"))
            if path.name != "just.rs" and 'Command::new("just")' in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [], f"spawn just through system::just instead: {offenders}")

    def test_launch_reports_a_terminal_only_when_one_was_used(self):
        # The recipes use sudo, never pkexec, so without a tty they cannot
        # prompt — the Hub must not claim a window it did not open.
        self.assertIn("in_terminal", MAIN_RS)
        self.assertIn("in_terminal", LIVE_DATA)
        self.assertIn("launch.in_terminal", SECTION_ACTIONS)

    def test_bootc_commands_do_not_claim_a_finished_change(self):
        # `just_launch` returns when the terminal window opens: the recipe
        # has not run and its sudo prompt is unanswered. These three used to
        # return "rolled back — reboot to apply" and "switch to X staged —
        # reboot to activate" at that moment, which is the same "reports
        # success for something that did nothing" bug in prose form.
        for command in ("bootc_upgrade", "bootc_rollback", "bootc_switch_branch"):
            body = re.search(rf"fn {command}\([^)]*\)[^{{]*{{(.*?)\n}}", MAIN_RS, re.S)
            self.assertIsNotNone(body, command)
            code = re.sub(r"//.*", "", body.group(1))
            self.assertIn("launch_in_terminal", code, command)
            for claim in ("rolled back", "staged", "completed", "applied"):
                self.assertNotIn(claim, code, f"{command} claims {claim!r} for a spawned window")

    def test_launch_wording_describes_the_window_not_the_result(self):
        # launch_in_terminal is the one place that wording lives, so it has
        # to talk about the terminal and the password prompt — and refuse
        # before spawning when there is no terminal, rather than starting a
        # process that is doomed at the sudo prompt and then explaining it.
        body = re.search(r"fn launch_in_terminal\(.*?\n}", MAIN_RS, re.S)
        self.assertIsNotNone(body)
        self.assertIn("terminal window", body.group(0))
        self.assertIn("password prompt", body.group(0))
        self.assertIn("no terminal emulator is installed", body.group(0))
        guard = body.group(0).index("terminal_available")
        self.assertLess(guard, body.group(0).index("just_launch"), "spawns before checking for a terminal")

    def test_parser_drops_lines_that_are_not_recipes(self):
        # Real `ujust --list` output carries a `[KythOS]` group heading and,
        # for upstream's long distrobox signatures, doc comments on their own
        # line. Both parse as recipes unless dropped.
        self.assertIn("line.starts_with('[') && line.ends_with(']')", JUST_RS)
        self.assertIn("line.starts_with('#')", JUST_RS)

    def test_recipes_use_sudo_so_a_terminal_is_required(self):
        # The premise of the terminal wrapper. If recipes ever move to
        # pkexec, the graphical agent can prompt and this can be revisited.
        recipes = list((ROOT / "build_files" / "just" / "kyth").glob("*.just"))
        self.assertTrue(recipes)
        text = "\n".join(path.read_text(encoding="utf-8") for path in recipes)
        self.assertRegex(text, r"(?m)^\s*sudo\b")


class BridgeFieldTests(unittest.TestCase):
    # Frontend interface -> the Rust struct that has to serialize it.
    BRIDGE_TYPES = {"JustRecipe": "JustRecipeResponse", "JustLaunch": "JustRunResponse"}

    def test_bridge_structs_carry_every_field_the_frontend_reads(self):
        for ts_name, rust_name in self.BRIDGE_TYPES.items():
            with self.subTest(interface=ts_name):
                declared = re.search(rf"export interface {ts_name} \{{(.*?)\}}", LIVE_DATA, re.S)
                self.assertIsNotNone(declared, f"{ts_name} not found in liveData.ts")
                fields = set(re.findall(r"(\w+)\s*:", declared.group(1)))
                self.assertTrue(fields)
                struct = re.search(rf"struct {rust_name} \{{(.*?)\n\}}", MAIN_RS, re.S)
                self.assertIsNotNone(struct, f"{rust_name} not found in main.rs")
                served = set(re.findall(r"(?m)^\s+(\w+):", struct.group(1)))
                self.assertEqual(fields - served, set(), f"{rust_name} never sends these")


class GuardianExecutionTests(unittest.TestCase):
    def test_guardian_execute_does_not_go_through_just(self):
        body = re.search(r"fn guardian_execute_recipe\(.*?\n\}", MAIN_RS, re.S)
        self.assertIsNotNone(body)
        # Guardian ids are dotted and are not just recipes; spawning one
        # succeeded and ran nothing, which the Hub reported as "launched".
        # Comments stripped: the body explains that history in prose.
        code = re.sub(r"//.*", "", body.group(0))
        self.assertNotIn("just_run", code)
        self.assertIn("execute_recipe", code)

    def test_advisory_recommendations_get_no_run_button(self):
        # The backend refuses them, so a button there could only ever report
        # "recipe is not eligible for automatic execution".
        self.assertIn('RUNNABLE_RISK = new Set(["safe", "confirm"])', GUARDIAN_SECTION)
        self.assertIn("RUNNABLE_RISK.has(item.risk) && (", GUARDIAN_SECTION)

    def test_rust_recipe_commands_match_the_python_table(self):
        self.assertEqual(rust_recipe_commands(), python_recipe_commands())

    def test_advisory_recipes_have_no_command_on_either_side(self):
        commands = python_recipe_commands()
        advisory = re.findall(r'Recipe \{ id: "([^"]+)".*?risk: "advisory"', GUARDIAN_RS)
        self.assertTrue(advisory)
        for recipe_id in advisory:
            self.assertEqual(commands[recipe_id], [], recipe_id)

    def test_executor_backed_recipes_are_all_held_back(self):
        # guardian_actions.py does the real work for these; their command
        # tuple alone is a read, or half a toggle. Rust runs the tuple, so
        # every executor id has to be excluded until the executor is ported.
        executors = re.search(
            r"ACTION_EXECUTORS: dict\[str, Callable\[\[Run\], tuple\[bool, str\]\]\] = \{(.*?)\}",
            GUARDIAN_ACTIONS_PY.read_text(encoding="utf-8"),
            re.S,
        )
        self.assertIsNotNone(executors)
        expected = set(re.findall(r'"([^"]+)":', executors.group(1)))
        held_back = re.search(r"const EXECUTOR_ONLY: &\[&str\] = &\[(.*?)\];", GUARDIAN_RS, re.S)
        self.assertIsNotNone(held_back)
        self.assertEqual(set(re.findall(r'"([^"]+)"', held_back.group(1))), expected)


if __name__ == "__main__":
    unittest.main()
