import { invoke } from "@tauri-apps/api/core";
import { inTauriShell } from "./tauriEnv";

// Several surfaces present the same fact (for example, an overview card and
// a detailed workspace).  A Tauri invoke is not automatically shared, so
// without this small cache one navigation could start the same `bootc` or
// `flatpak` process more than once.  Keep this deliberately local rather
// than adding a client-state dependency: callers still receive the typed
// result they expect, while concurrent readers receive one in-flight job.
type SharedRead = {
  value?: unknown;
  expiresAt: number;
  pending?: Promise<unknown>;
};

const sharedReads = new Map<string, SharedRead>();

async function sharedRead<T>(key: string, ttlMs: number, load: () => Promise<T>): Promise<T> {
  const now = Date.now();
  const current = sharedReads.get(key);
  if (current?.pending) return current.pending as Promise<T>;
  if (current && current.expiresAt > now) return current.value as T;

  const pending = load().then(
    (value) => {
      sharedReads.set(key, { value, expiresAt: Date.now() + ttlMs });
      return value;
    },
    (error) => {
      if (sharedReads.get(key)?.pending === pending) sharedReads.delete(key);
      throw error;
    },
  );
  sharedReads.set(key, { expiresAt: 0, pending });
  return pending;
}

export function invalidateSharedReads(...keys: string[]): void {
  for (const key of keys) sharedReads.delete(key);
}

/** Drop every cached shared read. Used on reconnect (see OfflineBanner):
 * TTLs served while offline go stale, and the banner promises actions work
 * without a manual refresh — so the next read after `online` must be live. */
export function invalidateAllSharedReads(): void {
  sharedReads.clear();
}

type OnlineRefetchListener = () => void;
const onlineRefetchListeners = new Set<OnlineRefetchListener>();

/** Sections with mount-only fetches subscribe so a reconnect re-runs them:
 * invalidation alone can't refresh state that was already rendered from a
 * stale (empty/error) read. Returns an unsubscribe function. */
export function onOnlineRefetch(listener: OnlineRefetchListener): () => void {
  onlineRefetchListeners.add(listener);
  return () => {
    onlineRefetchListeners.delete(listener);
  };
}

/** Emitted by OfflineBanner after invalidating: every subscriber refetches. */
export function emitOnlineRefetch(): void {
  for (const listener of [...onlineRefetchListeners]) {
    try {
      listener();
    } catch {
      /* one section's refetch must not break the others */
    }
  }
}

/** Bounded invoke for snapshot reads: a wedged backend must surface an
 * error instead of hanging the page forever. Callers keep their
 * try/catch-null shape; the timeout only converts a hang into a throw.
 * (Tauri invokes cannot be cancelled — the late response is dropped.) */
async function invokeBounded<T>(
  command: string,
  args?: Record<string, unknown>,
  ms = 30_000,
): Promise<T> {
  return withTimeout(invoke<T>(command, args), command, ms);
}

/** Race any promise against a cleared-on-settle timer. Backs invokeBounded
 * and multi-invoke snapshots alike. */
async function withTimeout<T>(
  task: Promise<T>,
  label: string,
  ms = 30_000,
): Promise<T> {
  let timer: ReturnType<typeof globalThis.setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = globalThis.setTimeout(
      () => reject(new Error(`${label} timed out; the backend did not respond.`)),
      ms,
    );
  });
  try {
    return await Promise.race([task, timeout]);
  } finally {
    if (timer !== undefined) globalThis.clearTimeout(timer);
  }
}

// Real backend data, read through the Tauri shell's bridge commands (see
// src-tauri/src/main.rs, which calls straight into the kyth-shared Rust
// crate — src/kyth-shared-rs — no subprocess). Every read here returns
// null rather than throwing when the data isn't available — running in a
// plain browser (npm run dev), no Tauri build, or (very commonly on a dev
// machine) no on-disk state yet because kyth-probe / Guardian have never
// run. Callers render an honest empty state on null; there are no fixtures
// left to fall back to.
//
// Two conventions the sections rely on:
//   - Reads may run on mount, but the Tauri commands for update status,
//     update summaries, and channel fallback offload blocking probes before
//     they reach this webview. Switching tabs therefore never blocks the UI.
//   - The mutating wrappers at the bottom throw instead of returning null,
//     so useSectionAction can report the failure rather than leaving a
//     button that appears to have done something.

export interface GuardianHistoryItem {
  timestamp: number;
  title: string;
  detail: string;
  status: "ok" | "warn" | "error";
  recipeId: string | null;
  action: string;
  verified: boolean | null;
}

export interface GuardianSnapshot {
  pendingCount: number;
  pending: GuardianPendingItem[];
  history: GuardianHistoryItem[];
}

// Mirrors main.rs's GuardianSnapshotResponse shape exactly.
interface GuardianBridgeHistoryItem {
  timestamp: number;
  recipe_id: string | null;
  title: string;
  detail: string;
  action: string;
  verified: boolean | null;
}
interface GuardianBridgePendingItem {
  recipe_id: string;
  title: string;
  detail: string;
  risk: string;
}
interface GuardianBridgeResponse {
  pending_count: number;
  pending: GuardianBridgePendingItem[];
  history: GuardianBridgeHistoryItem[];
}

function statusFor(item: GuardianBridgeHistoryItem): GuardianHistoryItem["status"] {
  if (item.action === "skipped") return "warn";
  if (item.verified === false) return "error";
  if (item.verified === true) return "ok";
  return "warn"; // recommended, not yet actioned
}

export async function fetchGuardianSnapshot(): Promise<GuardianSnapshot | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invokeBounded<GuardianBridgeResponse>("guardian_snapshot", undefined, 30_000);
    return {
      pendingCount: raw.pending_count,
      pending: raw.pending.map((item) => ({
        recipeId: item.recipe_id,
        title: item.title,
        detail: item.detail,
        risk: item.risk,
      })),
      history: raw.history.map((item) => ({
        timestamp: item.timestamp,
        recipeId: item.recipe_id,
        title: item.title,
        detail: item.detail,
        action: item.action,
        verified: item.verified,
        status: statusFor(item),
      })),
    };
  } catch {
    return null;
  }
}
interface GuardianActionLaunch { job: string; state: "running"; detail: string; }
function guardianJob(launch: GuardianActionLaunch): string { if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "Guardian action did not start."); return launch.job; }
export async function runGuardianCheck(investigate = false): Promise<string> {
  return guardianJob(await invokeBounded<GuardianActionLaunch>("guardian_check", { investigate }, 90_000));
}
export async function waitGuardianCheck(job: string): Promise<string> {
  trackJob("guardian", job);
  try {
    return resolveTerminalJob(await pollJobUntilSettled("guardian", job, {
      statusCommand: "guardian_check_status",
      limit: 180,
      lostContactMessage: "Lost contact with the Guardian check; refresh the page in a moment.",
      timeoutMessage: "Guardian is still running; refresh the page in a moment.",
    }));
  } finally {
    untrackJob("guardian", job);
  }
}

/** Terminal job-state resolution shared by every poller below: "complete"
 * returns detail, a user-cancelled job returns a friendly non-error, and
 * anything else throws so useSectionAction reports the failure. */
function resolveTerminalJob(state: InstallStatus): string {
  if (state.state === "complete") return state.detail;
  if (state.state === "cancelled") return "Cancelled.";
  throw new Error(state.detail);
}

/** Domains with at most one Hub-tracked job in flight. Launch wrappers
 * register their job id on entry and clear it on settle, so a section's
 * Cancel button can stop the actual running backend job without every
 * action having to thread job ids through its presentation state. Two
 * concurrent jobs in one domain is a misuse bug, not a supported state:
 * the second launch is rejected with an already-running error while the
 * first keeps the slot. */
export type JobDomain = "guardian" | "privileged" | "hub-action" | "update" | "job" | "install" | "security" | "gaming" | "vpn";

const inFlightJobs = new Map<JobDomain, string>();

// Resumable job ids survive a page reload so Cancel still reaches the real
// backend job after a refresh. Reattached on module init below.
const INFLIGHT_STORAGE_KEY = "kyth-hub:inflight-jobs";

/** Persisted slot: the job id plus when this tab tracked it. The timestamp
 * lets a reattaching tab drop entries older than the job TTL instead of
 * polling a backend job that is long gone. */
interface PersistedSlot {
  job: string;
  ts: number;
}

/** Upper bound on reattaching a persisted slot. Covers the longest
 * legitimate wait (hour-long update downloads) with margin; anything older
 * is a stale entry from a tab that died without untracking. */
const REATTACHED_JOB_TTL_MS = 2 * 60 * 60 * 1000;

// Domains allowed to own a resumable job, and the backend id shape
// (`<prefix>-<nanos>`, e.g. `gaming-install-123456789`). localStorage is
// attacker-reachable (XSS, devtools, extensions), so reattach drops anything
// that does not match rather than tracking a bogus id into a cancel call.
const JOB_DOMAINS: readonly JobDomain[] = [
  "guardian",
  "privileged",
  "hub-action",
  "update",
  "job",
  "install",
  "security",
  "gaming",
  "vpn",
];
const JOB_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]*-\d+$/;

function isValidPersistedJob(domain: string, job: unknown): job is string {
  return (
    (JOB_DOMAINS as readonly string[]).includes(domain) &&
    typeof job === "string" &&
    job.length > 0 &&
    job.length <= 128 &&
    JOB_ID_PATTERN.test(job)
  );
}

function persistInFlightJobs(): void {
  try {
    if (typeof localStorage === "undefined") return;
    if (inFlightJobs.size === 0) localStorage.removeItem(INFLIGHT_STORAGE_KEY);
    else {
      const slots: Record<string, PersistedSlot> = {};
      for (const [domain, job] of inFlightJobs) slots[domain] = { job, ts: Date.now() };
      localStorage.setItem(INFLIGHT_STORAGE_KEY, JSON.stringify(slots));
    }
  } catch {
    // Storage full or unavailable (private mode): in-memory tracking still works.
  }
}

/** Normalize one persisted entry. Accepts the current `{job, ts}` object
 * and the legacy plain-string id (treated as freshly tracked) so older
 * Hub builds' entries still reattach instead of stranding a Cancel. */
