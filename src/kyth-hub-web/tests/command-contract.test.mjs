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
const appShell = await readFile(resolve(root, "src/App.tsx"), "utf8");
const hubPage = await readFile(resolve(root, "src/pages/HubPage.tsx"), "utf8");
const deepLink = await readFile(resolve(root, "src/deepLink.ts"), "utf8");
const mainEntry = await readFile(resolve(root, "src/main.tsx"), "utf8");

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
  "fetchStageProgress",
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
  for (const command of ["bootc_rollback", "apply_staged"]) {
    assert.match(updatesRust, new RegExp(`fn ${command}\\b[\\s\\S]*?start_update_job`), command);
  }
  // The stage path streams helper progress markers, so it launches through
  // the streaming variant — same job bridge, same cancel/timeout contract.
  assert.match(updatesRust, /fn bootc_upgrade\b[\s\S]*?start_stage_job/, "bootc_upgrade");
  assert.match(updatesOverview, /invokeApplyStaged/);
  assert.doesNotMatch(updatesOverview, /RecipeButton recipe="(?:apply-staged|update-health)"/);
});

test("App updates poll long enough for the unbounded backend flatpak job and refresh the snapshot cache", () => {
  const fn = service.match(/export async function updateFlatpaks\(\)[\s\S]*?\n}/)?.[0] ?? "";
  assert.notEqual(fn, "", "updateFlatpaks not found");
  // update_flatpaks runs an unbounded `flatpak update --user` plus a
  // privileged system update with a 900s daemon timeout; the poll bound must
  // outlast that, not give up after ~2 minutes. Bound lives on the shared
  // per-domain poller now (limit: N) instead of a local for-loop.
  const shared = fn.match(/limit: (\d+)/)?.[1] ?? fn.match(/for \(let i = 0; i < (\d+); i \+= 1\)/)?.[1] ?? 0;
  assert.ok(Number(shared) >= 3600, `updateFlatpaks poll bound (${shared}) is too short for a real app update`);
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
  assert.match(updatesOverview, /const canStage = !stagedEffective && !isBlocked && \(/);
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
  // Both directions are bounded: a wedged daemon must fail fast on write
  // instead of freezing the UI behind the long read bound.
  assert.match(privilegeRust, /set_read_timeout/);
  assert.match(privilegeRust, /set_write_timeout/);
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
  // Transient tolerance lives in the shared per-domain poller (default 5
  // consecutive nulls); each strict waiter routes through it instead of
  // running its own loop.
  assert.match(service, /maxNulls \?\? 5/, "shared poller must default to 5 tolerated nulls");
  for (const name of ["waitGuardianCheck", "runPrivilegedAction", "waitJustJob", "waitUpdateJob", "uninstallFlatpak", "updateFlatpaks"]) {
    const start = service.indexOf(name);
    assert.ok(start !== -1, `${name} not found`);
    const fn = service.slice(start, service.indexOf("\n}\n", start) + 3);
    assert.match(fn, /pollJobUntilSettled/, `${name} must poll through the shared per-domain poller`);
    assert.match(fn, /lostContactMessage/, `${name} must keep its lost-contact message`);
  }
});

test("tolerant pollers bail on lost jobs and treat unknown as terminal", () => {
  for (const name of ["waitHubJob", "pollSecurityJob", "pollGamingJob"]) {
    const start = service.indexOf(`function ${name}`);
    assert.ok(start !== -1, `${name} not found`);
    const fn = service.slice(start, service.indexOf("\n}\n", start) + 3);
    assert.match(fn, /maxNulls: 10/, `${name} must bail after 10 consecutive nulls`);
    assert.match(fn, /state\.state === "unknown"\) throw/, `${name} must treat unknown as terminal`);
  }
});

