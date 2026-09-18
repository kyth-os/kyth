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
const updatesOverview = await readFile(resolve(root, "src/components/UpdatesOverview.tsx"), "utf8");
const updateMessages = await readFile(resolve(root, "src/components/updateMessages.ts"), "utf8");
const guardian = await readFile(resolve(root, "src/components/GuardianSection.tsx"), "utf8");
const hardware = await readFile(resolve(root, "src/components/HardwareSection.tsx"), "utf8");
const apps = await readFile(resolve(root, "src/components/AppStoreSection.tsx"), "utf8");
const vpn = await readFile(resolve(root, "src/components/VpnSection.tsx"), "utf8");
const exeDialog = await readFile(resolve(root, "src/components/ExeHandlerDialog.tsx"), "utf8");
const gaming = await readFile(resolve(root, "src/components/GamingSection.tsx"), "utf8");
const actions = await readFile(resolve(root, "src/components/SectionActions.tsx"), "utf8");
const rust = await readFile(resolve(root, "src-tauri/src/main.rs"), "utf8");
const updatesRust = await readFile(resolve(root, "src-tauri/src/commands/updates.rs"), "utf8");
const privilegeRust = await readFile(resolve(root, "src-tauri/src/commands/privilege.rs"), "utf8");
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
  "fetchUpdateHealth",
  "checkForUpdates",
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
  "collect_availability",
  "current_update_channel",
  "bootc_upgrade",
  "bootc_rollback",
  "apply_staged",
  "update_job_status",
  "update_health",
  "run_hub_action",
  "hub_action_status",
  "hub_action_cancel",
  "update_job_cancel",
  "cancel_job",
  "privileged_action_cancel",
  "install_cancel",
  "guardian_check_cancel",
  "security_job_cancel",
  "gaming_job_cancel",
];

test("Dashboard wrappers are present and used by the page", () => {
  for (const wrapper of dashboardWrappers) {
    assert.match(service, new RegExp(`export async function ${wrapper}\\b`), wrapper);
    assert.match(dashboard, new RegExp(`\\b${wrapper}\\b`), wrapper);
  }
});

test("Updates wrappers are present and used by the page", () => {
  for (const wrapper of updateWrappers) {
    assert.match(service, new RegExp(`export async function ${wrapper}\\b`), wrapper);
    assert.match(updatesOverview, new RegExp(`\\b(?:${wrapper}|fetchUpdatesSnapshot)\\b`), wrapper);
  }
});

test("Updates actions use the native job bridge instead of just recipes", () => {
  for (const command of ["bootc_upgrade", "bootc_rollback", "apply_staged"]) {
    assert.match(updatesRust, new RegExp(`fn ${command}\\b[\\s\\S]*?start_update_job`), command);
  }
  assert.match(updatesOverview, /invokeApplyStaged/);
  assert.doesNotMatch(updatesOverview, /RecipeButton recipe="(?:apply-staged|update-health)"/);
});

test("App updates poll long enough for the unbounded backend flatpak job and refresh the snapshot cache", () => {
  const fn = service.match(/export async function updateFlatpaks\(\)[\s\S]*?\n}/)?.[0] ?? "";
  assert.notEqual(fn, "", "updateFlatpaks not found");
  // update_flatpaks runs an unbounded `flatpak update --user` plus a
  // privileged system update with a 900s daemon timeout; the poll loop must
  // outlast that, not give up after ~2 minutes (240 * 500ms).
  const iterations = Number(fn.match(/for \(let i = 0; i < (\d+); i \+= 1\)/)?.[1] ?? 0);
  assert.ok(iterations >= 3600, `updateFlatpaks poll bound (${iterations} * 500ms) is too short for a real app update`);
  assert.match(fn, /invalidateSharedReads\([^)]*"updates-snapshot"/, "updateFlatpaks must invalidate updates-snapshot so refresh() after the update isn't served a stale cached count");
});

test("Backend flatpak update is bounded so a hung mirror can't wedge the job forever", () => {
  assert.match(rust, /fn update_flatpaks\b[\s\S]*?run_bounded_command/, "update_flatpaks must run the user flatpak update through run_bounded_command, not a raw .output() call");
  assert.match(rust, /fn update_flatpaks\b[\s\S]*?ErrorKind::TimedOut/, "a timeout from run_bounded_command must be reported as a timeout, not misreported as \"Could not start Flatpak\"");
});