function normalizePersistedSlot(domain: string, entry: unknown): string | null {
  if (typeof entry === "string") {
    return isValidPersistedJob(domain, entry) ? entry : null;
  }
  if (typeof entry !== "object" || entry === null || Array.isArray(entry)) return null;
  const { job, ts } = entry as { job?: unknown; ts?: unknown };
  if (!isValidPersistedJob(domain, job)) return null;
  if (typeof ts !== "number" || !Number.isFinite(ts)) return null;
  if (Date.now() - ts > REATTACHED_JOB_TTL_MS) return null;
  return job;
}

function reattachInFlightJobs(): void {
  try {
    if (typeof localStorage === "undefined") return;
    const raw = localStorage.getItem(INFLIGHT_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return;
    let dropped = false;
    for (const [domain, entry] of Object.entries(parsed)) {
      const job = normalizePersistedSlot(domain, entry);
      if (job == null) {
        dropped = true;
        continue;
      }
      inFlightJobs.set(domain as JobDomain, job);
    }
    // Drop mismatches from storage too so a poisoned entry cannot linger.
    if (dropped) persistInFlightJobs();
  } catch {
    // Corrupt entry: start clean rather than tracking a bogus job id.
  }
}

reattachInFlightJobs();

/** Status command per domain for the one-shot reattach validation below.
 * vpn_status returns the shared InstallStatus shape (unknown for a job the
 * backend no longer knows), so the vpn slot validates like every other. */
const DOMAIN_STATUS_COMMAND: Record<JobDomain, string> = {
  guardian: "guardian_check_status",
  privileged: "privileged_action_status",
  "hub-action": "hub_action_status",
  update: "update_job_status",
  job: "job_status",
  install: "install_status",
  security: "security_job_status",
  gaming: "gaming_job_status",
  vpn: "vpn_status",
};

/** Validate each reattached id with a single status probe before it is
 * trusted: a job the backend no longer knows (restart, eviction, TTL) is
 * dropped instead of tracked into a Cancel that can never land. Runs once
 * at module init; live launches use trackJob directly and need no probe. */
async function validateReattachedJobs(): Promise<void> {
  if (!inTauriShell()) return;
  const entries = [...inFlightJobs];
  if (entries.length === 0) return;
  await Promise.all(entries.map(async ([domain, job]) => {
    try {
      const state = await invoke<InstallStatus>(DOMAIN_STATUS_COMMAND[domain], { job });
      if (!state || state.state === "unknown") untrackJob(domain, job);
    } catch {
      // Probe itself failed (backend restarting): keep the slot so Cancel
      // still has a chance once the backend is back.
    }
  }));
}

void validateReattachedJobs();

/** Cross-tab single-flight: another Hub tab tracking or clearing a domain
 * slot adopts or releases it here, so two tabs never poll (or cancel) the
 * same backend job independently and a Cancel in one tab stops the other
 * tab's poller on its next tick (see pollJobUntilSettled). */
function handleInflightStorageEvent(event: StorageEvent): void {
  try {
    if (event.key !== INFLIGHT_STORAGE_KEY) return;
    const parsed = (event.newValue ? JSON.parse(event.newValue) : {}) as Record<string, unknown>;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return;
    const incoming = new Map<JobDomain, string>();
    for (const [domain, entry] of Object.entries(parsed)) {
      const job = normalizePersistedSlot(domain, entry);
      if (job != null) incoming.set(domain as JobDomain, job);
    }
    for (const [domain, job] of incoming) {
      if (inFlightJobs.get(domain) !== job) inFlightJobs.set(domain, job);
    }
    for (const domain of [...inFlightJobs.keys()]) {
      if (!incoming.has(domain)) inFlightJobs.delete(domain);
    }
  } catch {
    // Corrupt cross-tab payload: keep local tracking untouched.
  }
}

if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("storage", handleInflightStorageEvent);
}

/** Current tracked job for a domain, if any (including reattached ids). */
export function getInFlightJob(domain: JobDomain): string | undefined {
  return inFlightJobs.get(domain);
}

function trackJob(domain: JobDomain, job: string): void {
  const current = inFlightJobs.get(domain);
  if (current && current !== job) {
    throw new Error("Another action is already running; wait for it to finish or cancel it first.");
  }
  inFlightJobs.set(domain, job);
  persistInFlightJobs();
}

function untrackJob(domain: JobDomain, job: string): void {
  if (inFlightJobs.get(domain) === job) inFlightJobs.delete(domain);
  persistInFlightJobs();
}

interface DomainPollOptions {
  statusCommand: string;
  /** Max status probes before giving up. */
  limit: number;
  /** Probe interval for the first 30s (default 500ms). */
  baseIntervalMs?: number;
  /** Consecutive empty probes before lost-contact (default 5). */
  maxNulls?: number;
  lostContactMessage: string;
  timeoutMessage: string;
}

/** One poller per domain: concurrent waiters for the same job share a
 * single promise (and therefore a single probe cadence) instead of each
 * opening their own 500ms loop against the backend. A different job id in
 * the same domain is a misuse bug and is rejected like trackJob rejects it.
 *
 * Backoff: 500ms probes for the first 30s, then 2s — long upgrades and
 * installs do not need sub-second resolution for an hour. Slower-based
 * pollers (security/gaming at 3s) keep their cadence throughout.
 *
 * Storage-event subscribed: every tick re-checks the tracked slot, so a
 * Cancel (or untrack) from another tab stops this tab's poll on its next
 * tick instead of polling a dead job to the limit. */
const activeDomainPollers = new Map<JobDomain, { job: string; promise: Promise<InstallStatus> }>();

function pollJobUntilSettled(
  domain: JobDomain,
  job: string,
  options: DomainPollOptions,
): Promise<InstallStatus> {
  const active = activeDomainPollers.get(domain);
  if (active) {
    if (active.job === job) return active.promise;
    throw new Error("Another action is already running; wait for it to finish or cancel it first.");
  }
  const baseInterval = options.baseIntervalMs ?? 500;
  const maxNulls = options.maxNulls ?? 5;
  const startedAt = Date.now();
  const promise = (async (): Promise<InstallStatus> => {
    let nulls = 0;
    for (let i = 0; i < options.limit; i += 1) {
      const elapsed = Date.now() - startedAt;
      await new Promise((resolve) => window.setTimeout(resolve, elapsed > 30_000 ? Math.max(baseInterval, 2000) : baseInterval));
      // Another tab cleared or replaced this domain's slot: stop polling.
      if (inFlightJobs.get(domain) !== job) {
        throw new Error("This action is no longer tracked here; it may have been cancelled in another tab.");
      }
      const state = await invoke<InstallStatus>(options.statusCommand, { job }).catch(() => null);
      if (!state) {
        nulls += 1;
        if (nulls >= maxNulls) throw new Error(options.lostContactMessage);
        continue;
      }
      nulls = 0;
      if (state.state === "running") continue;
      return state;
    }
    throw new Error(options.timeoutMessage);
  })();
  activeDomainPollers.set(domain, { job, promise });
  const release = (): void => {
    if (activeDomainPollers.get(domain)?.promise === promise) activeDomainPollers.delete(domain);
  };
  promise.then(release, release);
  return promise;
}

/** Cancel a running backend job. Each domain owns a status/cancel command
 * pair over the same bounded store; cancelling kills the underlying process
 * (socket-I/O jobs are marked and their late finish is dropped instead). */
async function cancelBackendJob(command: string, job: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Cancelling is available from the installed Kyth Hub.");
  const state = await invoke<InstallStatus>(command, { job });
  // Never present backend prose as a success: a job that is still running
  // after the cancel call (non-preemptable privileged work) must say so.
  if (state.state === "cancelled") return "Cancelled.";
  if (state.state === "running") return `Still running — ${state.detail}`;
  return state.detail;
}

async function cancelTracked(domain: JobDomain, command: string): Promise<string> {
  const job = inFlightJobs.get(domain);
  if (!job) return "Nothing to cancel.";
  return cancelBackendJob(command, job);
}

export const cancelGuardianCheck = (): Promise<string> => cancelTracked("guardian", "guardian_check_cancel");
export const cancelPrivilegedAction = (): Promise<string> => cancelTracked("privileged", "privileged_action_cancel");
export const cancelHubAction = (): Promise<string> => cancelTracked("hub-action", "hub_action_cancel");
export const cancelUpdateJob = (): Promise<string> => cancelTracked("update", "update_job_cancel");
export const cancelJob = (): Promise<string> => cancelTracked("job", "cancel_job");
export const cancelInstall = (): Promise<string> => cancelTracked("install", "install_cancel");
export const cancelSecurityJob = (): Promise<string> => cancelTracked("security", "security_job_cancel");
export const cancelGamingJob = (): Promise<string> => cancelTracked("gaming", "gaming_job_cancel");
export async function runGuardianControl(action: string): Promise<string> {
  if (!confirmUserAction(`Change Guardian setting: ${action}?`)) return "Cancelled.";
  const job = guardianJob(await invokeBounded<GuardianActionLaunch>("guardian_control", { action }, 90_000));
  return await waitGuardianCheck(job);
}

/** Shared confirmation boundary for actions that can change system state.
 * Tests and non-browser renders remain usable; the Tauri webview always has
 * the native browser confirm dialog. Never pass secret values in message. */
export function confirmUserAction(message: string): boolean {
  if (typeof window === "undefined" || typeof window.confirm !== "function") return true;
  return window.confirm(message);
}

type PrivilegedPayload = Record<string, string | boolean | number>;
interface PrivilegedActionLaunch { job: string; state: "running"; detail: string; }

function privilegedActionPrompt(operation: string, payload: PrivilegedPayload): string {
  switch (operation) {
    case "bitlocker_unlock":
      return `Unlock ${payload.device ?? "this BitLocker volume"}? The recovery key will be sent only to the local privileged service.`;
    case "kernel_switch":
      return `Stage the ${payload.flavor ?? "selected"} kernel? This changes the next boot deployment.`;
    case "secureboot_enroll":
      return "Enroll the KythOS Secure Boot key? This changes firmware trust configuration.";
    case "nvidia_install":
      return "Install the NVIDIA driver? This stages a system image change.";
    case "firmware_update":
      return "Apply firmware updates? The device may reboot during this operation.";
    case "network_share_add":
      return `Add network share ${typeof payload.name === "string" ? payload.name : ""}? Its credentials are sent only to the local privileged helper and saved in a protected root-owned file.`;
    case "network_share_remove":
      return `Remove network share ${typeof payload.name === "string" ? payload.name : ""}? This deletes its systemd mount unit and protected credentials.`;
    default:
      return `Run privileged operation ${operation}?`;
  }
}