test("domains share one poller with backoff and cross-tab awareness", () => {
  assert.match(service, /activeDomainPollers/, "one poller per domain needs a shared registry");
  assert.match(service, /elapsed > 30_000 \? Math\.max\(baseInterval, 2000\)/, "pollers must back off 500ms -> 2s after 30s");
  assert.match(service, /inFlightJobs\.get\(domain\) !== job/, "poll ticks must stop when another tab clears the slot");
  assert.match(service, /addEventListener\("storage"/, "slot changes from other tabs need a storage listener");
});

test("persisted slots carry timestamps and stale ones are dropped", () => {
  assert.match(service, /\{ job, ts: Date\.now\(\) \}/, "persisted entries must be job + timestamp objects");
  assert.match(service, /REATTACHED_JOB_TTL_MS/, "reattach must drop entries older than the job TTL");
  assert.match(service, /validateReattachedJobs\(\)/, "reattached ids need a one-shot status probe before being trusted");
  assert.match(service, /DOMAIN_STATUS_COMMAND\[domain\]/, "reattach validation must probe each domain's own status command");
});

test("mutating Hub update launches serialize on the shared bootc lock", () => {
  for (const command of ["bootc_upgrade", "bootc_rollback", "bootc_switch_branch", "apply_staged"]) {
    const fn = updatesRust.match(new RegExp(`fn ${command}\\b[\\s\\S]*?start_(update|stage)_job`))?.[0] ?? "";
    assert.notEqual(fn, "", `${command} not found`);
    assert.match(fn, /with_bootc_lock/, `${command} must admission-check the shared bootc lock before launching`);
    assert.match(fn, /take_mutating_slot/, `${command} must take the in-process mutating slot: the flock probe is check-then-act across two rapid launches`);
  }
});

test("update job ids survive reload reattach (slug, never a label with spaces)", () => {
  // The frontend only reattaches `<prefix>-<nanos>` ids across a reload; an
  // id built from a display label ("Download and stage") fails the pattern
  // and strands the job with no Cancel. Every launch site must pass a slug.
  const slugs = [...updatesRust.matchAll(/start_(?:update|stage)_job\(\s*"([^"]+)"/g)].map((match) => match[1]);
  assert.ok(slugs.length >= 4, `expected update launch slugs, found ${slugs.length}`);
  for (const slug of slugs) {
    assert.match(slug, /^[a-z][a-z0-9-]*$/, `update job slug ${JSON.stringify(slug)} must match the reattach pattern`);
  }
  assert.match(service, /JOB_ID_PATTERN/, "the reattach pattern must stay strict");
});

test("Updates page renders a working Cancel wired to the update job", () => {
  assert.match(updatesOverview, /cancelUpdateJob/, "the page must import the update cancel path");
  assert.match(updatesOverview, /getInFlightJob\("update"\)/, "Cancel must cover jobs reattached after a reload");
  assert.match(updatesOverview, /Cancel update/, "a running update needs a visible Cancel");
  assert.match(updatesOverview, /cancelRunning\("update"\)/, "Cancel must invoke the update cancel path");
  // Cancel must stay enabled exactly when the mutating buttons disable.
  assert.match(updatesOverview, /disabled=\{cancelling \|\| !loaded\}/, "Cancel must not share the busy-disabled gate");
  assert.match(updatesOverview, /<ActionStatus status=\{cancelNote \?\? status\}/, "cancel progress must surface in the status row");
});

test("a cancelled stage warns that staged content may still be pending", () => {
  assert.match(updateMessages, /may already be staged/, "cancelling a stage must warn about reboot-pending content");
  assert.match(updateMessages, /No changes were made/, "non-stage cancels keep the clean no-op message");
});

test("blocked updates render as blocked with a reason, never up-to-date", () => {
  assert.match(updatesOverview, /check_state === "blocked"/, "the page must recognise the blocked state");
  assert.match(updatesOverview, /Update blocked/, "blocked must not read as up-to-date");
  assert.match(updatesOverview, /blocked_reason \|\| updateStatus\?\.detail/, "blocked must show its reason");
  assert.match(updatesOverview, /!isBlocked/, "staging must stay unavailable while blocked");
  const label = updatesOverview.match(/const overallLabel =[\s\S]*?;/)?.[0] ?? "";
  assert.ok(label.indexOf("isBlocked") !== -1 && label.indexOf("isBlocked") < label.indexOf('"uptodate"'), "blocked must win over up-to-date in the status chip");
});

test("reads during an operation render as busy, not a connection error", () => {
  assert.match(updatesOverview, /check_state === "busy"/, "the page must recognise the busy state");
  assert.match(updatesOverview, /Update in progress/, "busy must not read as a connection failure");
  assert.match(updatesOverview, /An update operation is in progress/, "busy needs its own guidance card");
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
  assert.match(exeDialog, /cancelExeHandlerBottles\(job\.job\)/, "Cancel must reach the backend Bottles job, not just close the dialog");
});

test("stale UI states recover without manual navigation", () => {
  assert.match(service, /emitOnlineRefetch\(\)/, "reconnect must emit a refetch signal, not just invalidate caches");
  assert.match(vpn, /onOnlineRefetch\(/, "mount-only VPN reads must re-run on reconnect");
  assert.match(service, /\} catch \{\n    return null;\n  \}\n\}/, "probe invoke failures must not be cached as null");
  assert.match(hubPage, /Unknown section/, "unknown ?section= must render a notice, not a blank page");
  assert.match(actions, /getInFlightJob\(trackedDomain\) !== undefined/, "resumed note must read the tracked slot live");
});

test("routing and init failures stay visible", () => {
  assert.match(appShell, /RouteErrorBoundary/, "lazy routes need an error boundary with retry");
  assert.match(deepLink, /deep-link-rejected/, "unknown deep links must not log as success");
  assert.match(mainEntry, /\.catch\(/, "deep-link init failure must not die silently");
  assert.match(vpn, /} finally \{\n.*setPassword\(""\)/s, "VPN password must clear even when connect throws");
  assert.doesNotMatch(vpn, /finally \{ setJob\(null\); \}/, "failed Disconnect must keep the job handle for retry");
});

test("stage progress survives reload and checks do not stack", () => {
  // Determinate bar must follow the backend-tracked job, not just the
  // local run: after a reload mid-stage the bar recovers instead of
  // dropping to indeterminate.
  assert.match(updatesOverview, /updateTracked && !\(readings\.status\?\.staged \|\| stagedLatch\)/, "stage polling must cover the reattached backend job");
  assert.match(updatesOverview, /stagedLatch/, "successful stage must latch the Restart-to-apply UI past probe lag");
  assert.match(updatesOverview, /progressPct/, "stage guidance must render the determinate bar");
  // The availability probe cannot be cancelled mid-invoke: single-flight
  // joins a second press, and the orphan timer is cleared on settle.
  assert.match(service, /availabilityCheckInFlight/, "concurrent checks must join instead of stacking registry fan-outs");
  assert.match(service, /clearTimeout\(timer\)/, "the check timeout must be cleared on settle");
});

test("exe trust-once fast path is wired end to end", () => {
  // Double-clicked files the user trusted must launch with no dialog:
  // the native handler checks the content-hash store first, the dialog
  // records consent with the full hash, and umu covers game exes.
  assert.match(rust, /\bexe_handler_trust\b/, "trust command must be registered");
  assert.match(rust, /\bexe_handler_launch_umu\b/, "umu launch command must be registered");
  assert.match(service, /trustExeHandlerFile/, "trust wrapper must exist");
  assert.match(service, /launchExeHandlerUmu/, "umu wrapper must exist");
  assert.match(exeDialog, /trustExeHandlerFile\(inspection\.sha256_full/, "dialog must record the full content hash, never a prefix");
  assert.match(exeDialog, /launchExeHandlerUmu/, "dialog must offer the Proton path for game exes");
});

test("phase-2 onboarding is state-driven, not copy", async () => {
  // Play checklist derives from live readings (first run shows steps,
  // finished setup shows actions); the Home banner and Steam step read
  // the background-install status; Steam Play defaults are verified
  // read-only from config.vdf, never written.
  assert.match(rust, /firstboot_apps_status/, "first-boot status command must be registered");
  assert.match(rust, /steam_play_status/, "steam play status command must be registered");
  assert.match(service, /fetchFirstbootAppsStatus/, "first-boot wrapper must exist");
  assert.match(service, /fetchSteamPlayStatus/, "steam play wrapper must exist");
  const playOverview = await readFile(resolve(root, "src/components/PlayOverview.tsx"), "utf8");
  const controllersSection = await readFile(resolve(root, "src/components/ControllersSection.tsx"), "utf8");
  const playPage = await readFile(resolve(root, "src/pages/Play.tsx"), "utf8");
  assert.match(playOverview, /setupSteps/, "Play must render the ordered setup checklist");
  assert.match(playOverview, /setupComplete/, "Play must collapse the checklist once setup finishes");
  assert.match(playPage, /Nothing played yet/, "Play must explain an empty session history");
  assert.match(gaming, /Steam Play defaults/, "Gaming must surface the Steam Play default state");
  assert.match(gaming, /Install Vesktop/, "Gaming must offer one-click voice chat");
  assert.match(controllersSection, /GamepadTester/, "Controllers must include a live input tester");
});

test("phase-3 graphics truth is wired, not implied", () => {
  // Shader tmpfs must point Mesa at the mount with a sticky mode, prune
  // must cap instead of deleting, gamescope presets must inject real flags,
  // SCX must offer installed schedulers, per-game saves must render to a
  // pasteable launch string, and PRIME/powerd/Xe must exist outside copy.
  assert.match(rust, /scx_available/, "scx list command must be registered");
  assert.match(rust, /per_game_launch_options/, "launch-options preview command must be registered");
  assert.match(service, /fetchScxAvailable/, "scx list wrapper must exist");
  assert.match(service, /fetchPerGameLaunchOptions/, "launch-options wrapper must exist");
  assert.match(service, /savePerGameProfile\(appid: string, profile: string, hdr: boolean, fps: string, prime: boolean\)/, "per-game save must carry fps and prime");
  assert.match(gaming, /Steam launch options/, "builder must show the pasteable launch string");
  assert.match(gaming, /PRIME/, "builder must offer the dGPU toggle");
});
