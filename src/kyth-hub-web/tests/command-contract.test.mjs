import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const service = await readFile(resolve(root, "src/services/liveData.ts"), "utf8");
const dashboard = await readFile(resolve(root, "src/pages/Dashboard.tsx"), "utf8");
const guardianHistory = await readFile(resolve(root, "src/components/GuardianHistoryCard.tsx"), "utf8");
const updates = await readFile(resolve(root, "src/components/UpdatesSection.tsx"), "utf8");
const updatesOverview = await readFile(resolve(root, "src/components/UpdatesOverview.tsx"), "utf8");
const guardian = await readFile(resolve(root, "src/components/GuardianSection.tsx"), "utf8");
const hardware = await readFile(resolve(root, "src/components/HardwareSection.tsx"), "utf8");
const apps = await readFile(resolve(root, "src/components/AppStoreSection.tsx"), "utf8");
const gaming = await readFile(resolve(root, "src/components/GamingSection.tsx"), "utf8");
const actions = await readFile(resolve(root, "src/components/SectionActions.tsx"), "utf8");
const rust = await readFile(resolve(root, "src-tauri/src/main.rs"), "utf8");
const updatesRust = await readFile(resolve(root, "src-tauri/src/commands/updates.rs"), "utf8");
const parity = await readFile(resolve(root, "PARITY.md"), "utf8");

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true, recursive: true });
  return entries
    .filter((entry) => entry.isFile() && /\.(?:ts|tsx)$/.test(entry.name))
    .map((entry) => resolve(entry.parentPath ?? directory, entry.name));
}

const dashboardWrappers = [
  "fetchGuardianSnapshot",
  "fetchUpdateChannel",
  "fetchGpuName",
  "fetchStorageFree",
  "fetchUserName",
  "fetchBootRuntimeChecks",
  "fetchRecoveryStatus",
];

const updateWrappers = [
  "fetchBootcSnapshot",
  "fetchUpdateStatus",
  "fetchPendingUpdatesSummary",
  "fetchUpdaterAvailable",
  "fetchUpdateHealth",
  "fetchCollectAvailability",
  "fetchUpdateAvailabilityView",
  "invokeBootcUpgrade",
  "invokeBootcRollback",
  "invokeApplyStaged",
];

const rustCommands = [
  "guardian_snapshot",
  "probe_backend",
  "hardware_snapshot",
  "storage_snapshot",
  "current_user_name",
  "boot_runtime_checks",
  "recovery_status",
  "update_status",
  "pending_updates_summary",
  "updater_available",
  "collect_availability",
  "update_availability_view",
  "current_update_channel",
  "bootc_upgrade",
  "bootc_rollback",
  "apply_staged",
  "update_job_status",
  "update_health",
  "update_watcher_status",
  "set_update_watcher_enabled",
  "check_for_updates_now",
  "defer_update_watcher",
  "just_run",
  "just_run_status",
];

test("Dashboard wrappers are present and used by the page", () => {
  for (const wrapper of dashboardWrappers) {
    assert.match(service, new RegExp(`export async function ${wrapper}\\b`), wrapper);
    assert.match(dashboard, new RegExp(`\\b${wrapper}\\b`), wrapper);
  }
});

test("Updates wrappers are present and used by the section", () => {
  for (const wrapper of updateWrappers) {
    assert.match(service, new RegExp(`export async function ${wrapper}\\b`), wrapper);
    assert.match(updates, new RegExp(`\\b${wrapper}\\b`), wrapper);
  }
});

test("Updates actions use the native job bridge instead of just recipes", () => {
  for (const command of ["bootc_upgrade", "bootc_rollback", "apply_staged"]) {
    assert.match(updatesRust, new RegExp(`fn ${command}\\b[\\s\\S]*?start_update_job`), command);
  }
  assert.match(updates, /invokeApplyStaged/);
  assert.doesNotMatch(updates, /RecipeButton recipe="(?:apply-staged|update-health)"/);
});

test("Updates overview reconciles a live check into the cards", () => {
  assert.match(updatesOverview, /fetchCollectAvailability\(null, false\)/);
  assert.match(updatesOverview, /check_state: availability\.state/);
  assert.match(updatesOverview, /blocked_reason: availability\.blocked_reason \|\| null/);
  assert.match(updatesOverview, /flatpak: String\(availability\.flatpak_count\)/);
});

