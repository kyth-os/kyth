// Tauri shell for the Kyth Hub web frontend — the Rust replacement for
// web_shell.py's QWebEngineView window (see that file's module docstring
// for why a native shell exists at all: same single-instance + --page
// deep-link contract the current PySide6 Hub has, just hosting the React
// build instead of a QWidget tree).
//
// Scope, deliberately: this swaps the *shell* only. kyth_shared (the ~200
// module Python library that does the actual host tuning) stays Python —
// see backend/probe_bridge.py for how this process reaches it. Porting
// kyth_shared itself to Rust is a separate, much bigger decision for
// later, not something this file assumes.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;

use tauri::{Emitter, Manager};

/// Compile-time location of this crate (src-tauri/) — used only to derive
/// dev-tree-relative defaults below, same spirit as web_shell.py's
/// `_static_root()`: a source-tree-relative path for now, replaced with a
/// real installed path once this ships (see that function's comment).
const MANIFEST_DIR: &str = env!("CARGO_MANIFEST_DIR");

/// Page-key -> nothing here; route mapping now lives on the TS side
/// (src/deepLink.ts) since the router already owns that table — this
/// process only extracts the raw `--page <key>` argument and forwards it
/// unchanged, whether that's at first launch (via `take_pending_page`) or
/// on a later single-instance activation (via the "navigate" event).
struct PendingPage(Mutex<Option<String>>);

fn extract_page_arg<S: AsRef<str>>(argv: &[S]) -> Option<String> {
    argv.iter()
        .position(|a| a.as_ref() == "--page")
        .and_then(|i| argv.get(i + 1))
        .map(|s| s.as_ref().to_string())
}

fn default_kyth_shared_pythonpath() -> PathBuf {
    // src/kyth-hub-web/src-tauri -> src/kyth_shared (contains the
    // importable `kyth_shared` package). Dev-tree default only, same as
    // web_shell.py's KYTH_HUB_WEB_DIST override pattern below.
    PathBuf::from(MANIFEST_DIR)
        .join("..")
        .join("..")
        .join("kyth_shared")
}

fn bridge_script_path(name: &str) -> PathBuf {
    PathBuf::from(MANIFEST_DIR).join("backend").join(name)
}

/// Shells out to one backend/*.py bridge script with PYTHONPATH pointed at
/// kyth_shared, parses its single-line JSON stdout. Shared by every bridge
/// command below — each script owns its own read-only contract with
/// kyth_shared (see their docstrings), this just runs the process.
fn run_bridge(script: &str, args: &[&str]) -> Result<serde_json::Value, String> {
    let pythonpath = std::env::var_os("KYTH_SHARED_PYTHONPATH")
        .map(PathBuf::from)
        .unwrap_or_else(default_kyth_shared_pythonpath);

    let output = Command::new("python3")
        .arg(bridge_script_path(script))
        .args(args)
        .env("PYTHONPATH", &pythonpath)
        .output()
        .map_err(|e| format!("failed to spawn python3 ({script}): {e}"))?;

    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).into_owned());
    }
    serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("{script} returned non-JSON output: {e}"))
}

/// Reads one disk-backed probe section (see kyth_shared.system.probe's
/// DISK_TTL for valid keys) by shelling out to backend/probe_bridge.py.
/// Read-only, and bounded by whatever read_section() itself does — no
/// fresh system probing happens here (see that script's docstring).
#[tauri::command]
fn probe_backend(section: String) -> Result<serde_json::Value, String> {
    run_bridge("probe_bridge.py", &[&section])
}

/// Guardian's pending-recommendation count + recent history, from disk —
/// see backend/guardian_bridge.py's docstring for why this deliberately
/// does NOT trigger a live symptom probe.
#[tauri::command]
fn guardian_snapshot() -> Result<serde_json::Value, String> {
    run_bridge("guardian_bridge.py", &[])
}

/// Raw first `lspci -nn` GPU line, if any — see backend/hardware_bridge.py.
#[tauri::command]
fn hardware_snapshot() -> Result<serde_json::Value, String> {
    run_bridge("hardware_bridge.py", &[])
}

/// Free/total bytes on the same filesystem Guardian's own storage check
/// looks at — see backend/storage_bridge.py.
#[tauri::command]
fn storage_snapshot() -> Result<serde_json::Value, String> {
    run_bridge("storage_bridge.py", &[])
}

/// One-shot pull for the page this process was launched with (`--page`,
/// e.g. from a desktop file or CLI deep link). Pulled by the frontend on
/// mount rather than pushed as an event, to avoid a race against the
/// webview's JS not having registered its "navigate" listener yet.
#[tauri::command]
fn take_pending_page(state: tauri::State<PendingPage>) -> Option<String> {
    state.0.lock().unwrap().take()
}

fn main() {
    let initial_page = extract_page_arg(&std::env::args().collect::<Vec<_>>());

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            // A second launch forwards here instead of opening a second
            // window — same "single instance, focus the existing one"
            // contract instance_ipc.py gives the current Qt Hub. Unlike
            // the initial-launch case, the webview is already up by now,
            // so this pushes the event directly instead of going through
            // PendingPage.
            let page = extract_page_arg(&argv);
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
                if let Some(page) = page {
                    let _ = window.emit("navigate", page);
                }
            }
        }))
        .manage(PendingPage(Mutex::new(initial_page)))
        .invoke_handler(tauri::generate_handler![
            probe_backend, guardian_snapshot, hardware_snapshot, storage_snapshot, take_pending_page
        ])
        .run(tauri::generate_context!())
        .expect("error while running the Kyth Hub shell");
}
