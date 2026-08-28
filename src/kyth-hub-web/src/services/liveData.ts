import { invoke } from "@tauri-apps/api/core";
import { inTauriShell } from "./tauriEnv";

// Real backend data, read through the Tauri shell's bridge commands (see
// src-tauri/src/main.rs, which calls straight into the kyth-shared Rust
// crate — src/kyth-shared-rs — no subprocess). Every function here
// returns null rather than throwing when the data isn't available —
// running in a plain browser (npm run dev), no Tauri build, or (very
// commonly on a dev machine) no on-disk state yet because kyth-probe /
// Guardian have never run. Callers fall back to the existing mock fixtures
// on null, same "prototype during migration" posture as mockDashboard.ts —
// the difference here is these paths are real when the data exists,
// not always-mock.

export interface GuardianHistoryItem {
  timestamp: number;
  title: string;
  detail: string;
  status: "ok" | "warn" | "error";
}

export interface GuardianSnapshot {
  pendingCount: number;
  pending: GuardianPendingItem[];
  history: GuardianHistoryItem[];
}

// Mirrors main.rs's GuardianSnapshotResponse shape exactly.
interface GuardianBridgeHistoryItem {
  timestamp: number;
  title: string;
  detail: string;
  action: string;
  verified: boolean | null;
}
interface GuardianBridgePendingItem {
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
    const raw = await invoke<GuardianBridgeResponse>("guardian_snapshot");
    return {
      pendingCount: raw.pending_count,
      pending: raw.pending,
      history: raw.history.map((item) => ({
        timestamp: item.timestamp,
        title: item.title,
        detail: item.detail,
        status: statusFor(item),
      })),
    };
  } catch {
    return null;
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
  try {
    const raw = await invoke<ProbeBridgeResponse<T>>("probe_backend", { section: key });
    return raw.data ?? null;
  } catch {
    return null;
  }
}

export async function fetchUpdateChannel(): Promise<string | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invoke<ProbeBridgeResponse<string>>("probe_backend", { section: "bootc-branch" });
    if (!raw.data) return null;
    return CHANNEL_DISPLAY[raw.data] ?? raw.data;
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

interface BootcStatusJsonEntry {
  image?: { image?: { image?: string }; version?: string; timestamp?: string; imageDigest?: string };
}

interface BootcStatusJson {
  status?: {
    booted?: BootcStatusJsonEntry;
    rollback?: BootcStatusJsonEntry;
  };
}

function deploymentFrom(entry: BootcStatusJsonEntry | undefined): BootcDeployment | null {
  const img = entry?.image;
  if (!img) return null;
  return {
    image: img.image?.image,
    version: img.version,
    timestamp: img.timestamp,
    imageDigest: img.imageDigest,
  };
}

export async function fetchBootcSnapshot(): Promise<BootcSnapshot | null> {
  if (!inTauriShell()) return null;
  try {
    const [statusRaw, channelRaw] = await Promise.all([
      invoke<ProbeBridgeResponse>("probe_backend", { section: "bootc-status-data" }),
      invoke<ProbeBridgeResponse<string>>("probe_backend", { section: "bootc-branch" }),
    ]);
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
  const [gpuName, summary] = await Promise.all([
    fetchGpuName(),
    fetchProbeSection<HardwareSummaryRaw>("hardware-summary"),
  ]);
  if (gpuName == null && summary == null) return null;
  return {
    gpuName,
    hasNvidia: summary?.has_nvidia ?? null,
    isHybrid: summary?.is_hybrid ?? null,
    capabilities: summary?.capabilities ?? [],
  };
}

// Mirrors main.rs's GuardianPendingResponse — the same
// pending_recommendations() list Hub's own mission bar/sidebar badge reads,
// now with a title (via RECIPES) and risk level attached for display.
export interface GuardianPendingItem {
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
  return fetchProbeSection<string>("bootc-branch");
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

// ntfs-drives — other-system NTFS/BitLocker partitions from lsblk, via
// probe_cached("ntfs-drives") in kyth_welcome/services/hardware/drives.py
// (also written to the shared probe-cache.json so Hub can read it).
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

// secureboot-state + firmware-cache — small scalars, same DISK_TTL family.
export async function fetchSecurebootState(): Promise<string | null> {
  return fetchProbeSection<string>("secureboot-state");
}
export async function fetchFirmwareCache(): Promise<unknown | null> {
  return fetchProbeSection<unknown>("firmware-cache");
}

// Just recipes — live `just --list` via Tauri (port of page_just.py).
export interface JustRecipe { name: string; comment: string }
export async function fetchJustList(): Promise<JustRecipe[] | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invoke<JustRecipe[]>("just_list");
    return raw ?? null;
  } catch { return null; }
}
export async function runJustRecipe(recipe: string): Promise<boolean | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invoke<{ launched: boolean }>("just_run", { recipe });
    return raw.launched;
  } catch { return null; }
}

// bootc_policy — pure presentation helpers now in Rust (was TS CHANNEL_DISPLAY duplicate)
export async function fetchBranchDisplayName(tag: string | null): Promise<string | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string>("branch_display_name", { tag }); } catch { return null; }
}
export interface UpdateAvailabilityView { card_style: string; icon_text: string; icon_style: string; title: string; body: string; update_btn_visible: boolean; restart_btn_visible: boolean; }
export async function fetchUpdateAvailabilityView(args: { staged: boolean; check_state: string; flatpak_count: number; check_ts: string; check_ts_details: string; staged_ts?: string | null }): Promise<UpdateAvailabilityView | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<UpdateAvailabilityView>("update_availability_view", args); } catch { return null; }
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
export async function fetchSmbMountCommand(share: string): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("smb_mount_command", { share }); } catch { return null; }
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

// Gaming slice — per-game cgroup wrapper
export async function fetchGamingSliceCommand(argv: string[], useUser?: boolean | null): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("gaming_slice_command", { argv, useUser: useUser ?? null }); } catch { return null; }
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
export async function fetchPrinterDiscover(): Promise<string[] | null> {
  if (!inTauriShell()) return null;
  try { return await invoke<string[]>("ipp_discover"); } catch { return null; }
}