export async function runPrivilegedAction(operation: string, payload: PrivilegedPayload = {}): Promise<string> {
  if (!confirmUserAction(privilegedActionPrompt(operation, payload))) return "Cancelled.";
  const launch = await invokeBounded<PrivilegedActionLaunch>("privileged_action", { operation, payload }, 90_000);
  if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "Privileged operation did not start.");
  const job = launch.job;
  trackJob("privileged", job);
  try {
    return resolveTerminalJob(await pollJobUntilSettled("privileged", job, {
      statusCommand: "privileged_action_status",
      limit: 1800,
      lostContactMessage: "Lost contact with the privileged operation; check the system status shortly.",
      timeoutMessage: "Privileged operation is still running; check the system status shortly.",
    }));
  } finally {
    untrackJob("privileged", job);
  }
}

// Mirrors kyth_shared.system.bootc_policy.branch_display_name() — small
// enough to duplicate as a presentation-only mapping here rather than
// round-trip through the bridge for display text.
const CHANNEL_DISPLAY: Record<string, string> = {
  latest: "Stable (latest)",
  testing: "Testing",
  "latest-cachy": "Stable + CachyOS kernel",
  "testing-cachy": "Testing + CachyOS kernel",
};

interface ProbeBridgeResponse<T = unknown> {
  key: string;
  data: T | null;
  error: string | null;
}

/** Generic disk-backed probe section read — see main.rs's probe_backend
 * command / kyth_shared::system::probe::read_section. Every probe_backend
 * caller below is this same call with a different key and a typed
 * reshape; this is just the shared plumbing. */
async function fetchProbeSection<T>(key: string): Promise<T | null> {
  if (!inTauriShell()) return null;
  // Invoke errors propagate out of the loader so sharedRead caches nothing:
  // a transient failure must not sit cached as null for the full TTL while
  // every section on that probe renders "No reading yet".
  try {
    return await sharedRead(`probe:${key}`, 10_000, async () => {
      const raw = await invoke<ProbeBridgeResponse<T>>("probe_backend", { section: key });
      return raw.data ?? null;
    });
  } catch {
    return null;
  }
}

export async function fetchUpdateChannel(): Promise<string | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invoke<string | null>("current_update_channel");
    if (!raw) return null;
    return CHANNEL_DISPLAY[raw] ?? raw;
  } catch {
    return null;
  }
}

interface HardwareBridgeResponse {
  gpu_line: string | null;
}

// Strips a raw `lspci -nn` line down to a display-sized name — best-effort
// only (lspci's format varies enough by vendor that a fully robust parse
// isn't realistic); falls back to the raw line untouched if the shape
// doesn't match what's stripped here, so nothing goes missing, just less
// tidy. Example input:
//   "03:00.0 VGA compatible controller [0300]: Advanced Micro Devices,
//    Inc. [AMD/ATI] Navi 31 [Radeon RX 7900 XT/7900 XTX] [1002:744c] (rev c8)"
function cleanGpuName(raw: string): string {
  return raw
    .replace(/^\S+\s+.*?\[[0-9a-f]{4}\]:\s*/i, "") // bus address + controller class + hex class code
    .replace(/\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]\s*$/i, "") // trailing vendor:device PCI id
    .replace(/\s*\(rev [0-9a-f]+\)\s*$/i, "") // trailing revision
    .trim();
}

export async function fetchGpuName(): Promise<string | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invoke<HardwareBridgeResponse>("hardware_snapshot");
    if (!raw.gpu_line) return null;
    return cleanGpuName(raw.gpu_line) || raw.gpu_line;
  } catch {
    return null;
  }
}

interface StorageBridgeResponse {
  free_bytes: number | null;
  total_bytes: number | null;
}

function formatGiB(bytes: number): string {
  return `${Math.round(bytes / 1024 ** 3)} GB`;
}

export async function fetchStorageFree(): Promise<string | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invoke<StorageBridgeResponse>("storage_snapshot");
    if (raw.free_bytes == null) return null;
    return formatGiB(raw.free_bytes);
  } catch {
    return null;
  }
}

// Shape of one `status.booted` / `status.rollback` entry in `bootc status
// --format=json`'s own output — see kyth_shared.system.bootc_query's
// fetch_status_data(), which is a bare parse of that command, no
// reshaping. Every field is optional: this is read straight off the
// disk-backed probe cache (see kyth_shared::system::probe::read_section),
// which only has this at all once kyth-probe.service has actually run on
// a real KythOS install —
// never on a plain dev checkout, which is the expected null case here.
export interface BootcDeployment {
  image?: string;
  version?: string;
  timestamp?: string;
  imageDigest?: string;
}

export interface BootcSnapshot {
  channel: string | null; // display name, e.g. "Testing"
  booted: BootcDeployment | null;
  rollback: BootcDeployment | null;
}

interface BootcStatusImage {
  image?: string | { image?: string; reference?: string; imageDigest?: string; digest?: string };
  reference?: string;
  version?: string;
  timestamp?: string;
  imageDigest?: string;
  digest?: string;
}

interface BootcStatusJsonEntry {
  image?: BootcStatusImage | string;
  version?: string;
  timestamp?: string;
  imageDigest?: string;
  digest?: string;
}

interface BootcStatusJson {
  status?: {
    booted?: BootcStatusJsonEntry;
    rollback?: BootcStatusJsonEntry;
  };
}

function deploymentFrom(entry: BootcStatusJsonEntry | undefined): BootcDeployment | null {
  const rawImage = entry?.image;
  if (!rawImage) return null;
  if (typeof rawImage === "string") {
    return {
      image: rawImage,
      version: entry.version,
      timestamp: entry.timestamp,
      imageDigest: entry.imageDigest ?? entry.digest,
    };
  }
  const nestedImage = typeof rawImage.image === "object" ? rawImage.image : null;
  const imageRef = typeof rawImage.image === "string"
    ? rawImage.image
    : nestedImage?.image ?? nestedImage?.reference ?? rawImage.reference;
  return {
    image: imageRef,
    version: entry.version ?? rawImage.version,
    timestamp: entry.timestamp ?? rawImage.timestamp,
    imageDigest: entry.imageDigest ?? rawImage.imageDigest ?? nestedImage?.imageDigest ?? rawImage.digest ?? nestedImage?.digest,
  };
}

export async function fetchBootcSnapshot(): Promise<BootcSnapshot | null> {
  if (!inTauriShell()) return null;
  return sharedRead("bootc-snapshot", 10_000, async () => {
    try {
      const [statusRaw, channelRaw] = await withTimeout(
        Promise.all([
          invoke<ProbeBridgeResponse>("probe_backend", { section: "bootc-status-data" }),
          invoke<ProbeBridgeResponse<string>>("probe_backend", { section: "bootc-branch" }),
        ]),
        "bootc-snapshot",
      );
      const data = statusRaw.data as unknown as BootcStatusJson | null;
      if (!data) return null;
      return {
        channel: channelRaw.data ? (CHANNEL_DISPLAY[channelRaw.data] ?? channelRaw.data) : null,
        booted: deploymentFrom(data.status?.booted),
        rollback: deploymentFrom(data.status?.rollback),
      };
    } catch {
      return null;
    }
  });
}

// kernel-flavor and nvidia-detect are both plain scalars already in
// DISK_TTL — no new backend needed, just fetchProbeSection with the right
// key and type.
export async function fetchKernelFlavor(): Promise<string | null> {
  return fetchProbeSection<string>("kernel-flavor");
}

export async function fetchNvidiaDetected(): Promise<boolean | null> {
  return fetchProbeSection<boolean>("nvidia-detect");
}

// Mirrors kyth_shared.system.probe's "network-summary" JSON-safe
// projection exactly (see probe.py's _collect_network_identity) — covers
// VPN, Network Shares, and Cloud Storage sections from one probe read.
export interface NetworkSummary {
  vpnConnected: boolean;
  vpnName: string;
  smbMounts: number;
  cloudProviders: string[];
  detail: string;
}

interface NetworkSummaryRaw {
  vpn_connected: boolean;
  vpn_name: string;
  smb_mounts: number;
  cloud_providers: string[];
  detail: string;
}

export async function fetchNetworkSummary(): Promise<NetworkSummary | null> {
  const raw = await fetchProbeSection<NetworkSummaryRaw>("network-summary");
  if (!raw) return null;
  return {
    vpnConnected: raw.vpn_connected,
    vpnName: raw.vpn_name,
    smbMounts: raw.smb_mounts,
    cloudProviders: raw.cloud_providers,
    detail: raw.detail,
  };
}

// Mirrors kyth_shared.system.controllers.detect_controllers()'s dict shape
// exactly — read from the disk-backed "controllers-detect" probe section
// (see probe.py's DISK_TTL), same as every fetchProbeSection call.
export interface ControllerInfo {
  usbControllers: { name: string; kind: string }[];
  inputNodeCount: number;
  driverLoaded: { xone: boolean; xpadneo: boolean; hidPlaystation: boolean };
}

interface ControllersDetectRaw {
  usb_controllers: [string, string][];
  input_nodes: string[];
  xone_loaded: boolean;
  xpadneo_loaded: boolean;
  hid_ps_loaded: boolean;
}

export async function fetchControllers(): Promise<ControllerInfo | null> {
  const raw = await fetchProbeSection<ControllersDetectRaw>("controllers-detect");
  if (!raw) return null;
  return {
    usbControllers: raw.usb_controllers.map(([name, kind]) => ({ name, kind })),
    inputNodeCount: raw.input_nodes.length,
    driverLoaded: { xone: raw.xone_loaded, xpadneo: raw.xpadneo_loaded, hidPlaystation: raw.hid_ps_loaded },
  };
}

