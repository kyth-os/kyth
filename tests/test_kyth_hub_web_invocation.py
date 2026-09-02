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
TAURI_SRC = ROOT / "src" / "kyth-hub-web" / "src-tauri" / "src"
MAIN_RS = (TAURI_SRC / "main.rs").read_text(encoding="utf-8")
MAIN_RS += "\n" + "\n".join(
    path.read_text(encoding="utf-8") for path in sorted((TAURI_SRC / "commands").glob("*.rs"))
)
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

    def test_recipe_launches_are_captured_in_the_hub(self):
        # Recipe actions own a background process and expose its captured
        # result through the Hub status row; no terminal wrapper is part of
        # the user-facing path.
        self.assertIn("command_for", JUST_RS)
        self.assertIn("start_hub_action_job", MAIN_RS)
        self.assertIn("hub_action_status", MAIN_RS)
        self.assertIn("hub_action_status", LIVE_DATA)
        self.assertNotIn("launch_in_terminal", MAIN_RS)
        self.assertNotIn("in_terminal", LIVE_DATA)
        self.assertNotIn("terminal window", SECTION_ACTIONS)

    def test_bootc_commands_use_native_update_jobs(self):
        # These commands return a native Rust-managed job and the frontend
        # waits for the captured result, rather than routing updates through
        # a generic just recipe.
        for command in ("bootc_upgrade", "bootc_rollback", "bootc_switch_branch"):
            body = re.search(rf"fn {command}\([^)]*\)[^{{]*{{(.*?)\n}}", MAIN_RS, re.S)
            self.assertIsNotNone(body, command)
            code = re.sub(r"//.*", "", body.group(1))
            self.assertIn("start_update_job", code, command)
            for claim in ("rolled back", "staged", "completed", "applied"):
                self.assertNotIn(claim, code, f"{command} claims {claim!r} for a spawned window")

    def test_recipe_runner_has_no_terminal_wrapper(self):
        self.assertNotIn("TERMINALS", JUST_RS)
        self.assertNotIn("KEEP_OPEN", JUST_RS)
        self.assertNotIn("konsole", JUST_RS)
        self.assertNotIn("xterm", JUST_RS)
        self.assertIn("SUDO_ASKPASS", MAIN_RS)

    def test_parser_drops_lines_that_are_not_recipes(self):
        # Real `ujust --list` output carries a `[KythOS]` group heading and,
        # for upstream's long distrobox signatures, doc comments on their own
        # line. Both parse as recipes unless dropped.
        self.assertIn("line.starts_with('[') && line.ends_with(']')", JUST_RS)
        self.assertIn("line.starts_with('#')", JUST_RS)

    def test_recipes_use_graphical_askpass_without_a_terminal(self):
        # Plain sudo recipes can use KDE's askpass helper when the Hub gives
        # them no tty, so their output can stay inside the app.
        recipes = list((ROOT / "build_files" / "just" / "kyth").glob("*.just"))
        self.assertTrue(recipes)
        text = "\n".join(path.read_text(encoding="utf-8") for path in recipes)
        self.assertRegex(text, r"(?m)^\s*sudo\b")


SHARED_RS_SOURCE = "\n".join(
    path.read_text(encoding="utf-8") for path in sorted(SHARED_RS.rglob("*.rs"))
)
ALL_RUST_SOURCE = MAIN_RS + "\n" + SHARED_RS_SOURCE

TS_PRIMITIVES = {"string", "boolean", "number", "void", "null", "undefined", "any"}

# Commands whose Rust return type has no struct to check fields against —
# each needs a one-line reason, and test_bridge_exemptions_are_still_real
# below checks the command itself hasn't been renamed out from under it.
UNTYPED_BRIDGE_RETURNS = {
    "ntfs_devices": "returns Vec<serde_json::Value> — an intentionally untyped JSON passthrough",
}


def _balanced_body(text: str, open_brace_index: int) -> str:
    """`text[open_brace_index]` must be '{'. Returns the substring strictly
    between it and its matching close brace, honoring nesting — a plain
    non-greedy `\\{(.*?)\\}` regex breaks on the first nested `{...}` (e.g.
    StarterPack's `apps: { id: string; ... }[]` field)."""
    assert text[open_brace_index] == "{"
    depth = 0
    for index in range(open_brace_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_index + 1 : index]
    raise ValueError("unbalanced braces")


