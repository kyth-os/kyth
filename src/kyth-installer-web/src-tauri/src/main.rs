// Unprivileged shell for the React installer frontend.
//
// The Python installer still owns the authenticated loopback API and all
// disk/boot operations. This process only embeds the frontend and hands it
// the fixed loopback endpoint plus the two per-run tokens supplied by the
// root-owned launcher. There is deliberately no filesystem or command bridge.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;

use serde::Serialize;
use tauri::Manager;

const BACKEND_URL: &str = "http://127.0.0.1:7777";

struct InstallerTokens(Mutex<Option<InstallerConnection>>);

#[derive(Clone, Serialize)]
struct InstallerConnection {
    base_url: String,
    bootstrap_token: String,
    session_token: String,
}

fn arg_value<S: AsRef<str>>(argv: &[S], name: &str) -> Option<String> {
    argv.iter()
        .position(|arg| arg.as_ref() == name)
        .and_then(|index| argv.get(index + 1))
        .map(|value| value.as_ref().to_string())
}

#[tauri::command]
fn installer_connection(state: tauri::State<InstallerTokens>) -> Result<InstallerConnection, String> {
    state
        .0
        .lock()
        .map_err(|_| "installer connection state unavailable".to_string())?
        .clone()
        .ok_or_else(|| "installer shell was not given backend tokens".to_string())
}

fn main() {
    let argv: Vec<String> = std::env::args().collect();
    let tokens = InstallerConnection {
        base_url: BACKEND_URL.to_string(),
        bootstrap_token: arg_value(&argv, "--bootstrap-token").unwrap_or_default(),
        session_token: arg_value(&argv, "--session-token").unwrap_or_default(),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .manage(InstallerTokens(Mutex::new(Some(tokens))))
        .invoke_handler(tauri::generate_handler![installer_connection])
        .run(tauri::generate_context!())
        .expect("error while running the KythOS installer shell");
}