// flatpak-apps and flatpak-updates are separate probe collectors with
// separate TTLs (see probe.py) — genuinely independent, so each stays
// nullable rather than collapsing a missing one to 0 (which would read as
// "zero updates" instead of "unknown").
export interface AppStoreSnapshot {
  installedCount: number | null;
  updatesAvailable: number | null;
}

export async function fetchAppStoreSnapshot(): Promise<AppStoreSnapshot | null> {
  const [apps, updates] = await Promise.all([
    fetchProbeSection<string[]>("flatpak-apps"),
    fetchProbeSection<number>("flatpak-updates"),
  ]);
  if (apps == null && updates == null) return null;
  return { installedCount: apps?.length ?? null, updatesAvailable: updates ?? null };
}

// Mirrors kyth_shared.system.probe's "hardware-summary" JSON-safe
// projection (see probe.py's _collect_hardware_view — deliberately not the
// raw HardwareView dataclass, which isn't JSON-serializable).
export interface HardwareSnapshot {
  gpuName: string | null;
  hasNvidia: boolean | null;
  isHybrid: boolean | null;
  capabilities: string[];
}

interface HardwareSummaryRaw {
  has_nvidia: boolean;
  is_hybrid: boolean;
  capabilities: string[];
}

export async function fetchHardwareSnapshot(): Promise<HardwareSnapshot | null> {
  try {
    const [gpuName, summary] = await withTimeout(
      Promise.all([
        fetchGpuName(),
        fetchProbeSection<HardwareSummaryRaw>("hardware-summary"),
      ]),
      "hardware-snapshot",
    );
    if (gpuName == null && summary == null) return null;
    return {
      gpuName,
      hasNvidia: summary?.has_nvidia ?? null,
      isHybrid: summary?.is_hybrid ?? null,
      capabilities: summary?.capabilities ?? [],
    };
  } catch {
    return null;
  }
}

// Mirrors main.rs's GuardianPendingResponse — the same
// pending_recommendations() list Hub's own mission bar/sidebar badge reads,
// now with a title (via RECIPES) and risk level attached for display.
export interface GuardianPendingItem {
  recipeId: string;
  title: string;
  detail: string;
  risk: string;
}

/** "3h ago" / "2d ago" style relative time — Guardian history stores raw
 * unix-seconds timestamps, formatting is a frontend presentation concern. */
export function relativeTime(unixSeconds: number): string {
  const diffMs = Date.now() - unixSeconds * 1000;
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

// Channels reuses bootc-branch (already cached for Update) — same data,
// different framing: ChannelSection shows the switcher state vs. Update's
// deployment view.
export async function fetchChannelRaw(): Promise<string | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string | null>("current_update_channel"); } catch { return null; }
}

// display-detect (capabilities/profiles) was collected but never readable
// via disk cache until the DISK_TTL fix above — now it's a normal
// fetchProbeSection like hardware-summary.
export interface DisplayDetect {
  capabilities: string[];
  profiles: string[];
}
export async function fetchDisplayDetect(): Promise<DisplayDetect | null> {
  return fetchProbeSection<DisplayDetect>("display-detect");
}

// ntfs-drives — other-system NTFS/BitLocker partitions from the native Rust
// probe cache (also written to the shared probe-cache.json so Hub can read it).
export interface NtfsDrive {
  dev: string;
  name: string;
  size: string;
  label: string;
  mount: string;
  is_bitlocker: boolean;
}
export async function fetchNtfsDrives(): Promise<NtfsDrive[] | null> {
  return fetchProbeSection<NtfsDrive[]>("ntfs-drives");
}

// audit-cache — 46-140 perf audit (gaming + scheduler + memory tunables)
// plus systemd-analyze line. Written by kyth_shared.perf_audit via
// update_sections({"audit-cache": data}); large, loosely-typed by design.
export type AuditCache = Record<string, unknown> & { ts?: number; systemd_analyze?: string; master?: string };
export async function fetchAuditCache(): Promise<AuditCache | null> {
  const raw = await fetchProbeSection<AuditCache>("audit-cache");
  if (!raw || typeof raw !== "object") return null;
  return raw;
}

// secureboot-state — the cheap disk-cached Secure Boot scalar. Read on
// mount; CompatibilitySection escalates to live mokutil (fetchMokStatus)
// only when the user asks, because mokutil is slow enough to stall a tab
// switch. The "firmware-cache" section is deliberately not wrapped —
// fetchFirmwareUpdatesCount is the readable form of the same thing.
export async function fetchSecurebootState(): Promise<string | null> {
  return fetchProbeSection<string>("secureboot-state");
}

// Just recipes — live `just --list` via Tauri (port of page_just.py).
// `params` is non-empty when the recipe takes arguments. The Hub only offers
// buttons for no-argument recipes until it has a safe, user-friendly form for
// choosing those arguments.
export interface JustRecipe { name: string; params: string; comment: string }
export interface HubActionLaunch { job: string; state: "running"; detail: string; }
export async function fetchJustList(): Promise<JustRecipe[] | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invoke<JustRecipe[]>("just_list");
    return raw ?? null;
  } catch { return null; }
}
// Recipes run as captured background jobs. KDE's graphical askpass helper is
// used by the Rust shell for sudo, so there is no terminal window to find or
// explain to a new user.
async function waitJustJob(job: string): Promise<string> {
  trackJob("hub-action", job);
  try {
    return resolveTerminalJob(await pollJobUntilSettled("hub-action", job, {
      statusCommand: "hub_action_status",
      limit: 1800,
      lostContactMessage: "Lost contact with this action; check the status here again in a moment.",
      timeoutMessage: "This action is still running; check the status here again in a moment.",
    }));
  } finally {
    untrackJob("hub-action", job);
  }
}

async function waitHubActionLaunch(launch: HubActionLaunch): Promise<string> {
  if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "Recipe did not start.");
  return await waitJustJob(launch.job);
}

export interface UpdateActionLaunch { job: string; state: "running"; detail: string; }

async function waitUpdateJob(job: string): Promise<string> {
  // Upgrade downloads can legitimately take an hour on a slow connection.
  trackJob("update", job);
  try {
    return resolveTerminalJob(await pollJobUntilSettled("update", job, {
      statusCommand: "update_job_status",
      limit: 7200,
      lostContactMessage: "Lost contact with the update; refresh the Updates page in a moment.",
      timeoutMessage: "The update is still running; refresh the Updates page in a moment.",
    }));
  } finally {
    untrackJob("update", job);
  }
}

async function waitUpdateLaunch(launch: UpdateActionLaunch): Promise<string> {
  if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "Update action did not start.");
  const detail = await waitUpdateJob(launch.job);
  invalidateSharedReads(
    "updates-snapshot",
    "bootc-snapshot",
    "pending-updates",
    "update-status",
    "update-health",
    "probe:bootc-status-data",
    "probe:bootc-branch",
    "probe:flatpak-updates",
  );
  return detail;
}

async function runHubAction(recipe: string): Promise<string> {
  if (!inTauriShell()) throw new Error("This action is only available in the Hub app.");
  return await waitHubActionLaunch(await invokeBounded<HubActionLaunch>("run_hub_action", { action: recipe }, 90_000));
}

export async function runHubRecipeAction(recipe: string): Promise<string> {
  return await runHubAction(recipe);
}

// Mok verify — live mokutil Secure Boot + enrollment (N40)
export interface MokStatus { sb_state: string; enrolled: string; }
export async function fetchMokStatus(): Promise<MokStatus | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<MokStatus>("mok_status"); } catch { return null; }
}

// Fonts ready — live fc-list check (N35)
export interface FontsReady { ready: boolean; detail: string; }
export async function fetchFontsReady(): Promise<FontsReady | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<FontsReady>("fonts_ready"); } catch { return null; }
}

// Mesa version — live glxinfo/rpm check (N41)
export async function fetchMesaVersion(): Promise<string | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string>("mesa_version"); } catch { return null; }
}
export async function fetchMesaOverlayDryRun(): Promise<{ ok: boolean; detail: string } | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<{ ok: boolean; detail: string }>("mesa_overlay_dry_run"); } catch { return null; }
}

// SMB — Aurora autodiscover parity (N33)
export async function fetchSmbBrowse(host?: string | null): Promise<{ ok: boolean; detail: string } | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<{ ok: boolean; detail: string }>("smb_browse", { host: host ?? null }); } catch { return null; }
}
export async function mountSmbShare(share: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Share mounting is available from the installed Kyth Hub.");
  return await invokeBounded<string>("smb_mount", { share }, 90_000);
}
export interface ConfiguredNetworkShare {
  name: string;
  server: string;
  share_path: string;
  mount_point: string;
  username: string;
  domain: string;
  auto_mount: boolean;
}
export interface NetworkShareInput extends ConfiguredNetworkShare {
  password: string;
  mount_now: boolean;
}
interface SmbActionResult { state: "complete"; detail: string; }
export async function fetchConfiguredNetworkShares(): Promise<ConfiguredNetworkShare[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<ConfiguredNetworkShare[]>("smb_configured_shares"); } catch { return null; }
}
export async function addNetworkShare(share: NetworkShareInput): Promise<string> {
  const detail = await runPrivilegedAction("network_share_add", { ...share });
  if (detail === "Cancelled.") return detail;
  const saved = await invokeBounded<SmbActionResult>("smb_save_configured_share", { share: {
    name: share.name, server: share.server, share_path: share.share_path,
    mount_point: share.mount_point, username: share.username, domain: share.domain,
    auto_mount: share.auto_mount,
  } }, 90_000);
  if (saved.state !== "complete") throw new Error(saved.detail || "Network share configuration was not saved.");
  return detail;
}
export async function removeNetworkShare(share: Pick<ConfiguredNetworkShare, "name" | "mount_point">): Promise<string> {
  const detail = await runPrivilegedAction("network_share_remove", { ...share });
  if (detail === "Cancelled.") return detail;
  const removed = await invokeBounded<SmbActionResult>("smb_remove_configured_share", { name: share.name }, 90_000);
  if (removed.state !== "complete") throw new Error(removed.detail || "Network share configuration was not removed.");
  return detail;
}

