import type { Config, Disk, FreeRegion, InstallRequest, InstallerEvent, Partition, PendingOperation, RescueProbe, TransactionReport } from "./types";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { inTauriShell } from "./services/tauriEnv";

declare global { interface Window { __KYTH_SESSION_TOKEN__?: string; } }

interface InstallerConnection {
  base_url: string;
  bootstrap_token: string;
  session_token: string;
  transport: "http" | "unix";
  socket_path?: string;
}

interface InstallerNativeResponse {
  status: number;
  body: string;
}

let connection: InstallerConnection | null = null;
let connectionPromise: Promise<void> | null = null;

/**
 * Bootstrap the embedded UI against the root-owned Rust installer daemon once.
 * The HTTP bootstrap fetch below only runs on the dev-loopback transport; the
 * packaged Unix-socket transport authenticates via the session token instead.
 */
/**
 * fetch with a cleared-on-settle timeout (ES2020-safe: no
 * AbortSignal.timeout). A hung daemon surfaces an error instead of hanging
 * the installer forever. A caller-supplied signal wins over the timeout.
 */
async function fetchBounded(url: string, init: RequestInit | undefined, ms: number, label: string): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: init?.signal ?? controller.signal });
  } catch (error) {
    if (init?.signal == null && error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`${label} did not respond; the installer backend may be stuck.`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function ensureConnection(): Promise<void> {
  if (!inTauriShell() || connection) return;
  if (!connectionPromise) {
    connectionPromise = invoke<InstallerConnection>("installer_connection").then(async (value) => {
      if (value.transport === "http") {
        // Bearer header, never the query string: a token in the URL lands
        // in daemon access logs, proxy logs, history, and crash reports.
        const response = await fetchBounded(
          `${value.base_url}/`,
          {
            headers: {
              Accept: "application/json",
              Authorization: `Bearer ${value.bootstrap_token}`,
            },
          },
          30_000,
          "Installer backend bootstrap",
        );
        if (!response.ok) throw new Error(`Installer backend bootstrap failed (${response.status})`);
      }
      connection = value;
    });
    // A failed bootstrap must not brick the UI until reload: drop the
    // rejected promise so the next action re-attempts bootstrap.
    connectionPromise = connectionPromise.catch((error: unknown) => {
      if (!connection) connectionPromise = null;
      throw error;
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
  let status: number;
  let text: string;
  if (connection?.transport === "unix") {
    const native = await invoke<InstallerNativeResponse>("installer_request", {
      method: init?.method ?? "GET",
      path,
      body: typeof init?.body === "string" ? init.body : null,
    });
    status = native.status;
    text = native.body;
  } else {
    const response = await fetchBounded(apiUrl(path), {
      ...init,
      headers,
      credentials: inTauriShell() ? "omit" : "same-origin",
    }, 60_000, `Installer request ${path}`);
    status = response.status;
    text = await response.text();
  }
  let payload: unknown = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = text;
  }
  if (status < 200 || status >= 300) {
    const record = typeof payload === "object" && payload !== null ? payload as Record<string, unknown> : {};
    const message = record.message ?? record.error ?? (text || `Request failed (${status})`);
    throw new InstallerApiError(status, String(message), payload);
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
  log: () => request<string>("/api/log"),
  rescueProbe: async () => {
    const probe = await request<RescueProbe>("/api/rescue/probe");
    const status = probe.transaction?.status;
    if (inTauriShell() && status) {
      const guidance = await invoke<NonNullable<RescueProbe["rescue_guidance"]>>("installer_recovery_guidance", { status });
      probe.rescue_guidance = guidance;
    }
    return probe;
  },
  validatePlan: async (body: InstallRequest): Promise<void> => {
    if (inTauriShell()) await invoke("installer_validate_plan", { request: body });
  },
  start: (body: InstallRequest) => post<{ started: boolean }>("/api/start", body),
  cancel: () => post<{ ok: boolean; message?: string }>("/api/cancel", {}),
  reboot: () => post<{ ok: boolean }>("/api/reboot", {}),
  rescueLogsToUsb: (usb_mount?: string) => post<{ ok: boolean; dest?: string; copied?: string[]; message?: string }>("/api/rescue/logs-to-usb", { usb_mount }),
  newTable: (disk: string, table_type: "gpt" | "msdos") => post("/api/disk/new-table", { disk, table_type }),
  createPartition: (body: Record<string, unknown>) => post("/api/disk/create", body),
  deletePartition: (disk: string, partition: string) => post("/api/disk/delete", { disk, partition }),
  resizePartition: (disk: string, partition: string, new_size_bytes: number, attest?: { gpt_backup_path?: string; ntfs_verified_clean?: boolean; on_ac_power?: boolean }) => post("/api/disk/resize", { disk, partition, new_size_bytes, ...attest }),
  formatPartition: (disk: string, partition: string, fs_type: string, label: string) => post("/api/disk/format", { disk, partition, fs_type, label }),
  setMountpoint: (disk: string, partition: string, mountpoint: string) => post("/api/disk/set-mountpoint", { disk, partition, mountpoint }),
  removePending: (disk: string, index: number) => post("/api/disk/pending/remove", { disk, index }),
  commitPartitions: (disk: string) => post<{ ok: boolean; root_partition?: string; errors?: string[] }>("/api/disk/commit", { disk }),
  rollbackPartitions: (disk: string) => post("/api/disk/rollback", { disk }),
};

export function subscribeToInstallEvents(onEvent: (event: InstallerEvent) => void, onDisconnect: () => void): () => void {
  let source: EventSource | undefined;
  let closed = false;
  let unlistenEvent: (() => void) | undefined;
  let unlistenError: (() => void) | undefined;
  void ensureConnection().then(() => {
    if (closed) return;
    if (connection?.transport === "unix") {
      void Promise.all([
        listen<InstallerEvent>("installer-event", (event) => onEvent(event.payload)),
        listen<string>("installer-stream-error", () => onDisconnect()),
      ]).then(([removeEvent, removeError]) => {
        if (closed) {
          removeEvent();
          removeError();
          return;
        }
        unlistenEvent = removeEvent;
        unlistenError = removeError;
        return invoke("installer_stream");
      }).catch(() => onDisconnect());
      return;
    }
    // EventSource cannot set a header, so this read-only stream relies on
    // the HttpOnly bootstrap cookie (sent via withCredentials) — the
    // session token deliberately never appears in the URL, keeping it out
    // of request lines, devtools, and proxy logs. Mutating requests use
    // the X-Kyth-Session-Token header below.
    const streamPath = "/api/stream";
    source = new EventSource(apiUrl(streamPath), { withCredentials: true });
    source.onmessage = (message) => {
      try { onEvent(JSON.parse(message.data) as InstallerEvent); } catch {
        source?.close();
        onDisconnect();
      }
    };
    source.onerror = () => {
      source?.close();
      onDisconnect();
    };
  }).catch(onDisconnect);
  return () => {
    closed = true;
    source?.close();
    unlistenEvent?.();
    unlistenError?.();
    if (connection?.transport === "unix") void invoke("installer_stream_stop").catch(() => undefined);
  };
}
