import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { inTauriShell } from "./services/tauriEnv";
import {
  APPS_SECTIONS,
  MOVE_IN_SECTIONS,
  PLAY_SECTIONS,
  THIS_PC_SECTIONS,
  type HubSection,
} from "./data/hubSections";

// Mirrors web_shell.py's _ROUTE_FOR_PAGE table (the QWebEngineView-shell
// prototype this replaces) — same page-key contract the current Qt Hub's
// page_registry.py keys use, just consumed here instead of on the Python
// side. Kept on the TS side, not duplicated in Rust, since the router
// already owns "what routes exist" (see App.tsx).
//
// The 21 section keys are derived from hubSections.ts rather than written
// out again here: krunner_desktop.py ships a .desktop entry per page key
// and 23-kyth-helper-ctx-installs.sh ships `--page "App Store"`, so a key
// this table misses doesn't error — it silently lands on Home. Deriving
// keeps that from happening the next time a section is added.
const DESTINATIONS: Array<[key: string, route: string, sections: HubSection[]]> = [
  ["Play", "/play", PLAY_SECTIONS],
  ["Apps", "/apps", APPS_SECTIONS],
  ["This PC", "/this-pc", THIS_PC_SECTIONS],
  ["Move In", "/move-in", MOVE_IN_SECTIONS],
];

function buildRouteTable(): Record<string, string> {
  const table: Record<string, string> = { Welcome: "/" };
  for (const [dest, route, sections] of DESTINATIONS) {
    table[dest] = route;
    // HubPage reads ?section= (see its useSearchParams call) — a section is
    // a tab within its destination, not a route of its own.
    for (const section of sections) {
      table[section.key] = `${route}?section=${encodeURIComponent(section.key)}`;
    }
  }
  return table;
}

const ROUTE_FOR_PAGE = buildRouteTable();

// page_registry.py's resolve_page_key() folds these onto Welcome before
// dispatching; unknown keys already fall back to "/" below, so these exist
// to keep the contract explicit rather than accidental.
const WELCOME_ALIASES = new Set(["home", "hub", "kyth hub", "system hub", "pulse", "kyth pulse"]);

function routeForPage(page: string): string {
  const text = page.trim();
  if (!text) return "/";
  if (text in ROUTE_FOR_PAGE) return ROUTE_FOR_PAGE[text];

  const lowered = text.toLowerCase();
  if (WELCOME_ALIASES.has(lowered)) return "/";
  // resolve_page_key() also matches rail entries case-insensitively by
  // title, so "guardian" reaches the same tab "Guardian" does.
  for (const [key, route] of Object.entries(ROUTE_FOR_PAGE)) {
    if (key.toLowerCase() === lowered) return route;
  }
  return "/";
}

function navigateToPage(page: string): void {
  // HashRouter, not history-API routing (see main.tsx) — this is the
  // entire deep-link contract with the shell: one string, one convention.
  window.location.hash = routeForPage(page);
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