// Memory pressure + snapshot count (Diagnostics/Repair)
export async function fetchMemoryPressure(): Promise<{ status: string; detail: string } | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<{ status: string; detail: string }>("memory_pressure"); } catch { return null; }
}
export async function fetchSnapshotCount(): Promise<number | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<number>("snapshot_count"); } catch { return null; }
}
export interface SnapshotRow {
  id: string;
  timestamp: string;
  type: string;
  description: string;
  healthy?: boolean | null;
}
export async function fetchSnapshotTimeline(limit = 20): Promise<SnapshotRow[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<SnapshotRow[]>("snapshot_timeline", { limit }); } catch { return null; }
}

export async function fetchGamingSliceAvailable(): Promise<boolean | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<boolean>("is_gaming_slice_available"); } catch { return null; }
}

// Cloud OAuth + Printing (N36/N34)
export async function fetchCloudOauthStatus(): Promise<{ ok: boolean; detail: string } | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<{ ok: boolean; detail: string }>("cloud_oauth_status"); } catch { return null; }
}
export interface CloudSyncRemote {
  name: string;
  service: string;
  folder: string;
  last_sync: number | null;
  last_ok: boolean | null;
}
export async function fetchCloudSyncRemotes(): Promise<CloudSyncRemote[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<CloudSyncRemote[]>("cloud_sync_remotes"); } catch { return null; }
}
async function waitHubJob(job: string, limit = 7200): Promise<string> {
  trackJob("job", job);
  try {
    const state = await pollJobUntilSettled("job", job, {
      statusCommand: "job_status",
      limit,
      maxNulls: 10,
      lostContactMessage: "Lost contact with this action; check back in a moment.",
      timeoutMessage: "This action is still running; check back in a moment.",
    });
    if (state.state === "unknown") throw new Error("The background job is no longer known; it may have been cleared by a restart. Check back in a moment.");
    return resolveTerminalJob(state);
  } finally {
    untrackJob("job", job);
  }
}
export async function runCloudSync(remote: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Cloud sync is available from the installed Kyth Hub.");
  if (!confirmUserAction(`Copy ${remote} to its saved local folder? Files already here are kept; overwritten ones are backed up first.`)) return "Cancelled.";
  return await waitHubJob(await invokeBounded<string>("cloud_sync_now", { remote }, 90_000));
}
export async function openBackupApp(): Promise<string> {
  if (!inTauriShell()) throw new Error("Backup is available from the installed Kyth Hub.");
  return await invoke<string>("open_backup_app");
}
export async function openCloudStorageApp(): Promise<string> {
  if (!inTauriShell()) throw new Error("The full Cloud Storage workflow is available from the installed Kyth Hub.");
  return await invoke<string>("open_cloud_storage_app");
}
export async function openMoveFilesApp(): Promise<string> {
  if (!inTauriShell()) throw new Error("The full migration workflow is available from the installed Kyth Hub.");
  return await invoke<string>("open_move_files_app");
}
export interface MigrationReadiness { bookmarks: string; drives: string; files: string; onedrive: string; pwa: string; parity: string; }
export async function fetchMigrationReadiness(): Promise<MigrationReadiness | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<MigrationReadiness>("migration_readiness"); } catch { return null; }
}
export async function openNetworkSharesApp(): Promise<string> {
  if (!inTauriShell()) throw new Error("The full Network Shares workflow is available from the installed Kyth Hub.");
  return await invoke<string>("open_network_shares_app");
}
export async function fetchPrinterDiscover(): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("ipp_discover"); } catch { return null; }
}

// Btrfs + drivers (Repair/Hardware)
export async function fetchBtrfsHealth(): Promise<{ status: string; detail: string } | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<{ status: string; detail: string }>("btrfs_health"); } catch { return null; }
}
export async function fetchPciByClass(deviceClass: string): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("pci_devices_by_class", { class: deviceClass }); } catch { return null; }
}

// Controllers live detect (lsusb + lsmod)
export interface ControllersLive { usb_controllers: [string,string][]; input_nodes: string[]; xone_dongle: boolean; xone_loaded: boolean; xpadneo_loaded: boolean; hid_ps_loaded: boolean; dualsense_found: boolean; }
export async function fetchControllersLive(): Promise<ControllersLive | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<ControllersLive>("controllers_detect"); } catch { return null; }
}

// Hardware view summary — canonical ProbeService cached view (30s)
export interface HardwareViewSummary { has_nvidia: boolean; is_hybrid: boolean; capabilities: string[]; }
export async function fetchHardwareViewSummary(): Promise<HardwareViewSummary | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<HardwareViewSummary>("hardware_view_summary"); } catch { return null; }
}

// Network identity live (VPN/SMB/cloud) — live nmcli + mounts, reshaped to
// the same NetworkSummary the cached "network-summary" probe read returns
// so the three Move In sections can swap one for the other. Mount reads the
// cache; a Refresh button reads this.
interface NetworkIdentityLive { vpn_connected: boolean; vpn_name: string; smb_mounts: number; cloud_providers: string[]; detail: string; }
async function fetchNetworkIdentityLive(): Promise<NetworkIdentityLive | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<NetworkIdentityLive>("network_identity"); } catch { return null; }
}

export async function fetchNetworkSummaryLive(): Promise<NetworkSummary | null> {
  const raw = await fetchNetworkIdentityLive();
  if (!raw) return null;
  return {
    vpnConnected: raw.vpn_connected,
    vpnName: raw.vpn_name,
    smbMounts: raw.smb_mounts,
    cloudProviders: raw.cloud_providers,
    detail: raw.detail,
  };
}

export async function openVpnApp(): Promise<string> {
  if (!inTauriShell()) throw new Error("Native VPN controls are available from the installed Kyth Hub.");
  return await invoke<string>("open_vpn_app");
}
export async function startVpnConnection(profile: { gateway: string; protocol: string; osEmulation: string; username: string; password: string }): Promise<string> {
  if (!inTauriShell()) throw new Error("VPN connections require the installed Kyth Hub.");
  // The Tauri binding is snake_case (`os_emulation`): map the camelCase
  // profile field at the boundary or the invoke fails to deserialize.
  const { gateway, protocol, osEmulation, username, password } = profile;
  const job = await invokeBounded<string>("vpn_connect", { gateway, protocol, os_emulation: osEmulation, username, password }, 90_000);
  // Tracked like every other cancellable job: Disconnect/Cancel keeps reaching
  // the real backend job after a reload via the reattached slot, and a second
  // connect is rejected while one owns the domain. Untracked when the
  // section's poller observes a terminal state (see untrackVpnJob).
  trackJob("vpn", job);
  return job;
}
export interface VpnConnectionStatus { id: string; state: "connecting" | "authentication_required" | "connected" | "disconnected" | "failed" | "complete" | "failed_lockdown" | "failed_lockdown_open" | "connected_firewall_open" | "complete_firewall_open" | "unknown"; detail: string; }
export async function fetchVpnConnectionStatus(job: string): Promise<VpnConnectionStatus | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<VpnConnectionStatus>("vpn_status", { job }); } catch { return null; }
}
export async function disconnectVpnConnection(job: string): Promise<string> {
  if (!inTauriShell()) throw new Error("VPN connections require the installed Kyth Hub.");
  try {
    return await invokeBounded<string>("vpn_disconnect", { job }, 90_000);
  } finally {
    untrackJob("vpn", job);
  }
}
/** Release the tracked VPN job without disconnecting. Called when the
 * section poller observes a terminally-dead state (failed/disconnected):
 * the tunnel is gone, so Cancel has nothing to reach. Live states —
 * connecting/authentication_required/connected — stay tracked so Disconnect
 * keeps working, including after a reload via the reattached slot. */
export function untrackVpnJob(job: string): void {
  untrackJob("vpn", job);
}
/** Cancel/Disconnect entry point for the tracked VPN job. vpn_disconnect
 * returns a plain string (not the InstallStatus shape cancelBackendJob
 * expects), so the vpn domain resolves its slot here instead of through
 * cancelTracked. Returns "Nothing to cancel." with no tracked job, matching
 * every other domain's cancel contract. */
export async function cancelVpnConnection(): Promise<string> {
  const job = inFlightJobs.get("vpn");
  if (!job) return "Nothing to cancel.";
  return disconnectVpnConnection(job);
}
export interface VpnSavedProfile { gateway: string; protocol: string; os: string; }
export interface VpnProtectionStatus { vpn_fail_closed: boolean; vpn_dns_exclusive: boolean; firewall_zone: string; }
export async function fetchVpnProtectionStatus(): Promise<VpnProtectionStatus | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<VpnProtectionStatus>("vpn_protection_status"); } catch { return null; }
}
export async function setVpnProtection(protection: { vpnFailClosed: boolean; vpnDnsExclusive: boolean }): Promise<string> {
  if (!inTauriShell()) throw new Error("VPN protection toggles require the installed Kyth Hub.");
  // The Tauri binding is snake_case: map camelCase fields at the boundary.
  return await invokeBounded<string>("set_vpn_protection", { vpn_fail_closed: protection.vpnFailClosed, vpn_dns_exclusive: protection.vpnDnsExclusive }, 90_000);
}
export async function fetchVpnSavedProfile(): Promise<VpnSavedProfile | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<VpnSavedProfile | null>("vpn_saved_profile"); } catch { return null; }
}

// Updates unified — bootc/flatpak/firmware summary
export async function fetchPendingUpdatesSummary(): Promise<Record<string,string> | null> {
  if (!inTauriShell()) return null;
  return sharedRead("pending-updates", 15_000, async () => {
    try { return await invoke<Record<string,string>>("pending_updates_summary"); } catch { return null; }
  });
}

// PipeWire quantum presets (N32)
export async function fetchAudioPresets(): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("available_audio_presets"); } catch { return null; }
}
export async function applyPipewireQuantum(preset: string, dryRun = false): Promise<{ ok: boolean; detail: string } | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<{ ok: boolean; detail: string }>("apply_pipewire_quantum", { preset, dryRun }); } catch { return null; }
}

// Deployment history — bootc timeline (Repair)
export interface DeploymentInfo { section: string; label: string; available: boolean; reference?: string | null; branch?: string | null; timestamp?: string | null; digest?: string | null; short_digest?: string | null; status_text: string; }
export async function fetchDeploymentHistory(): Promise<DeploymentInfo[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<DeploymentInfo[]>("deployment_history"); } catch { return null; }
}