def _find_balanced_body(text: str, header_pattern: str) -> str | None:
    """`header_pattern` must match up to (not including) the opening '{'."""
    match = re.search(header_pattern, text)
    if match is None:
        return None
    return _balanced_body(text, match.end())


def _ts_candidate_type(raw: str) -> str | None:
    """A bare interface/type name this check can look up, or None for a
    primitive, union, or inline object literal type — those have no single
    named interface to check field coverage against, so they're out of
    scope here rather than silently mis-flagged."""
    raw = re.sub(r"\s*\|\s*null$", "", raw.strip())
    raw = re.sub(r"\[\]$", "", raw)
    if re.fullmatch(r"[A-Za-z_]\w*", raw) and raw not in TS_PRIMITIVES:
        return raw
    return None


def _rust_struct_short_name(return_type: str) -> str:
    """Strips Result<_, String>/Vec<_>/Option<_>/crate:: wrappers down to a
    bare struct name, then the last `::` segment of any qualified path
    (kyth_shared::system::foo::Bar -> Bar)."""
    return_type = return_type.strip().rstrip(";").strip()
    changed = True
    while changed:
        changed = False
        for pattern in (r"Result<\s*(.+?)\s*,\s*String\s*>", r"Vec<\s*(.+?)\s*>", r"Option<\s*(.+?)\s*>", r"crate::(.+)"):
            match = re.fullmatch(pattern, return_type)
            if match:
                return_type = match.group(1)
                changed = True
                break
    return return_type.split("::")[-1]


def _ts_top_level_field_names(body: str) -> set[str]:
    # Strip nested `{...}` groups first so a nested object type's own field
    # names (StarterPack.apps[].id) aren't mistaken for the outer
    # interface's fields.
    previous = None
    while previous != body:
        previous = body
        body = re.sub(r"\{[^{}]*\}", "", body)
    return set(re.findall(r"(\w+)\s*\??\s*:", body))


def _rust_field_names(body: str) -> set[str]:
    # `#[serde(rename = "...")]` changes the wire name a field actually
    # serializes as (system::snapshot::SnapshotRow's `row_type` field is
    # `#[serde(rename = "type")]`, matching the TS `type` field) — checked
    # against the Rust identifier alone, that one reads as a false gap.
    names = set()
    for match in re.finditer(
        r'(?:#\[serde\([^\]]*rename\s*=\s*"(\w+)"[^\]]*\)\]\s*)?(?:^|[,\n])\s*(?:pub(?:\(crate\))?\s+)?(\w+)\s*:',
        body,
    ):
        names.add(match.group(1) or match.group(2))
    return names


