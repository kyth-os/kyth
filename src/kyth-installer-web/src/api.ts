import type { Config, Disk, FreeRegion, InstallRequest, InstallerEvent, Partition, PendingOperation, RescueProbe, TransactionReport } from "./types";
import { invoke } from "@tauri-apps/api/core";
import { inTauriShell } from "./services/tauriEnv";

declare global { interface Window { __KYTH_SESSION_TOKEN__?: string; } }

interface InstallerConnection {
  base_url: string;
  bootstrap_token: string;
  session_token: string;
}

let connection: InstallerConnection | null = null;
let connectionPromise: Promise<void> | null = null;

/** Bootstrap the embedded UI against the root-owned Python backend once. */
async function ensureConnection(): Promise<void> {
  if (!inTauriShell() || connection) return;
  if (!connectionPromise) {
    connectionPromise = invoke<InstallerConnection>("installer_connection").then(async (value) => {
      const response = await fetch(`${value.base_url}/?bootstrap_token=${encodeURIComponent(value.bootstrap_token)}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`Installer backend bootstrap failed (${response.status})`);
      connection = value;
    });
  }
  await connectionPromise;
}

function apiUrl(path: string): string {
  return `${connection?.base_url ?? ""}${path}`;
}

export class InstallerApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly details?: unknown) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await ensureConnection();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const token = connection?.session_token ?? window.__KYTH_SESSION_TOKEN__;
  if (token) headers.set("X-Kyth-Session-Token", token);
  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    credentials: inTauriShell() ? "omit" : "same-origin",
  });
  const text = await response.text();
  let payload: unknown = text;
  try { payload = text ? JSON.parse(text) : {}; } catch { /* preserve plain-text errors */ }
  if (!response.ok) {
    const record = typeof payload === "object" && payload !== null ? payload as Record<string, unknown> : {};
    const message = record.message ?? record.error ?? (text || `Request failed (${response.status})`);
    throw new InstallerApiError(response.status, String(message), payload);
  }
  return payload as T;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const installerApi = {
  config: () => request<Config>("/api/config"),
  disks: () => request<Disk[]>("/api/disks"),
  partitions: (disk: string) => request<Partition[]>(`/api/partitions?disk=${encodeURIComponent(disk)}`),
  freeSpace: (disk: string) => request<FreeRegion[]>(`/api/free-space?disk=${encodeURIComponent(disk)}`),
  timezones: () => request<string[]>("/api/timezones"),
  locales: () => request<string[]>("/api/locales"),
  keymaps: () => request<string[]>("/api/keymaps"),
  pending: () => request<PendingOperation[]>("/api/disk/pending"),
  filesystems: () => request<Array<{ id: string; name?: string }>>("/api/disk/filesystems"),
  report: () => request<TransactionReport>("/api/report"),
  rescueProbe: () => request<RescueProbe>("/api/rescue/probe"),
  start: (body: InstallRequest) => post<{ started: boolean }>("/api/start", body),
  cancel: () => post<{ ok: boolean; message?: string }>("/api/cancel", {}),
  reboot: () => post<{ ok: boolean }>("/api/reboot", {}),
  rescueLogsToUsb: (usb_mount?: string) => post<{ ok: boolean; dest?: string; copied?: string[]; message?: string }>("/api/rescue/logs-to-usb", { usb_mount }),
  newTable: (disk: string, table_type: "gpt" | "msdos") => post("/api/disk/new-table", { disk, table_type }),
  createPartition: (body: Record<string, unknown>) => post("/api/disk/create", body),
  deletePartition: (disk: string, partition: string) => post("/api/disk/delete", { disk, partition }),
  resizePartition: (disk: string, partition: string, new_size_bytes: number) => post("/api/disk/resize", { disk, partition, new_size_bytes }),
  formatPartition: (disk: string, partition: string, fs_type: string, label: string) => post("/api/disk/format", { disk, partition, fs_type, label }),
  setMountpoint: (disk: string, partition: string, mountpoint: string) => post("/api/disk/set-mountpoint", { disk, partition, mountpoint }),
  removePending: (disk: string, index: number) => post("/api/disk/pending/remove", { disk, index }),
  commitPartitions: (disk: string) => post<{ ok: boolean; root_partition?: string; errors?: string[] }>("/api/disk/commit", { disk }),
  rollbackPartitions: (disk: string) => post("/api/disk/rollback", { disk }),
};

export function subscribeToInstallEvents(onEvent: (event: InstallerEvent) => void, onDisconnect: () => void): () => void {
  let source: EventSource | undefined;
  let closed = false;
  void ensureConnection().then(() => {
    if (closed) return;
    // EventSource cannot set a header; use the session token in the URL for
    // this read-only stream. Mutating requests always use the header below.
    const streamToken = connection?.session_token;
    const streamPath = streamToken
      ? `/api/stream?session_token=${encodeURIComponent(streamToken)}`
      : "/api/stream";
    source = new EventSource(apiUrl(streamPath), { withCredentials: true });
    source.onmessage = (message) => {
      try { onEvent(JSON.parse(message.data) as InstallerEvent); } catch { onDisconnect(); source?.close(); }
    };
    source.onerror = () => onDisconnect();
  }).catch(onDisconnect);
  return () => { closed = true; source?.close(); };
}