// Recovery status — staged/rollback/quarantined single view (Repair)
export interface RecoveryStatus { has_staged: boolean; has_rollback: boolean; quarantined_digest: string; quarantine_detail: string; watcher_staged: boolean; clear_quarantine_cmd: string; last_rollback_error: string; banner: string; }
export async function fetchRecoveryStatus(): Promise<RecoveryStatus | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<RecoveryStatus>("recovery_status"); } catch { return null; }
}

// Update status — TTL-bounded check_state (Updates)
export interface UpdateStatusLive { booted?: string | null; staged: boolean; rollback: boolean; remote_digest?: string | null; blocked_reason?: string | null; retry_cmd?: string | null; check_state: string; detail: string; }
export async function fetchUpdateStatus(): Promise<UpdateStatusLive | null> {
  if (!inTauriShell()) return null;
  return sharedRead("update-status", 10_000, async () => {
    try { return await invoke<UpdateStatusLive>("update_status"); } catch { return null; }
  });
}

export interface UpdateHealthLive { status: string; pending_digest: string; last_healthy_digest: string; failures: number; quarantined: number; detail: string; }
export async function fetchUpdateHealth(): Promise<UpdateHealthLive | null> {
  if (!inTauriShell()) return null;
  return sharedRead("update-health", 10_000, async () => {
    try { return await invoke<UpdateHealthLive>("update_health"); } catch { return null; }
  });
}

export interface UpdatesSnapshot {
  snapshot: BootcSnapshot | null;
  status: UpdateStatusLive | null;
  pending: Record<string, string> | null;
  health: UpdateHealthLive | null;
}

// One page-level owner for the Updates read model. All update facts are
// loaded together so the page cannot render a mix of old and new states.
export async function fetchUpdatesSnapshot(): Promise<UpdatesSnapshot> {
  return sharedRead("updates-snapshot", 10_000, async () => {
    const [snapshot, status, pending, health] = await Promise.all([
      fetchBootcSnapshot(),
      fetchUpdateStatus(),
      fetchPendingUpdatesSummary(),
      fetchUpdateHealth(),
    ]);
    return { snapshot, status, pending, health };
  });
}

// Process helpers — live session + ansi + disk bytes
export async function fetchIsLiveSession(): Promise<boolean | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<boolean>("is_live_session"); } catch { return null; }
}

// Firmware — fwupd counts (Hardware)
export async function fetchFirmwareUpdatesCount(): Promise<number | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<number>("firmware_updates_count"); } catch { return null; }
}

// Plasma HDR/VRR presets
export async function fetchPlasmaPresets(): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("plasma_presets"); } catch { return null; }
}

// Update availability check (Hub-side 90s deadline, issue #164)
export interface AvailabilityStatusLive { state: string; detail: string; flatpak_count: number; flatpak_detail: string; staged: boolean; manifest_raw: string; blocked_reason: string; }
/** Run the user-requested availability check without hiding an invoke error.
 * The explicit button press needs to tell the page why it could not run so
 * the user gets a useful next step instead of a misleading shell message. */
let availabilityCheckInFlight: Promise<AvailabilityStatusLive> | null = null;
export async function checkForUpdates(): Promise<AvailabilityStatusLive> {
  if (!inTauriShell()) throw new Error("Update checking is available from the installed Kyth Hub.");
  // Single-flight: the backend probe cannot be cancelled mid-invoke, so a
  // second press while one check runs joins it instead of stacking another
  // registry fan-out against a dead mirror.
  if (availabilityCheckInFlight) return availabilityCheckInFlight;
  const task = (async (): Promise<AvailabilityStatusLive> => {
    // The backend check fans out to the update registry and can hang on a
    // dead mirror past the Hub-side 90s deadline (issue #164): race the
    // invoke against a 95s timer so the button always settles with a
    // friendly, actionable error instead of spinning forever.
    let timer: ReturnType<typeof globalThis.setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = globalThis.setTimeout(() => reject(new Error("The update check timed out; your current system has not changed. Check your connection and try again.")), 95_000);
    });
    try {
      return await Promise.race([
        invoke<AvailabilityStatusLive>("collect_availability", {
          branch: null,
          useCached: false,
        }),
        timeout,
      ]);
    } finally {
      if (timer !== undefined) globalThis.clearTimeout(timer);
    }
  })();
  availabilityCheckInFlight = task;
  try {
    return await task;
  } finally {
    if (availabilityCheckInFlight === task) availabilityCheckInFlight = null;
  }
}

// Drives — live `lsblk -J` blockdevices (Move In's "Rescan drives"). The
// cached fetchNtfsDrives above is what the section reads on mount; this is
// the escalation when the user has just plugged something in. Typed to the
// lsblk column set get_ntfs_devices() asks for, not `any`.
export interface NtfsDevice {
  name?: string;
  fstype?: string | null;
  label?: string | null;
  uuid?: string | null;
  mountpoint?: string | null;
  children?: NtfsDevice[];
}
export async function fetchNtfsDevices(): Promise<NtfsDevice[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<NtfsDevice[]>("ntfs_devices"); } catch { return null; }
}

// Boot runtime + desktop stack + updater (final reads)
export interface BootRuntimeCheck { name: string; passed: boolean; detail: string; }
export interface TelemetrySession {
  game_name: string;
  started_at: number | null;
  duration_s: number | null;
  avg_fps: number | null;
  p1_low_fps: number | null;
  stutter_count: number;
  scheduler: string;
  avg_latency_ms: number | null;
  p99_latency_ms: number | null;
}

export async function fetchTelemetryRecent(limit = 7): Promise<TelemetrySession[] | null> {
  if (!inTauriShell()) return null;
  return sharedRead(`telemetry:${limit}`, 10_000, async () => {
    try {
      const rows = await invoke<TelemetrySession[]>("telemetry_recent", { limit });
      return rows;
    } catch {
      return null;
    }
  });
}

export interface CompatibilityGame {
  name: string;
  anticheat: string;
  status: "native" | "proton" | "tweaks" | "blocked";
  note: string;
  checked: string;
  source: string;
  source_url: string;
}

export async function fetchCompatibilityGames(): Promise<CompatibilityGame[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<CompatibilityGame[]>("compatibility_games"); } catch { return null; }
}


export interface LauncherEntry { id: string; label: string; installed: boolean; library_count: number | null; path: string; }
export async function fetchGamingLibrary(): Promise<LauncherEntry[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<LauncherEntry[]>("gaming_library"); } catch { return null; }
}
export interface StarterPack { name: string; desc: string; apps: { id: string; label: string; selected: boolean; description: string }[]; }
export async function fetchStarterPacks(): Promise<StarterPack[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<StarterPack[]>("starter_packs"); } catch { return null; }
}

export async function fetchBootRuntimeChecks(): Promise<BootRuntimeCheck[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<BootRuntimeCheck[]>("boot_runtime_checks"); } catch { return null; }
}

// Current user's display name for the dashboard greeting. Empty string
// means "no name available" — callers greet without a name rather than
// substituting a placeholder person.
export async function fetchUserName(): Promise<string | null> {
  if (!inTauriShell()) return null;
  try {
    const name = await invoke<string>("current_user_name");
    return name.trim() ? name : null;
  } catch { return null; }
}

// Phase 2 mutating (Updates + Repair/Diagnostics)
export interface StageProgress {
  pct: number;
  phase: string;
  detail: string;
  active: boolean;
}

export async function fetchStageProgress(): Promise<StageProgress | null> {
  if (!inTauriShell()) return null;
  try {
    return await invoke<StageProgress>("stage_progress");
  } catch { return null; }
}
export async function invokeBootcUpgrade(): Promise<string> {
  if (!inTauriShell()) throw new Error("not in Tauri");
  if (!confirmUserAction("Download and stage the next system update? It will require a reboot to apply.")) return "Cancelled.";
  return await waitUpdateLaunch(await invoke<UpdateActionLaunch>("bootc_upgrade"));
}
export async function invokeBootcRollback(): Promise<string> {
  if (!inTauriShell()) throw new Error("not in Tauri");
  if (!confirmUserAction("Roll back to the previous system deployment? This changes the next boot target.")) return "Cancelled.";
  return await waitUpdateLaunch(await invoke<UpdateActionLaunch>("bootc_rollback"));
}
export async function invokeApplyStaged(): Promise<string> {
  if (!inTauriShell()) throw new Error("not in Tauri");
  if (!confirmUserAction("Restart now to apply the staged system update?")) return "Cancelled.";
  return await waitUpdateLaunch(await invoke<UpdateActionLaunch>("apply_staged"));
}
export async function invokeBootcSwitchBranch(branch: string): Promise<string> {
  if (!inTauriShell()) throw new Error("not in Tauri");
  if (!confirmUserAction(`Switch the system update channel to ${branch}? This stages a new deployment.`)) return "Cancelled.";
  return await waitUpdateLaunch(await invoke<UpdateActionLaunch>("bootc_switch_branch", { branch }));
}
export async function invokeGuardianExecute(recipeId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("not in Tauri");
  if (!confirmUserAction(`Run Guardian fix ${recipeId}? It may change system configuration.`)) return "Cancelled.";
  return await invokeBounded<string>("guardian_execute_recipe", { recipeId }, 90_000);
}
export async function dismissGuardianRecommendation(recipeId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("not in Tauri");
  return await invoke<string>("guardian_dismiss", { recipeId });
}

// Plasma HDR/VRR presets — apply_plasma_preset is the mutating half of the
// pair fetchPlasmaPresets lists (same shape as the PipeWire pair above).
export async function applyPlasmaPreset(preset: string, dryRun = false): Promise<{ ok: boolean; detail: string } | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<{ ok: boolean; detail: string }>("apply_plasma_preset", { preset, dryRun }); } catch { return null; }
}