class BridgeFieldTests(unittest.TestCase):
    """Every `invoke<TsType>("command")` call site in liveData.ts, matched
    by command name (not by guessing a naming convention between the TS and
    Rust names — they often don't share one, e.g. `HardwareBridgeResponse`
    TS vs. `HardwareResponse` Rust) to that command's actual Rust return
    type, and checked field-for-field. Supersedes a two-pair hardcoded
    version of this test that only ever covered JustRecipe/InstallStatus —
    the bug that motivated writing it (JustRecipeResponse silently missing
    a `params` field liveData.ts declared) could just as easily land in any
    of the ~40 other bridge types this now covers automatically; a new one
    needs no enrollment step to be checked, only a documented exemption if
    it genuinely can't be (UNTYPED_BRIDGE_RETURNS)."""

    def _command_ts_types(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for match in re.finditer(r'invoke<([^>]+)>\("([a-zA-Z_]+)"', LIVE_DATA):
            found.setdefault(match.group(2), match.group(1))
        return found

    def test_bridge_structs_carry_every_field_the_frontend_reads(self):
        command_ts_types = self._command_ts_types()
        self.assertGreater(len(command_ts_types), 80, "invoke<...> extraction broke")
        checked = 0
        for command, ts_raw in sorted(command_ts_types.items()):
            if command in UNTYPED_BRIDGE_RETURNS:
                continue
            ts_name = _ts_candidate_type(ts_raw)
            if ts_name is None:
                continue  # primitive / union / inline object literal — out of scope
            with self.subTest(command=command):
                fn_match = re.search(rf"fn {command}\([^)]*\)\s*(?:->\s*([^{{]+))?{{", MAIN_RS)
                self.assertIsNotNone(fn_match, f"no Rust fn {command} found")
                rust_return = (fn_match.group(1) or "()").strip()
                short_name = _rust_struct_short_name(rust_return)
                struct_body = _find_balanced_body(ALL_RUST_SOURCE, rf"struct {re.escape(short_name)}\s*")
                self.assertIsNotNone(
                    struct_body,
                    f"{command} returns {rust_return!r} (-> struct {short_name}) but no such struct exists; "
                    f"add it to UNTYPED_BRIDGE_RETURNS with a reason if this is intentionally untyped",
                )
                iface_body = _find_balanced_body(LIVE_DATA, rf"(?:export\s+)?interface\s+{re.escape(ts_name)}(?:<[^>]*>)?\s*")
                self.assertIsNotNone(iface_body, f"TS interface {ts_name} not found in liveData.ts")
                ts_fields = _ts_top_level_field_names(iface_body)
                self.assertTrue(ts_fields, f"{ts_name} has no fields — extraction broke")
                rust_fields = _rust_field_names(struct_body)
                missing = ts_fields - rust_fields
                self.assertEqual(missing, set(), f"struct {short_name} never sends these fields TS {ts_name} reads")
                checked += 1
        self.assertGreater(checked, 30, "far fewer bridge types were checkable than expected — did extraction break?")

    def test_bridge_exemptions_are_still_real_commands(self):
        command_ts_types = self._command_ts_types()
        for command in UNTYPED_BRIDGE_RETURNS:
            self.assertIn(command, command_ts_types, f"{command} is exempted but is no longer invoked from liveData.ts")

    def test_compatibility_matrix_bridge_is_registered_and_consumed(self):
        # The old Hub's title matrix is image-owned JSON. A typed Tauri
        # command keeps the React and Qt surfaces on the same data source;
        # an unregistered command would silently leave the page in Preview.
        self.assertIn("fn compatibility_games()", MAIN_RS)
        self.assertIn("compatibility_games", MAIN_RS)
        self.assertIn('invoke<CompatibilityGame[]>("compatibility_games")', LIVE_DATA)
        component = (HUB_WEB / "components" / "CompatibilitySection.tsx").read_text(encoding="utf-8")
        self.assertIn("fetchCompatibilityGames", component)
        self.assertIn("gameFilter", component)
        self.assertIn("gameQuery", component)

    def test_performance_section_consumes_live_session_telemetry(self):
        component = (HUB_WEB / "components" / "PerformanceSection.tsx").read_text(encoding="utf-8")
        self.assertIn("fetchTelemetryRecent(8)", component)
        self.assertIn("Recent gaming sessions", component)
        self.assertIn("session.avg_fps", component)

    def test_performance_and_app_store_expose_advanced_frontend_paths(self):
        performance = (HUB_WEB / "components" / "PerformanceSection.tsx").read_text(encoding="utf-8")
        app_store = (HUB_WEB / "components" / "AppStoreSection.tsx").read_text(encoding="utf-8")
        for command in ("ujust gamescope -- %command%", "ujust game-hdr -- %command%", "ujust low-latency -- %command%", "ujust scx status"):
            self.assertIn(command, performance)
        # export-kali-apps used to be a RecipeButton here; the Security tab's
        # KaliCard now runs the same export through the live kali_export
        # bridge command instead (see BridgeFieldTests / commands/security.rs),
        # so it's no longer a static recipe button to check for.
        for recipe in ("hdr-per-game", "enable-bpftune", "disable-bpftune", "setup-kyth-dev-box", "ai-dev-status", "ai-dev-setup", "setup-waydroid", "remove-waydroid"):
            self.assertIn(f'recipe="{recipe}"', performance + app_store)

    def test_network_share_and_vpn_parity_bridges_are_registered(self):
        shares = (HUB_WEB / "components" / "NetworkSharesSection.tsx").read_text(encoding="utf-8")
        vpn = (HUB_WEB / "components" / "VpnSection.tsx").read_text(encoding="utf-8")
        self.assertIn("smb_configured_shares", MAIN_RS)
        self.assertIn("smb_save_configured_share", MAIN_RS)
        self.assertIn("network_share_add", MAIN_RS)
        self.assertIn("addNetworkShare", LIVE_DATA)
        self.assertIn("Credentials go only", shares)
        self.assertIn("open_vpn_app", MAIN_RS)
        self.assertIn("openVpnApp", LIVE_DATA)
        self.assertIn("vpn_saved_profile", MAIN_RS)
        self.assertIn("fetchVpnSavedProfile", LIVE_DATA)
        self.assertIn("Open full VPN connection", vpn)
        self.assertIn("Saved profile", vpn)

    def test_move_in_readiness_and_full_workflow_bridges_are_registered(self):
        move_files = (HUB_WEB / "components" / "MoveFilesSection.tsx").read_text(encoding="utf-8")
        cloud = (HUB_WEB / "components" / "CloudStorageSection.tsx").read_text(encoding="utf-8")
        shares = (HUB_WEB / "components" / "NetworkSharesSection.tsx").read_text(encoding="utf-8")
        for command in ("migration_readiness", "open_cloud_storage_app", "open_move_files_app", "open_network_shares_app"):
            self.assertIn(command, MAIN_RS)
        for wrapper in ("fetchMigrationReadiness", "fetchCloudSyncRemotes", "openCloudStorageApp", "openMoveFilesApp", "openNetworkSharesApp"):
            self.assertIn(wrapper, LIVE_DATA)
        self.assertIn("cloud_sync_remotes", MAIN_RS)
        self.assertIn("Migration readiness", move_files)
        self.assertIn("Open full Cloud Storage", cloud)
        self.assertIn("Saved sync folders", cloud)
        self.assertIn("Open full share controls", shares)

    def test_parity_items_4_to_10_have_native_surface_and_bridge(self):
        guardian = (HUB_WEB / "components" / "GuardianSection.tsx").read_text(encoding="utf-8")
        performance = (HUB_WEB / "components" / "PerformanceSection.tsx").read_text(encoding="utf-8")
        work = (HUB_WEB / "components" / "WorkSetupSection.tsx").read_text(encoding="utf-8")
        repair = (HUB_WEB / "components" / "RepairSection.tsx").read_text(encoding="utf-8")
        cloud = (HUB_WEB / "components" / "CloudStorageSection.tsx").read_text(encoding="utf-8")
        dashboard = (HUB_WEB / "pages" / "Dashboard.tsx").read_text(encoding="utf-8")
        history = (HUB_WEB / "components" / "GuardianHistoryCard.tsx").read_text(encoding="utf-8")
        self.assertIn("Confirm & run", history)
        self.assertIn("Dismiss", history)
        self.assertIn("aria-expanded", history)
        self.assertIn("dismissGuardianRecommendation", dashboard)
        self.assertIn("aria-expanded", guardian)
        self.assertIn("setScxScheduler", performance)
        self.assertIn("gaming_perf_status", MAIN_RS)
        for wrapper in ("openM365App", "createM365Shortcuts", "fetchPstFiles", "convertPst", "startFocusSession", "stopFocusSession"):
            self.assertIn(wrapper, LIVE_DATA)
        for command in ("open_m365_app", "create_m365_shortcuts", "pst_files", "convert_pst", "focus_start", "focus_stop"):
            self.assertIn(command, MAIN_RS)
        self.assertIn("Pika Backup", repair)
        self.assertIn("runCloudSync", cloud)
        self.assertIn("cloud_sync_now", MAIN_RS)


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
        expected = python_recipe_commands()
        expected["storage.maint"] = ["/usr/bin/kyth-btrfs-maint"]
        self.assertEqual(rust_recipe_commands(), expected)

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
