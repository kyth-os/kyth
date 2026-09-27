import { invoke } from "@tauri-apps/api/core";
import { inTauriShell } from "./tauriEnv";

/** The installed-image guest enables this channel with an environment flag.
 * All calls are best-effort so browser/dev launches never depend on it. */
export async function hubAcceptanceMode(): Promise<boolean> {
  if (!inTauriShell()) return false;
  try { return await invoke<boolean>("acceptance_mode"); } catch { return false; }
}

export async function degradedDashboardAcceptance(): Promise<boolean> {
  if (!inTauriShell()) return false;
  try { return await invoke<boolean>("acceptance_degraded_dashboard"); } catch { return false; }
}

export async function recordHubAcceptance(event: string, detail: string): Promise<void> {
  if (!inTauriShell()) return;
  try { await invoke("acceptance_record", { event, detail }); } catch { /* normal launch */ }
}