// Driver/desktop introspection (Hardware, Desktop & displays).
export async function fetchLoadedKernelModules(): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("loaded_kernel_modules"); } catch { return null; }
}
export interface DesktopStackCheck { name: string; passed: boolean; detail: string; advisory: boolean; }
export async function fetchDesktopStackChecks(): Promise<DesktopStackCheck[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<DesktopStackCheck[]>("desktop_stack_checks"); } catch { return null; }
}
// "Windows app -> Flatpak" chooser backing the App Store search box.
export interface FamiliarApp { windows_name: string; description: string; flatpak_id: string }
export async function fetchFamiliarApps(): Promise<FamiliarApp[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<FamiliarApp[]>("familiar_apps"); } catch { return null; }
}

export interface AppStreamApp { id: string; name: string; summary: string; icon_url: string }
export interface AppImageEntry { name: string; path: string; executable: boolean }
export interface InstallStatus { id: string; state: "running" | "complete" | "failed" | "unknown" | "cancelled"; detail: string }
export async function searchAppStream(query: string): Promise<AppStreamApp[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<AppStreamApp[]>("appstream_search", { query }); } catch { return null; }
}
export async function fetchAppImages(): Promise<AppImageEntry[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<AppImageEntry[]>("appimage_list"); } catch { return null; }
}

export interface InstalledFlatpak { id: string; name: string; version: string; branch: string; arch: string; scope: "user" | "system"; icon_url: string }
interface InstallActionLaunch { job: string; state: "running"; detail: string; }
export async function fetchInstalledFlatpaks(): Promise<InstalledFlatpak[] | null> {
  if (!inTauriShell()) return null;
  return sharedRead("installed-flatpaks", 15_000, async () => {
    try { return await invoke<InstalledFlatpak[]>("installed_flatpaks"); } catch { return null; }
  });
}
export async function makeAppImageExecutable(path: string): Promise<string> {
  if (!inTauriShell()) throw new Error("AppImage actions are available from the installed Kyth Hub.");
  return await invoke<string>("make_appimage_executable", { path });
}
export async function importAppImage(path: string): Promise<string> {
  if (!inTauriShell()) throw new Error("AppImage actions are available from the installed Kyth Hub.");
  return await invoke<string>("import_appimage", { path });
}
export async function uninstallFlatpak(id: string): Promise<string> {
  if (!inTauriShell()) throw new Error("App installs are available from the installed Kyth Hub.");
  if (!confirmUserAction(`Uninstall ${id}? This removes the application from this system.`)) return "Cancelled.";
  const launch = await invoke<InstallActionLaunch>("uninstall_flatpak", { appId: id });
  if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "Uninstall did not start.");
  const job = launch.job;
  trackJob("install", job);
  try {
    const state = await pollJobUntilSettled("install", job, {
      statusCommand: "install_status",
      limit: 120,
      lostContactMessage: "Lost contact with the uninstall; refresh Flatpak in a moment.",
      timeoutMessage: "Uninstall is still running; refresh Flatpak in a moment.",
    });
    if (state.state === "complete") return state.detail;
    throw new Error(state.detail);
  } finally {
    untrackJob("install", job);
  }
}
export async function launchAppImage(path: string): Promise<string> {
  if (!inTauriShell()) throw new Error("AppImage actions are available from the installed Kyth Hub.");
  return await invoke<string>("launch_appimage", { path });
}
export async function updateFlatpaks(): Promise<string> {
  if (!inTauriShell()) throw new Error("App installs are available from the installed Kyth Hub.");
  const launch = await invoke<InstallActionLaunch>("update_flatpaks");
  if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "App updates did not start.");
  // Both Flatpak scopes are bounded server-side, but metadata refresh and
  // large app/runtime updates can still take several minutes. Keep this poll
  // limit above the helper timeout rather than turning a slow update into a
  // false failure.
  trackJob("install", launch.job);
  try {
    const state = await pollJobUntilSettled("install", launch.job, {
      statusCommand: "install_status",
      limit: 7200,
      lostContactMessage: "Lost contact with the app update; refresh status in a moment.",
      timeoutMessage: "App updates are still running. Refresh status in a moment.",
    });
    if (state.state === "complete") {
      invalidateSharedReads("updates-snapshot", "installed-flatpaks", "pending-updates", "probe:flatpak-apps", "probe:flatpak-updates");
      return state.detail;
    }
    throw new Error(state.detail);
  } finally {
    untrackJob("install", launch.job);
  }
}
export async function installFlatpak(appId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("App installs are available from the installed Kyth Hub.");
  const launch = await invoke<InstallActionLaunch>("install_flatpak", { appId });
  if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "Install did not start.");
  return launch.job;
}
export async function fetchInstallStatus(id: string): Promise<InstallStatus | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<InstallStatus>("install_status", { job: id }); } catch { return null; }
}

/** Shared install-job waiter for the App Store, Repair, and Work Setup
 * sections. Registers the job in the install domain so its Cancel button
 * stops the actual running backend job. */
export async function waitInstallJob(job: string, limit = 120): Promise<string> {
  trackJob("install", job);
  let settled = false;
  try {
    // Null probes are tolerated to the limit here (same as before): the UI
    // wait may expire while the backend job still runs.
    const state = await pollJobUntilSettled("install", job, {
      statusCommand: "install_status",
      limit,
      maxNulls: Number.POSITIVE_INFINITY,
      lostContactMessage: "Lost contact with the install; refresh Apps in a moment.",
      timeoutMessage: "Installation is still running; refresh Apps in a moment.",
    });
    settled = true;
    return resolveTerminalJob(state);
  } catch (error) {
    // The UI wait expired but the backend job is still running: leave it
    // tracked so Cancel still reaches it and a later status check reattaches.
    if (error instanceof Error && error.message === "Installation is still running; refresh Apps in a moment.") throw error;
    settled = true;
    throw error;
  } finally {
    if (settled) untrackJob("install", job);
  }
}

// ---------------------------------------------------------------------
// Security tab: Kali distrobox lifecycle + host-side (Flatpak) tools grid.
// Kali create/export/remove run as background jobs (security_job_status),
// same running/complete/failed shape as installFlatpak/uninstallFlatpak
// above — polled longer since a "kali-linux-everything" pull can run many
// minutes. Reported status text, not a live percentage; see
// kyth-shared-rs's security_container module doc for why.
// ---------------------------------------------------------------------

export async function fetchKaliStatus(): Promise<boolean | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<boolean>("kali_status"); } catch { return null; }
}

export interface SecHostTool { flatpak: string; name: string; desc: string; installed: boolean }
export async function fetchSecHostTools(): Promise<SecHostTool[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<SecHostTool[]>("sec_host_tools"); } catch { return null; }
}

async function pollSecurityJob(job: string, maxIterations: number): Promise<string> {
  trackJob("security", job);
  try {
    const state = await pollJobUntilSettled("security", job, {
      statusCommand: "security_job_status",
      limit: maxIterations,
      baseIntervalMs: 3000,
      maxNulls: 10,
      lostContactMessage: "Lost contact with the security job; check back in a moment.",
      timeoutMessage: "Still running; check back in a moment.",
    });
    if (state.state === "unknown") throw new Error("The security job is no longer known; it may have been cleared by a restart. Check back in a moment.");
    return resolveTerminalJob(state);
  } finally {
    untrackJob("security", job);
  }
}
interface SecurityActionLaunch { job: string; state: "running"; detail: string; }
function securityJob(launch: SecurityActionLaunch): string { if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "Security action did not start."); return launch.job; }

export async function createKaliBox(tier: "headless" | "default" | "everything"): Promise<string> {
  if (!confirmUserAction(`Create the Kali box (${tier} tools)? This pulls a container image and installs packages — it may take several minutes, longer for "everything".`)) return "Cancelled.";
  const job = securityJob(await invoke<SecurityActionLaunch>("kali_create", { tier }));
  return await pollSecurityJob(job, 600); // up to 30 minutes
}
export async function exportKaliApps(): Promise<string> {
  const job = securityJob(await invoke<SecurityActionLaunch>("kali_export", {}));
  return await pollSecurityJob(job, 100); // up to 5 minutes
}
export async function removeKaliBox(): Promise<string> {
  if (!confirmUserAction("Remove the Kali distrobox container? Files in your home directory are not affected.")) return "Cancelled.";
  const job = securityJob(await invoke<SecurityActionLaunch>("kali_remove", {}));
  return await pollSecurityJob(job, 60); // up to 3 minutes
}
export async function enterKaliTerminal(): Promise<string> {
  if (!inTauriShell()) throw new Error("Security tools are available from the installed Kyth Hub.");
  return await invoke<string>("kali_enter_terminal");
}

export async function installSecHostTool(flatpakId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Security tools are available from the installed Kyth Hub.");
  const job = securityJob(await invoke<SecurityActionLaunch>("sec_host_tool_install", { flatpakId }));
  return await pollSecurityJob(job, 240); // up to 12 minutes
}
export async function uninstallSecHostTool(flatpakId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Security tools are available from the installed Kyth Hub.");
  if (!confirmUserAction("Remove this tool?")) return "Cancelled.";
  const job = securityJob(await invoke<SecurityActionLaunch>("sec_host_tool_uninstall", { flatpakId }));
  return await pollSecurityJob(job, 60);
}
export async function launchSecHostTool(flatpakId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Security tools are available from the installed Kyth Hub.");
  return await invoke<string>("sec_host_tool_launch", { flatpakId });
}

// ---------------------------------------------------------------------
// Gaming tab: the install/launch/uninstall tool grid, the two one-shot
// Flatpak permission fixes (Discord screen share, OBS PipeWire capture),
// and the first-failure playbook / Fix My Game folder shortcuts. Mirrors
// page_gaming_tools_grid.py / page_gaming_fixes.py.
// ---------------------------------------------------------------------

export interface GamingTool { flatpak: string; name: string; desc: string; installed: boolean }
export async function fetchGamingTools(): Promise<GamingTool[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<GamingTool[]>("gaming_tools"); } catch { return null; }
}

