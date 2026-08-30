//! Native Slint installer shell.
//!
//! The root-owned Python installer service remains the only process allowed
//! to perform storage/boot operations. This native shell starts with a real
//! bounded read-only connection check and will receive the validated installer
//! flow page by page before it replaces the Tauri shell.

slint::include_modules!();

use slint::{ComponentHandle, SharedString, Weak};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::time::Duration;

const MAX_RESPONSE_BYTES: usize = 1024 * 1024;

#[derive(Clone)]
struct ConnectionArgs {
    socket_path: Option<String>,
    session_token: String,
}

fn arg_value(args: &[String], name: &str) -> Option<String> {
    args.windows(2)
        .find_map(|pair| (pair[0] == name).then(|| pair[1].clone()))
}

fn connection_args() -> ConnectionArgs {
    let args = std::env::args().collect::<Vec<_>>();
    ConnectionArgs {
        socket_path: arg_value(&args, "--socket-path"),
        session_token: arg_value(&args, "--session-token").unwrap_or_default(),
    }
}

fn get_json(config: &ConnectionArgs, path: &str) -> Result<(u16, serde_json::Value), String> {
    let Some(socket_path) = config.socket_path.as_deref() else {
        return Err("Waiting for the installer service socket".to_string());
    };
    let mut stream = UnixStream::connect(socket_path).map_err(|_| "Installer service is not available yet".to_string())?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(3)));
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: kyth-installer.local\r\nX-Kyth-Session-Token: {}\r\nAccept: application/json\r\nContent-Length: 0\r\n\r\n",
        config.session_token,
    );
    stream.write_all(request.as_bytes()).map_err(|_| "Could not contact installer service".to_string())?;
    let mut reader = BufReader::new(stream);
    let mut status = String::new();
    reader.read_line(&mut status).map_err(|_| "Installer service returned no response".to_string())?;
    let code = status.split_whitespace().nth(1).and_then(|value| value.parse::<u16>().ok()).ok_or_else(|| "Installer service returned an invalid response".to_string())?;
    let mut length = None;
    loop {
        let mut line = String::new();
        reader.read_line(&mut line).map_err(|_| "Installer response could not be read".to_string())?;
        if line == "\r\n" || line == "\n" { break; }
        if let Some(value) = line.strip_prefix("Content-Length:") {
            length = value.trim().parse::<usize>().ok();
        }
    }
    let Some(length) = length.filter(|value| *value <= MAX_RESPONSE_BYTES) else {
        return Err("Installer response was not safely bounded".to_string());
    };
    let mut body = vec![0_u8; length];
    std::io::Read::read_exact(&mut reader, &mut body).map_err(|_| "Installer response was incomplete".to_string())?;
    let value = serde_json::from_slice::<serde_json::Value>(&body).map_err(|_| "Installer response was not valid JSON".to_string())?;
    Ok((code, value))
}

fn disk_inventory(value: &serde_json::Value) -> (String, String) {
    let Some(disks) = value.as_array() else {
        return ("Installer returned no disk inventory".to_string(), "Disk details are unavailable.".to_string());
    };
    if disks.is_empty() {
        return ("No install targets reported yet".to_string(), "Connect installation media or attach a writable disk.".to_string());
    }
    let mut details = Vec::new();
    for disk in disks.iter().take(6) {
        let name = disk.get("name").and_then(serde_json::Value::as_str).unwrap_or("unnamed device");
        let model = disk.get("model").and_then(serde_json::Value::as_str).filter(|value| !value.trim().is_empty()).unwrap_or("Unknown model");
        let size = disk.get("size_bytes").and_then(serde_json::Value::as_u64).map(|bytes| kyth_shared::transfer::human_bytes(bytes as f64)).unwrap_or_else(|| "size unavailable".to_string());
        let current = disk.get("current").and_then(serde_json::Value::as_bool).unwrap_or(false);
        details.push(if current {
            format!("{name} · {model} · {size} · current system disk")
        } else {
            format!("{name} · {model} · {size}")
        });
    }
    if disks.len() > details.len() { details.push(format!("… and {} more target(s)", disks.len() - details.len())); }
    (format!("{} install target(s) available", disks.len()), details.join("\n"))
}

