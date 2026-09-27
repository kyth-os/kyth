/** True once the page is actually running inside the Tauri shell (main.rs),
 * false in a plain browser tab during `npm run dev` — every Tauri-only code
 * path (deep links, live backend data) is a no-op off that path, so the web
 * app still runs standalone. */
export function inTauriShell(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}