async function pollGamingJob(job: string, maxIterations: number): Promise<string> {
  trackJob("gaming", job);
  try {
    const state = await pollJobUntilSettled("gaming", job, {
      statusCommand: "gaming_job_status",
      limit: maxIterations,
      baseIntervalMs: 3000,
      maxNulls: 10,
      lostContactMessage: "Lost contact with the gaming job; check back in a moment.",
      timeoutMessage: "Still running; check back in a moment.",
    });
    if (state.state === "unknown") throw new Error("The gaming job is no longer known; it may have been cleared by a restart. Check back in a moment.");
    return resolveTerminalJob(state);
  } finally {
    untrackJob("gaming", job);
  }
}
interface GamingActionLaunch { job: string; state: "running"; detail: string; }
function gamingJob(launch: GamingActionLaunch): string { if (launch.state !== "running" || !launch.job) throw new Error(launch.detail || "Gaming action did not start."); return launch.job; }

export async function installGamingTool(flatpakId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Gaming tools are available from the installed Kyth Hub.");
  const job = gamingJob(await invoke<GamingActionLaunch>("gaming_tool_install", { flatpakId }));
  return await pollGamingJob(job, 240); // up to 12 minutes
}
export async function uninstallGamingTool(flatpakId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Gaming tools are available from the installed Kyth Hub.");
  if (!confirmUserAction("Remove this tool?")) return "Cancelled.";
  const job = gamingJob(await invoke<GamingActionLaunch>("gaming_tool_uninstall", { flatpakId }));
  return await pollGamingJob(job, 60);
}
export async function launchGamingTool(flatpakId: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Gaming tools are available from the installed Kyth Hub.");
  return await invoke<string>("gaming_tool_launch", { flatpakId });
}

export async function fixDiscordScreenshare(): Promise<string> {
  if (!inTauriShell()) throw new Error("Gaming tools are available from the installed Kyth Hub.");
  return await invoke<string>("fix_discord_screenshare");
}
export async function fixObsPipewire(): Promise<string> {
  if (!inTauriShell()) throw new Error("Gaming tools are available from the installed Kyth Hub.");
  return await invoke<string>("fix_obs_pipewire");
}
export async function openGameFolder(key: "compatdata" | "shadercache"): Promise<string> {
  if (!inTauriShell()) throw new Error("Gaming tools are available from the installed Kyth Hub.");
  return await invoke<string>("open_game_folder", { key });
}

// ---------------------------------------------------------------------
// Overlays / sched-ext / per-game profile builder — page_gaming_tools_perf.py.
// ---------------------------------------------------------------------

export interface GamingPerfStatus { mangohud_installed: boolean; gamescope_installed: boolean; vkbasalt_installed: boolean }
export async function fetchGamingPerfStatus(): Promise<GamingPerfStatus | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<GamingPerfStatus>("gaming_perf_status"); } catch { return null; }
}

export interface ScxStatus { active: boolean; configured: string }
export async function fetchScxStatus(): Promise<ScxStatus | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<ScxStatus>("scx_status"); } catch { return null; }
}
export async function fetchScxAvailable(): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("scx_available"); } catch { return null; }
}
export async function setScxScheduler(scheduler: "rusty" | "lavd" | "bpfland" | "stop"): Promise<string> {
  if (!inTauriShell()) throw new Error("Gaming tools are available from the installed Kyth Hub.");
  const job = await invoke<string>("scx_set_scheduler", { scheduler });
  trackJob("gaming", job);
  try {
    const state = await pollJobUntilSettled("gaming", job, {
      statusCommand: "gaming_job_status",
      limit: 20,
      baseIntervalMs: 1500,
      maxNulls: 10,
      lostContactMessage: "Lost contact with the scheduler change; check back in a moment.",
      timeoutMessage: "Still running; check back in a moment.",
    });
    if (state.state === "unknown") throw new Error("The scheduler change is no longer known; it may have been cleared by a restart. Check back in a moment.");
    return resolveTerminalJob(state);
  } finally {
    untrackJob("gaming", job);
  }
}

export interface GameProfile { profile: string; hdr: boolean; fps: string; prime: boolean }
export async function fetchPerGameProfile(appid: string): Promise<GameProfile | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<GameProfile>("per_game_profile", { appid }); } catch { return null; }
}
export async function savePerGameProfile(appid: string, profile: string, hdr: boolean, fps: string, prime: boolean): Promise<string> {
  if (!inTauriShell()) throw new Error("Gaming tools are available from the installed Kyth Hub.");
  return await invoke<string>("save_per_game_profile", { appid, profile, hdr, fps, prime });
}
export async function fetchPerGameLaunchOptions(appid: string): Promise<string | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string>("per_game_launch_options", { appid }); } catch { return null; }
}
export interface ProtonDbResult { app_id: string; tier: string; detail: string }
export interface AntiCheatEntry { game: string; status: string; detail: string }
export async function fetchProtonDbMany(appIds: string[]): Promise<ProtonDbResult[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<ProtonDbResult[]>("protondb_lookup_many", { appIds }); } catch { return null; }
}
export async function fetchAntiCheatTable(): Promise<AntiCheatEntry[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<AntiCheatEntry[]>("anti_cheat_table"); } catch { return null; }
}

/** Feedback's send path — opens a prefilled kyth-os/kyth issue via
 * xdg-open. Throws like the other mutating wrappers so useSectionAction
 * can surface the failure. */
export async function invokeOpenFeedbackIssue(title: string, body: string): Promise<string> {
  if (!inTauriShell()) throw new Error("not in Tauri");
  return await invoke<string>("open_feedback_issue", { title, body });
}

// Work Setup parity: fixed Microsoft 365 web apps, PST discovery/import, and
// a timed sleep-inhibited focus session. The catalog is intentionally fixed;
// no arbitrary URL or command is accepted from the webview.
export async function openM365App(name: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Microsoft 365 shortcuts are available from the installed Kyth Hub.");
  return await invoke<string>("open_m365_app", { name });
}
export async function createM365Shortcuts(): Promise<string> {
  if (!inTauriShell()) throw new Error("Microsoft 365 shortcuts are available from the installed Kyth Hub.");
  return await invoke<string>("create_m365_shortcuts");
}
export async function fetchPstFiles(): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("pst_files"); } catch { return null; }
}
export async function convertPst(path: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Outlook import is available from the installed Kyth Hub.");
  const job = await invoke<string>("convert_pst", { path });
  return await waitHubJob(job, 3600);
}
export async function startFocusSession(minutes: number): Promise<string> {
  if (!inTauriShell()) throw new Error("Focus sessions are available from the installed Kyth Hub.");
  return await invoke<string>("focus_start", { minutes });
}
export async function stopFocusSession(id: string): Promise<string> {
  if (!inTauriShell()) throw new Error("Focus sessions are available from the installed Kyth Hub.");
  return await invoke<string>("focus_stop", { id });
}

// Downloaded executable / RPM MIME-handler workflow.  The native launcher
// supplies the path; these wrappers are deliberately narrow so the webview
// never receives a generic process or filesystem bridge.
export interface ExeHandlerCompatibility {
  level: "likely" | "unknown" | "unsupported";
  summary: string;
  detail: string;
}
export interface ExeHandlerInspection {
  path: string;
  basename: string;
  is_rpm: boolean;
  app_name: string | null;
  suggestion: string;
  flatpak_id: string | null;
  search_term: string;
  compatibility: ExeHandlerCompatibility | null;
  sha256_prefix: string | null;
  sha256_full: string | null;
  trusted_direct: boolean;
  auto_bottles: boolean;
}
export interface ExeHandlerJob { job: string; state: "running" | "complete" | "failed" | "unknown" | "cancelled"; detail: string; }

export async function takePendingExeHandler(): Promise<string | null> {
  if (!inTauriShell()) return null;
  return await invoke<string | null>("take_pending_exe_handler");
}
export async function inspectExeHandler(path: string): Promise<ExeHandlerInspection> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  return await invoke<ExeHandlerInspection>("exe_handler_inspect", { path });
}
export interface FirstbootAppsStatus { state: string; message: string; updated: string; }
export interface SteamPlayStatus { steam_present: boolean; steam_running: boolean; mapping_present: boolean; detail: string; }
export async function fetchSteamPlayStatus(): Promise<SteamPlayStatus | null> {
  if (!inTauriShell()) return null;
  try {
    return await invoke<SteamPlayStatus>("steam_play_status");
  } catch { return null; }
}
export async function fetchFirstbootAppsStatus(): Promise<FirstbootAppsStatus | null> {
  if (!inTauriShell()) return null;
  try {
    return await invoke<FirstbootAppsStatus>("firstboot_apps_status");
  } catch { return null; }
}
export async function trustExeHandlerFile(sha256: string, name: string, runner: "bottles" | "umu"): Promise<void> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  await invoke("exe_handler_trust", { sha256, name, runner });
}
export async function untrustExeHandlerFile(sha256: string): Promise<void> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  await invoke("exe_handler_untrust", { sha256 });
}
export async function launchExeHandlerUmu(path: string): Promise<void> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  await invoke("exe_handler_launch_umu", { path });
}
export async function setExeHandlerAutoBottles(enabled: boolean): Promise<void> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  await invoke("exe_handler_set_auto_bottles", { enabled });
}
export async function openExeHandlerFlathub(searchTerm: string): Promise<void> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  await invoke("exe_handler_open_flathub", { searchTerm });
}
export async function isExeHandlerFlatpakInstalled(appId: string): Promise<boolean> {
  if (!inTauriShell()) return false;
  return await invoke<boolean>("exe_handler_flatpak_installed", { appId });
}
export async function launchExeHandlerFlatpak(appId: string): Promise<void> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  await invoke("exe_handler_launch_flatpak", { appId });
}
export async function startExeHandlerFlatpakInstall(appId: string): Promise<ExeHandlerJob> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  return await invoke<ExeHandlerJob>("install_flatpak", { appId });
}
export async function startExeHandlerBottles(path: string, allowUnsupported: boolean): Promise<ExeHandlerJob> {
  if (!inTauriShell()) throw new Error("Installer help is available from the installed Kyth Hub.");
  return await invoke<ExeHandlerJob>("exe_handler_start_bottles", { path, allowUnsupported });
}

/** Cancel a running Bottles provisioning job. The backend job lives in the
 * shared app-installs store (launch_in_bottles is a library call, so cancel
 * marks it and its late finish becomes a no-op) — reachable through the
 * install_cancel command. */
export async function cancelExeHandlerBottles(job: string): Promise<string> {
  return cancelBackendJob("install_cancel", job);
}