fn transaction_snapshot(config: &ConnectionArgs) -> String {
    match get_json(config, "/api/report") {
        Ok((200, value)) if value.as_object().is_some_and(|object| !object.is_empty()) => {
            let status = value.get("status").and_then(serde_json::Value::as_str).unwrap_or("unknown");
            let phase = value.get("phase").and_then(serde_json::Value::as_str).filter(|phase| !phase.is_empty());
            let message = value.get("message").and_then(serde_json::Value::as_str).filter(|message| !message.trim().is_empty());
            let mut result = format!("{status}{}", phase.map_or(String::new(), |phase| format!(" · {phase}")));
            if let Some(message) = message {
                result.push_str(&format!(" · {message}"));
            }
            result
        }
        Ok((200, _)) => "No install transaction recorded".to_string(),
        Ok(_) => "Transaction report is not available yet".to_string(),
        Err(_) => "Transaction state will appear when the service is ready".to_string(),
    }
}

fn array_count(config: &ConnectionArgs, path: &str) -> Option<usize> {
    get_json(config, path).ok().and_then(|(status, value)| (status == 200).then(|| value.as_array().map_or(0, Vec::len)))
}

fn step_snapshot(config: &ConnectionArgs, step: &str) -> String {
    match step {
        "Configure" => {
            let timezones = array_count(config, "/api/timezones");
            let locales = array_count(config, "/api/locales");
            let keymaps = array_count(config, "/api/keymaps");
            match (timezones, locales, keymaps) {
                (Some(timezones), Some(locales), Some(keymaps)) => format!("Configuration data ready · {timezones} timezones · {locales} locales · {keymaps} keymaps"),
                _ => "Configuration choices will appear when the service is ready".to_string(),
            }
        }
        "Review" => match get_json(config, "/api/disk/pending") {
            Ok((200, value)) => {
                let count = value.as_array().map_or(0, Vec::len);
                if count == 0 { "No staged disk operations · review is currently clear".to_string() } else { format!("{count} staged disk operation(s) · review before committing") }
            }
            _ => "Staged disk operations will appear when the service is ready".to_string(),
        },
        "Install" => transaction_snapshot(config),
        "Select disk" => "Disk inventory is read-only until an explicit plan is reviewed".to_string(),
        _ => "Service connection and source image are shown below".to_string(),
    }
}

fn connection_snapshot(config: &ConnectionArgs) -> (String, String, String, String) {
    let connection = match get_json(config, "/api/config") {
        Ok((200, value)) => {
            let source = value.get("source").and_then(|source| source.get("message")).and_then(serde_json::Value::as_str).filter(|message| !message.trim().is_empty());
            source.map_or_else(|| "Installer service connected".to_string(), |message| format!("Installer service connected · {message}"))
        }
        Ok(_) => "Installer service rejected the connection".to_string(),
        Err(error) => error,
    };
    let (disk_summary, disk_details) = match get_json(config, "/api/disks") {
        Ok((200, value)) => disk_inventory(&value),
        Ok(_) => ("Disk inventory is not available yet".to_string(), "The installer service did not return a disk list.".to_string()),
        Err(_) => ("Connect to see available install targets".to_string(), "Disk details will appear here when the service is ready.".to_string()),
    };
    let transaction = transaction_snapshot(config);
    (connection, disk_summary, disk_details, transaction)
}

fn refresh_connection(weak: Weak<InstallerWindow>, config: ConnectionArgs) {
    std::thread::spawn(move || {
        let (status, disk_summary, disk_details, transaction) = connection_snapshot(&config);
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                window.set_status_text(SharedString::from(status));
                window.set_disk_summary(SharedString::from(disk_summary));
                window.set_disk_details(SharedString::from(disk_details));
                window.set_transaction_text(SharedString::from(transaction));
            }
        });
    });
}

