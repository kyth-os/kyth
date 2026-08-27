import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { inTauriShell } from "./services/tauriEnv";

// Mirrors web_shell.py's _ROUTE_FOR_PAGE table (the QWebEngineView-shell
// prototype this replaces) — same page-key contract the current Qt Hub's
// page_registry.py keys use, just consumed here instead of on the Python
// side. Kept on the TS side, not duplicated in Rust, since the router
// already owns "what routes exist" (see App.tsx).
const ROUTE_FOR_PAGE: Record<string, string> = {
  Welcome: "/",
  Play: "/play",
  Apps: "/apps",
  "This PC": "/this-pc",
  "Move In": "/move-in",
};

function navigateToPage(page: string): void {
  // HashRouter, not history-API routing (see main.tsx) — this is the
  // entire deep-link contract with the shell: one string, one convention.
  window.location.hash = ROUTE_FOR_PAGE[page] ?? "/";
}

/** Call once from main.tsx before the first render settles. Handles both
 * halves of the shell's deep-link contract (main.rs's PendingPage /
 * "navigate" event, see that file's comments for why they're split):
 * the page this process launched with (pulled once, avoiding a race
 * against this listener not being registered yet), and any later
 * single-instance activation (pushed as an event once we're already up). */
export async function installDeepLinkHandling(): Promise<void> {
  if (!inTauriShell()) return;

  const pending = await invoke<string | null>("take_pending_page");
  if (pending) navigateToPage(pending);

  await listen<string>("navigate", (event) => navigateToPage(event.payload));
}
