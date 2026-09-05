import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { inTauriShell } from "./services/tauriEnv";
import { recordHubAcceptance } from "./services/acceptance";
import { DESTINATIONS } from "./data/destinations";

// Builds the page-key route table from the shared manifest. Kept on the TS
// side, not duplicated in Rust, since the router
// already owns "what routes exist" (see App.tsx).
//
// The 21 section keys are derived from the shared hubRoutes.json manifest
// rather than written out again here. Packaging-time KRunner entries use the
// same manifest, so adding a section updates both launch surfaces together.
function buildRouteTable(): Record<string, string> {
  const table: Record<string, string> = { Welcome: "/" };
  for (const { key: dest, route, sections } of DESTINATIONS) {
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

// Legacy aliases fold onto Welcome before dispatching; unknown keys already
// fall back to "/" below, so these exist
// to keep the contract explicit rather than accidental.
const WELCOME_ALIASES = new Set(["home", "hub", "kyth hub", "system hub", "pulse", "kyth pulse"]);

export function routeForPage(page: string): string {
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

function navigateToPage(page: string, source: "initial" | "single-instance"): void {
  // HashRouter, not history-API routing (see main.tsx) — this is the
  // entire deep-link contract with the shell: one string, one convention.
  const route = routeForPage(page);
  window.location.hash = route;
  void recordHubAcceptance("deep-link", JSON.stringify({ page: page.trim(), route, source }));
}

/** Call once from main.tsx before the first render settles. Handles both
 * halves of the shell's deep-link contract (main.rs's PendingPage /
 * "navigate" event, see that file's comments for why they're split):
 * the page this process launched with (pulled once, avoiding a race
 * against this listener not being registered yet), and any later
 * single-instance activation (pushed as an event once we're already up). */
export async function installDeepLinkHandling(): Promise<void> {
  if (!inTauriShell()) return;

  // Register before resolving the initial page. The acceptance harness (and
  // real desktop launchers) can issue a second invocation as soon as the
  // initial telemetry is recorded; registering afterward creates a narrow
  // lost-event window for the single-instance `navigate` callback.
  await listen<string>("navigate", (event) => navigateToPage(event.payload, "single-instance"));

  const pending = await invoke<string | null>("take_pending_page");
  if (pending) navigateToPage(pending, "initial");
}
