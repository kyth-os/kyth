import { invoke } from "@tauri-apps/api/core";
import { inTauriShell } from "./tauriEnv";

// Real backend data, read through the Tauri shell's bridge commands (see
// src-tauri/src/main.rs + src-tauri/backend/*.py). Every function here
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
  history: GuardianHistoryItem[];
}

// Mirrors backend/guardian_bridge.py's JSON output shape exactly.
interface GuardianBridgeHistoryItem {
  timestamp: number;
  title: string;
  detail: string;
  action: string;
  verified: boolean | null;
}
interface GuardianBridgeResponse {
  pending_count: number;
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

interface ProbeBridgeResponse {
  key: string;
  data: string | null;
  error: string | null;
}

export async function fetchUpdateChannel(): Promise<string | null> {
  if (!inTauriShell()) return null;
  try {
    const raw = await invoke<ProbeBridgeResponse>("probe_backend", { section: "bootc-branch" });
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