test("Updates overview exposes the automatic watcher controls", () => {
  for (const wrapper of ["fetchUpdateWatcherStatus", "setUpdateWatcherEnabled", "checkForUpdatesNow", "deferUpdateWatcher"]) {
    assert.match(service, new RegExp(`export (?:async )?function ${wrapper}\\b`), wrapper);
    assert.match(updatesOverview, new RegExp(`\\b${wrapper}\\b`), wrapper);
  }
  assert.match(updatesOverview, /Defer automatic updates/);
  assert.match(updatesOverview, /Disable automatic updates|Enable automatic updates/);
});

test("ledger commands are registered in the Tauri handler", () => {
  const handler = rust.match(/generate_handler!\[([\s\S]*?)\]/)?.[1] ?? "";
  assert.notEqual(handler, "", "Tauri handler registration not found");
  for (const command of rustCommands) {
    assert.match(handler, new RegExp(`\\b${command}\\b`), command);
  }
});

test("every frontend invoke is registered in the Tauri handler", async () => {
  const handler = rust.match(/generate_handler!\[([\s\S]*?)\]/)?.[1] ?? "";
  const invoked = new Set();
  for (const file of await sourceFiles(resolve(root, "src"))) {
    const text = await readFile(file, "utf8");
    for (const match of text.matchAll(/invoke(?:<[^>]+>)?\(\"([^\"]+)\"/g)) invoked.add(match[1]);
  }
  assert.ok(invoked.size > 0, "no frontend invoke calls found");
  for (const command of invoked) {
    assert.match(handler, new RegExp(`\\b${command}\\b`), `${command} is invoked by the frontend but not registered`);
  }
});

test("frontend stays behind the typed Tauri/Rust boundary", async () => {
  const forbidden = [
    [/\b(?:PySide6|PyQt6)\b/, "Python/Qt UI dependency"],
    [/from\s+["'](?:node:)?child_process["']|@tauri-apps\/plugin-shell/, "process or shell plugin"],
    [/\b(?:spawn|exec|execFile|fork)\s*\(/, "direct process execution"],
    [/\b(?:run_command|execute_command|run_argv|spawn_process)\b/, "generic command bridge"],
  ];
  for (const file of await sourceFiles(resolve(root, "src"))) {
    const text = await readFile(file, "utf8");
    for (const [pattern, label] of forbidden) {
      assert.doesNotMatch(text, pattern, `${label} found in ${file}`);
    }
  }
});

test("multiplexed probe selectors used by Dashboard and Updates remain explicit", () => {
  for (const selector of ["bootc-branch", "bootc-status-data"]) {
    assert.match(service, new RegExp(`section: ["']${selector}["']`), selector);
  }
});

test("core workflow sections retain their read, action, and refresh paths", () => {
  for (const [name, source, wrappers] of [
    ["Guardian", guardian, ["fetchGuardianSnapshot", "runGuardianCheck", "runGuardianControl"]],
    ["Hardware", hardware, ["fetchHardwareSnapshot", "fetchHardwareViewSummary", "fetchLoadedKernelModules"]],
    ["Applications", apps, ["fetchAppStoreSnapshot", "searchAppStream", "installFlatpak", "fetchInstallStatus", "fetchInstalledFlatpaks"]],
    ["Gaming", gaming, ["fetchGamingLibrary", "fetchGamingSliceAvailable", "fetchProtonDbMany", "fetchAntiCheatTable"]],
  ]) {
    for (const wrapper of wrappers) assert.match(source, new RegExp(`\\b${wrapper}\\b`), `${name}: ${wrapper}`);
  }
  assert.match(updates, /Refresh status/);
  assert.match(guardian, /controlGuardian/);
  assert.match(apps, /installAndRefresh/);
});

test("parity notes do not describe completed core workflows as TODO", () => {
  assert.doesNotMatch(parity, /still TODO: migration checklist/);
  assert.doesNotMatch(parity, /Still TODO: `appstream`/);
});

test("privileged and destructive frontend paths require confirmation", () => {
  assert.match(service, /export function confirmUserAction/);
  assert.match(service, /privilegedActionPrompt/);
  assert.match(service, /Uninstall \$\{id\}\?/);
  assert.match(actions, /confirmUserAction\(`Run \$\{recipe\}\?/);
  assert.match(service, /recovery key will be sent only to the local privileged service/);
  assert.doesNotMatch(service, /confirmUserAction\([^\n]*key/);
});

test("Home Guardian activity exposes expandable current recommendations", () => {
  assert.match(guardianHistory, /aria-expanded=\{isExpanded\}/);
  assert.match(guardianHistory, /Confirm & run/);
  assert.match(guardianHistory, /Dismiss/);
  assert.match(dashboard, /dismissGuardianRecommendation/);
  assert.match(dashboard, /invokeGuardianExecute/);
});