test("Updates page reconciles the explicit check into the read model", () => {
  assert.match(service, /export async function checkForUpdates\b/);
  const check = service.match(/export async function checkForUpdates\(\)[\s\S]*?\n}/)?.[0] ?? "";
  assert.match(check, /"collect_availability"/);
  assert.match(check, /useCached: false/);
  assert.doesNotMatch(check, /catch/);
  assert.match(updatesOverview, /checkForUpdates\(\)/);
  assert.match(updatesOverview, /check_state: availability\.state/);
  assert.match(updatesOverview, /blocked_reason: availability\.blocked_reason \|\| null/);
  assert.match(updatesOverview, /flatpak: String\(availability\.flatpak_count\)/);
});

test("Updates page has one action owner and no duplicate legacy section", async () => {
  const page = await readFile(resolve(root, "src/pages/Updates.tsx"), "utf8");
  assert.doesNotMatch(page, /UpdatesSection|HubPage|Detailed update tools/);
  assert.doesNotMatch(updatesOverview, /update-watcher|Check now|Refresh status/);
  assert.match(updatesOverview, /const canStage = !staged && \(/);
  assert.match(updatesOverview, /lastAction === "check" \|\| lastAction === "stage"/);
  assert.doesNotMatch(updatesOverview, /disabled=\{busy !== null \|\| blocked\}/, "a failed check must not disable the safe staging retry");
});

test("Updates page gives plain-language next steps", () => {
  assert.match(updatesOverview, /updates-guidance/);
  assert.match(updatesOverview, /const \[lastAction, setLastAction\]/);
  assert.match(updatesOverview, /lastAction === "stage"/);
  assert.match(updatesOverview, /lastAction === "apps"/);
  assert.match(updatesOverview, /Downloading and preparing your update/);
  assert.match(updatesOverview, /Update ready — restart to finish/);
  assert.match(updatesOverview, /Choose “Restart to apply”/);
  assert.match(updatesOverview, /<ActionStatus/);
  assert.match(updateMessages, /We couldn't reach the update service/);
  assert.match(updateMessages, /couldn't reach the update registry before the check timed out/);
  assert.match(updateMessages, /current system has not changed/);
  assert.match(updatesOverview, /Free up some disk space/);
  assert.match(updatesOverview, /Your current system is still safe to use/);
  assert.match(updateMessages, /The update is downloaded and ready/);
  assert.match(updateMessages, /No changes were made/);
});

test("Privileged-helper outage is not reported as a network problem", () => {
  // A dead kyth-privileged daemon surfaces as "privileged service is
  // unavailable", which also matches the generic "unavailable" network
  // branch. The backend tags every daemon-client failure with
  // "[privileged]" and the mappers route on the tag first, so the message
  // stays correct whatever the human wording becomes. The legacy
  // "privileged service" substring branch covers old backends without tags.
  assert.match(privilegeRust, /PRIVILEGED_ERROR_TAG: &str = "\[privileged\]"/);
  assert.match(privilegeRust, /tag_privileged\(/);
  for (const [mapper, label] of [
    [updateMessages.slice(0, updateMessages.indexOf("export function friendlyActionError")), "friendlyAvailabilityDetail"],
    [updateMessages.slice(updateMessages.indexOf("export function friendlyActionError")), "friendlyActionError"],
  ]) {
    const tagBranch = mapper.indexOf("[privileged]");
    assert.ok(tagBranch !== -1, `${label} must route on the [privileged] tag`);
    assert.ok(
      tagBranch < mapper.indexOf("We couldn't reach the update service"),
      `${label} tag branch must win over the network message`,
    );
    const legacyBranch = mapper.indexOf("privileged service");
    assert.ok(legacyBranch !== -1, `${label} must keep the legacy substring branch`);
    assert.ok(
      legacyBranch < mapper.indexOf("We couldn't reach the update service"),
      `${label} legacy branch must win over the network message`,
    );
  }
  assert.match(updateMessages, /helper service isn't running/);
  assert.match(updateMessages, /system update helper isn't running/);
  assert.match(updatesOverview, /helper service isn't running/);
  assert.match(updatesOverview, /system update helper isn't running/);
});

test("cancel commands pair every job status command and resolve in the pollers", () => {
  for (const command of [
    "cancel_job",
    "hub_action_cancel",
    "update_job_cancel",
    "privileged_action_cancel",
    "install_cancel",
    "guardian_check_cancel",
    "security_job_cancel",
    "gaming_job_cancel",
  ]) {
    assert.match(service, new RegExp(`"${command}"`), `${command} needs a frontend cancel wrapper`);
  }
  // A cancelled job is user intent, not a backend error: every poller must
  // resolve it instead of looping to its timeout or throwing it as a failure.
  assert.match(service, /"cancelled"\) return "Cancelled\."/, "cancelled jobs must resolve friendly");
  assert.ok(!/state\.state === "failed" \|\| state\.state === "unknown"\) throw/.test(service), "pollers must route terminal states through resolveTerminalJob");
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
    ["Applications", apps, ["fetchAppStoreSnapshot", "searchAppStream", "installFlatpak", "waitInstallJob", "fetchInstalledFlatpaks"]],
    ["Gaming", gaming, ["fetchGamingLibrary", "fetchGamingSliceAvailable", "fetchProtonDbMany", "fetchAntiCheatTable"]],
  ]) {
    for (const wrapper of wrappers) assert.match(source, new RegExp(`\\b${wrapper}\\b`), `${name}: ${wrapper}`);
  }
  assert.match(updatesOverview, /Download and stage/);
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

test("App Store install waits out slow mirrors and stays cancellable after the UI wait", () => {
  assert.match(apps, /waitInstallJob\(await installFlatpak\(id\), 1800\)/, "install bound must be 1800 iters (15 min), not 60");
  const fn = service.match(/export async function waitInstallJob\(job: string[\s\S]*?\n\}/)?.[0] ?? "";
  assert.notEqual(fn, "", "waitInstallJob not found");
  assert.match(fn, /settled/, "waitInstallJob must keep the job tracked after a UI timeout so Cancel still reaches it");
  assert.match(fn, /if \(settled\) untrackJob/, "waitInstallJob must only untrack on terminal settle");
});

test("availability check races a 95s timeout with a friendly error", () => {
  const check = service.match(/export async function checkForUpdates\(\)[\s\S]*?\n\}/)?.[0] ?? "";
  assert.notEqual(check, "", "checkForUpdates not found");
  assert.match(check, /Promise\.race/, "collect_availability must race a timeout");
  assert.match(check, /95_000/, "timeout must be 95s");
  assert.match(check, /timed out/, "timeout must throw a friendly error");
});

test("strict pollers tolerate transient status failures before throwing", () => {
  for (const name of ["waitGuardianCheck", "runPrivilegedAction", "waitJustJob", "waitUpdateJob", "uninstallFlatpak", "updateFlatpaks"]) {
    const start = service.indexOf(name);
    assert.ok(start !== -1, `${name} not found`);
    const fn = service.slice(start, service.indexOf("\n}\n", start) + 3);
    assert.match(fn, /statusFailures >= 5/, `${name} must tolerate 5 consecutive status failures`);
  }
});

test("tolerant pollers bail on lost jobs and treat unknown as terminal", () => {
  for (const name of ["waitHubJob", "pollSecurityJob", "pollGamingJob"]) {
    const start = service.indexOf(`function ${name}`);
    assert.ok(start !== -1, `${name} not found`);
    const fn = service.slice(start, service.indexOf("\n}\n", start) + 3);
    assert.match(fn, /nulls >= 10/, `${name} must bail after 10 consecutive nulls`);
    assert.match(fn, /state\.state === "unknown"\) throw/, `${name} must treat unknown as terminal`);
  }
});

test("a second launch into an occupied domain is rejected", () => {
  const fn = service.match(/function trackJob\(domain: JobDomain, job: string\): void \{[\s\S]*?\n\}/)?.[0] ?? "";
  assert.notEqual(fn, "", "trackJob not found");
  assert.match(fn, /already running/, "trackJob must reject a second launch into an occupied slot");
});

test("in-flight jobs persist across reloads and reattach on init", () => {
  assert.match(service, /kyth-hub:inflight-jobs/, "resumable ids need a localStorage key");
  assert.match(service, /localStorage\.setItem/, "track must persist resumable ids");
  assert.match(service, /localStorage\.getItem/, "init must reattach resumable ids");
  assert.match(service, /reattachInFlightJobs\(\);/, "reattach must run on module init");
  assert.match(service, /export function getInFlightJob/, "cancel paths need a reader for reattached ids");
});

test("VPN polling stops on terminal states and is capped with backoff", () => {
  assert.match(vpn, /connected", "failed", "disconnected/, "all terminal states must stop polling");
  assert.match(vpn, /polls >= 300/, "polls must be capped at 300");
  assert.match(vpn, /polls < 60 \? 1000 : 5000/, "polling must back off after the first minute");
  assert.doesNotMatch(vpn, /setInterval/, "the unbounded 1s interval must go");
});

test("exe handler dialog caps polls and stays cancellable while running", () => {
  assert.match(exeDialog, /polls >= 240/, "exe handler polls must cap at 240");
  assert.match(exeDialog, /still running after several minutes/, "cap must surface a terminal error");
  assert.doesNotMatch(exeDialog, /setInspection\(null\)\} disabled/, "Cancel must stay enabled while a job runs");
  assert.match(exeDialog, /Bottles.*timeout|timeout.*Bottles/i, "Cancel must note the backend Bottles timeout followup");
});