fn refresh_step(weak: Weak<InstallerWindow>, config: ConnectionArgs, step: String) {
    std::thread::spawn(move || {
        let status = step_snapshot(&config, &step);
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                if window.get_selected_step().as_str() == step {
                    window.set_step_status(SharedString::from(status));
                }
            }
        });
    });
}

fn step_copy(step: &str) -> (&'static str, &'static str) {
    match step {
        "Select disk" => (
            "Select an install target",
            "The native flow will show disks and free space from the installer service before any change is proposed.",
        ),
        "Configure" => (
            "Configure KythOS",
            "Choose the kernel, account, locale, timezone, and keyboard layout for the new system.",
        ),
        "Review" => (
            "Review your choices",
            "Every destructive operation is summarized here for confirmation before the service can apply it.",
        ),
        "Install" => (
            "Install KythOS",
            "Progress and service events stay visible in this window. Cancellation remains an explicit request.",
        ),
        _ => (
            "Welcome to KythOS",
            "Install the immutable gaming and development desktop with guarded, reviewable steps.",
        ),
    }
}

fn step_index(step: &str) -> usize {
    match step {
        "Select disk" => 1,
        "Configure" => 2,
        "Review" => 3,
        "Install" => 4,
        _ => 0,
    }
}

fn step_name(index: usize) -> &'static str {
    match index {
        1 => "Select disk",
        2 => "Configure",
        3 => "Review",
        4 => "Install",
        _ => "Welcome",
    }
}

fn apply_step(window: &InstallerWindow, step: &str) {
    let (title, detail) = step_copy(step);
    let index = step_index(step);
    window.set_selected_step(SharedString::from(step));
    window.set_step_title(SharedString::from(title));
    window.set_step_detail(SharedString::from(detail));
    window.set_step_progress(SharedString::from(format!("Step {} of 5", index + 1)));
    window.set_next_label(SharedString::from(if index == 4 { "Review installation" } else { "Continue" }));
    window.set_back_enabled(index > 0);
    window.set_step_status(SharedString::from("Reading native step status…"));
}

fn main() -> Result<(), slint::PlatformError> {
    let config = connection_args();
    let window = InstallerWindow::new()?;
    window.set_status_text(SharedString::from("Connecting to installer service…"));
    window.set_step_status(SharedString::from("Reading native step status…"));
    apply_step(&window, "Welcome");
    let weak = window.as_weak();
    let connect_weak = weak.clone();
    let connect_config = config.clone();
    window.on_connect(move || {
        if let Some(window) = connect_weak.upgrade() {
            window.set_status_text(SharedString::from("Connecting to installer service…"));
            refresh_connection(connect_weak.clone(), connect_config.clone());
        }
    });
    let step_weak = window.as_weak();
    let step_config = config.clone();
    window.on_select_step(move |step| {
        if let Some(window) = step_weak.upgrade() {
            apply_step(&window, step.as_str());
            refresh_step(step_weak.clone(), step_config.clone(), step.to_string());
        }
    });
    let next_weak = window.as_weak();
    let next_config = config.clone();
    window.on_next_step(move || {
        if let Some(window) = next_weak.upgrade() {
            let next = (step_index(window.get_selected_step().as_str()) + 1).min(4);
            let step = step_name(next);
            apply_step(&window, step);
            refresh_step(next_weak.clone(), next_config.clone(), step.to_string());
        }
    });
    let previous_weak = window.as_weak();
    let previous_config = config.clone();
    window.on_previous_step(move || {
        if let Some(window) = previous_weak.upgrade() {
            let current = step_index(window.get_selected_step().as_str());
            let step = step_name(current.saturating_sub(1));
            apply_step(&window, step);
            refresh_step(previous_weak.clone(), previous_config.clone(), step.to_string());
        }
    });
    refresh_step(window.as_weak(), config.clone(), "Welcome".to_string());
    refresh_connection(weak, config);
    window.run()
}
