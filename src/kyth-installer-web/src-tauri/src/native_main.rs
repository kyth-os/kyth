//! Native Slint installer shell.
//!
//! The root-owned Python installer service remains the only process allowed
//! to perform storage/boot operations. This native shell owns the request
//! model and fixed-route transport for the guarded installer flow. Manual
//! partition editing and live event streaming are intentionally still being
//! ported before it replaces the Tauri shell.

slint::include_modules!();

use slint::{ComponentHandle, SharedString, Weak};
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::time::Duration;

const MAX_RESPONSE_BYTES: usize = 1024 * 1024;

#[derive(Clone)]
struct ConnectionArgs {
    socket_path: Option<String>,
    session_token: String,
}

#[derive(Clone)]
struct InstallState {
    disk: String,
    install_mode: String,
    target_partition: String,
    resize_partition: String,
    resize_gib: u64,
    free_region_start: u64,
    free_region_end: u64,
    hostname: String,
    timezone: String,
    locale: String,
    keymap: String,
    username: String,
    password: String,
    kernel: String,
    confirm_backup: bool,
    confirm_erase: bool,
    confirm_current: bool,
}

impl Default for InstallState {
    fn default() -> Self {
        Self {
            disk: String::new(),
            install_mode: "wipe".into(),
            target_partition: String::new(),
            resize_partition: String::new(),
            resize_gib: 64,
            free_region_start: 0,
            free_region_end: 0,
            hostname: "kyth".into(),
            timezone: "UTC".into(),
            locale: "en_US.UTF-8".into(),
            keymap: "us".into(),
            username: String::new(),
            password: String::new(),
            kernel: "fedora".into(),
            confirm_backup: false,
            confirm_erase: false,
            confirm_current: false,
        }
    }
}

impl InstallState {
    fn as_request(&self) -> Value {
        json!({
            "disk": self.disk,
            "install_mode": self.install_mode,
            "target_partition": self.target_partition,
            "resize_partition": self.resize_partition,
            "resize_gib": self.resize_gib,
            "free_region_start": self.free_region_start,
            "free_region_end": self.free_region_end,
            "hostname": self.hostname,
            "timezone": self.timezone,
            "locale": self.locale,
            "keymap": self.keymap,
            "username": self.username,
            "password": self.password,
            "kernel": self.kernel,
            "confirm_backup": self.confirm_backup,
            "confirm_erase": self.confirm_erase,
            "confirm_current": self.confirm_current,
        })
    }

    fn can_start(&self) -> bool {
        !self.disk.is_empty()
            && !self.username.trim().is_empty()
            && !self.password.is_empty()
            && self.confirm_backup
            && self.confirm_erase
            && self.install_mode != "manual"
            && (self.install_mode != "wipe" || self.confirm_current)
            && (self.install_mode != "alongside" || !self.target_partition.is_empty())
            && (self.install_mode != "free_space" || self.free_region_end > self.free_region_start)
            && (self.install_mode != "resize_ntfs" || self.resize_gib >= 32)
    }
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

fn post_json(config: &ConnectionArgs, path: &str, body: Value) -> Result<(u16, Value), String> {
    const ALLOWED: &[&str] = &[
        "/api/start",
        "/api/cancel",
        "/api/reboot",
        "/api/rescue/logs-to-usb",
    ];
    if !ALLOWED.contains(&path) {
        return Err("Installer route is not allowlisted".to_string());
    }
    let Some(socket_path) = config.socket_path.as_deref() else {
        return Err("Waiting for the installer service socket".to_string());
    };
    let mut stream = UnixStream::connect(socket_path).map_err(|_| "Installer service is not available yet".to_string())?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(610)));
    let payload = serde_json::to_string(&body).map_err(|_| "Could not encode installer request".to_string())?;
    let request = format!(
        "POST {path} HTTP/1.1\r\nHost: kyth-installer.local\r\nX-Kyth-Session-Token: {}\r\nAccept: application/json\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{payload}",
        config.session_token,
        payload.len(),
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
    let mut response = vec![0_u8; length];
    std::io::Read::read_exact(&mut reader, &mut response).map_err(|_| "Installer response was incomplete".to_string())?;
    let value = serde_json::from_slice::<Value>(&response).map_err(|_| "Installer response was not valid JSON".to_string())?;
    Ok((code, value))
}

fn stream_install_events(weak: Weak<InstallerWindow>, config: ConnectionArgs) {
    std::thread::spawn(move || {
        let Some(socket_path) = config.socket_path.as_deref() else { return; };
        let mut stream = match UnixStream::connect(socket_path) {
            Ok(stream) => stream,
            Err(_) => return,
        };
        let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
        let request = format!(
            "GET /api/stream HTTP/1.1\r\nHost: kyth-installer.local\r\nX-Kyth-Session-Token: {}\r\nAccept: text/event-stream\r\n\r\n",
            config.session_token,
        );
        if stream.write_all(request.as_bytes()).is_err() { return; }
        let mut reader = BufReader::new(stream);
        let mut status = String::new();
        if reader.read_line(&mut status).is_err() || !status.contains(" 200 ") { return; }
        loop {
            let mut header = String::new();
            match reader.read_line(&mut header) {
                Ok(0) => return,
                Ok(_) if header == "\r\n" || header == "\n" => break,
                Ok(_) => continue,
                Err(error) if error.kind() == std::io::ErrorKind::TimedOut || error.kind() == std::io::ErrorKind::WouldBlock => continue,
                Err(_) => return,
            }
        }

        let mut data = String::new();
        for _ in 0..1800 {
            let mut line = String::new();
            match reader.read_line(&mut line) {
                Ok(0) => return,
                Ok(_) => {
                    if let Some(payload) = line.strip_prefix("data: ") {
                        data.push_str(payload.trim_end());
                    } else if (line == "\r\n" || line == "\n") && !data.is_empty() {
                        let parsed = serde_json::from_str::<Value>(&data);
                        data.clear();
                        let Ok(event) = parsed else { continue; };
                        let event_type = event.get("type").and_then(Value::as_str).unwrap_or("");
                        let terminal = matches!(event_type, "done" | "error");
                        let _ = slint::invoke_from_event_loop({
                            let weak = weak.clone();
                            let event = event.clone();
                            move || {
                                if let Some(window) = weak.upgrade() {
                                    match event.get("type").and_then(Value::as_str).unwrap_or("") {
                                        "log" => {
                                            if let Some(text) = event.get("text").and_then(Value::as_str) {
                                                window.set_event_log(SharedString::from(text));
                                            }
                                        }
                                        "progress" => {
                                            if let Some(value) = event.get("value").and_then(Value::as_f64) {
                                                window.set_progress(value as f32);
                                            }
                                        }
                                        "phase" => {
                                            if let Some(phase) = event.get("phase").and_then(Value::as_str) {
                                                window.set_step_status(SharedString::from(format!("Installer phase: {phase}")));
                                                window.set_event_log(SharedString::from(format!("Installer service is applying the {phase} phase…")));
                                            }
                                        }
                                        "done" => {
                                            window.set_progress(100.0);
                                            window.set_transaction_text(SharedString::from("Installation complete"));
                                            window.set_event_log(SharedString::from("Installation complete. Remove the installation media before rebooting."));
                                            window.set_busy(false);
                                            window.set_selected_step(SharedString::from("Done"));
                                        }
                                        "error" => {
                                            let message = response_message(&event, "Installation failed");
                                            window.set_error_text(SharedString::from(message.as_str()));
                                            window.set_event_log(SharedString::from("Installation failed; inspect Rescue & diagnostics."));
                                            window.set_busy(false);
                                            window.set_selected_step(SharedString::from("Rescue"));
                                        }
                                        _ => {}
                                    }
                                }
                            }
                        });
                        if terminal { return; }
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::TimedOut || error.kind() == std::io::ErrorKind::WouldBlock => continue,
                Err(_) => return,
            }
        }
    });
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

fn disk_names(value: &Value) -> [String; 6] {
    let mut names = std::array::from_fn(|_| String::new());
    if let Some(disks) = value.as_array() {
        for (slot, disk) in disks.iter().take(names.len()).enumerate() {
            if let Some(name) = disk.get("name").and_then(Value::as_str) {
                names[slot] = name.to_string();
            }
        }
    }
    names
}

fn storage_snapshot(config: &ConnectionArgs, disk: &str) -> (String, [String; 6], [String; 6]) {
    let empty = std::array::from_fn(|_| String::new());
    if disk.is_empty() {
        return ("Select a disk to inspect its partitions and free space.".to_string(), empty.clone(), empty);
    }

    let query_disk = disk.replace(' ', "%20");
    let partitions = get_json(config, &format!("/api/partitions?disk={query_disk}"));
    let free_regions = get_json(config, &format!("/api/free-space?disk={query_disk}"));
    let mut partition_names = std::array::from_fn(|_| String::new());
    let mut free_names = std::array::from_fn(|_| String::new());
    let mut detail_lines = Vec::new();

    if let Ok((200, value)) = partitions {
        if let Some(items) = value.as_array() {
            for (slot, part) in items.iter().take(6).enumerate() {
                let name = part.get("name").and_then(Value::as_str).unwrap_or("unnamed partition");
                let fs = part.get("fstype").and_then(Value::as_str).filter(|value| !value.is_empty()).unwrap_or("unknown filesystem");
                let size = part.get("size_bytes").and_then(Value::as_u64).map(|bytes| kyth_shared::transfer::human_bytes(bytes as f64)).unwrap_or_else(|| "size unavailable".to_string());
                let suffix = if part.get("current").and_then(Value::as_bool).unwrap_or(false) { " · current" } else if part.get("in_use").and_then(Value::as_bool).unwrap_or(false) { " · in use" } else if part.get("efi").and_then(Value::as_bool).unwrap_or(false) { " · EFI" } else { "" };
                let selectable = !part.get("current").and_then(Value::as_bool).unwrap_or(false)
                    && !part.get("in_use").and_then(Value::as_bool).unwrap_or(false);
                if selectable {
                    partition_names[slot] = name.to_string();
                }
                detail_lines.push(format!("{name} · {fs} · {size}{suffix}"));
            }
        }
    }
    if let Ok((200, value)) = free_regions {
        if let Some(items) = value.as_array() {
            for (slot, region) in items.iter().take(6).enumerate() {
                let start = region.get("start_bytes").and_then(Value::as_u64).unwrap_or(0);
                let end = region.get("end_bytes").and_then(Value::as_u64).unwrap_or(0);
                let size = region.get("size_bytes").and_then(Value::as_u64).map(|bytes| kyth_shared::transfer::human_bytes(bytes as f64)).unwrap_or_else(|| "size unavailable".to_string());
                free_names[slot] = format!("{start}:{end} · {size}");
            }
        }
    }

    let details = if detail_lines.is_empty() {
        "No usable partitions or free regions reported for this disk.".to_string()
    } else {
        detail_lines.join("\n")
    };
    (details, partition_names, free_names)
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

fn connection_snapshot(config: &ConnectionArgs) -> (String, String, String, String, [String; 6]) {
    let connection = match get_json(config, "/api/config") {
        Ok((200, value)) => {
            let source = value.get("source").and_then(|source| source.get("message")).and_then(serde_json::Value::as_str).filter(|message| !message.trim().is_empty());
            source.map_or_else(|| "Installer service connected".to_string(), |message| format!("Installer service connected · {message}"))
        }
        Ok(_) => "Installer service rejected the connection".to_string(),
        Err(error) => error,
    };
    let (disk_summary, disk_details, names) = match get_json(config, "/api/disks") {
        Ok((200, value)) => {
            let (summary, details) = disk_inventory(&value);
            (summary, details, disk_names(&value))
        }
        Ok(_) => ("Disk inventory is not available yet".to_string(), "The installer service did not return a disk list.".to_string(), std::array::from_fn(|_| String::new())),
        Err(_) => ("Connect to see available install targets".to_string(), "Disk details will appear here when the service is ready.".to_string(), std::array::from_fn(|_| String::new())),
    };
    let transaction = transaction_snapshot(config);
    (connection, disk_summary, disk_details, transaction, names)
}

fn refresh_connection(weak: Weak<InstallerWindow>, config: ConnectionArgs) {
    std::thread::spawn(move || {
        let (status, disk_summary, disk_details, transaction, names) = connection_snapshot(&config);
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                window.set_status_text(SharedString::from(status));
                window.set_disk_summary(SharedString::from(disk_summary));
                window.set_disk_details(SharedString::from(disk_details));
                window.set_transaction_text(SharedString::from(transaction));
                window.set_disk_one(SharedString::from(names[0].as_str()));
                window.set_disk_two(SharedString::from(names[1].as_str()));
                window.set_disk_three(SharedString::from(names[2].as_str()));
                window.set_disk_four(SharedString::from(names[3].as_str()));
                window.set_disk_five(SharedString::from(names[4].as_str()));
                window.set_disk_six(SharedString::from(names[5].as_str()));
            }
        });
    });
}

fn refresh_storage(weak: Weak<InstallerWindow>, config: ConnectionArgs, disk: String) {
    std::thread::spawn(move || {
        let (details, partitions, free_regions) = storage_snapshot(&config, &disk);
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                if window.get_selected_disk().as_str() != disk { return; }
                window.set_storage_details(SharedString::from(details));
                window.set_partition_one(SharedString::from(partitions[0].as_str()));
                window.set_partition_two(SharedString::from(partitions[1].as_str()));
                window.set_partition_three(SharedString::from(partitions[2].as_str()));
                window.set_partition_four(SharedString::from(partitions[3].as_str()));
                window.set_partition_five(SharedString::from(partitions[4].as_str()));
                window.set_partition_six(SharedString::from(partitions[5].as_str()));
                window.set_free_region_one(SharedString::from(free_regions[0].as_str()));
                window.set_free_region_two(SharedString::from(free_regions[1].as_str()));
                window.set_free_region_three(SharedString::from(free_regions[2].as_str()));
                window.set_free_region_four(SharedString::from(free_regions[3].as_str()));
                window.set_free_region_five(SharedString::from(free_regions[4].as_str()));
                window.set_free_region_six(SharedString::from(free_regions[5].as_str()));
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

fn request_from_window(window: &InstallerWindow, state: &Arc<Mutex<InstallState>>) -> Value {
    let mut request = state.lock().expect("installer state lock poisoned");
    request.disk = window.get_selected_disk().to_string();
    request.target_partition = window.get_target_partition().to_string();
    request.free_region_start = window.get_free_region_start().parse().unwrap_or(0);
    request.free_region_end = window.get_free_region_end().parse().unwrap_or(0);
    request.install_mode = window.get_install_mode().to_string();
    request.resize_gib = window.get_resize_gib().parse().unwrap_or(0);
    request.kernel = window.get_kernel().to_string();
    request.hostname = window.get_hostname().to_string();
    request.timezone = window.get_timezone().to_string();
    request.locale = window.get_locale().to_string();
    request.keymap = window.get_keymap().to_string();
    request.username = window.get_username().to_string();
    request.password = window.get_password().to_string();
    request.confirm_backup = window.get_confirm_backup();
    request.confirm_erase = window.get_confirm_erase();
    request.confirm_current = window.get_confirm_current();
    request.as_request()
}

fn response_message(value: &Value, fallback: &str) -> String {
    value
        .get("message")
        .or_else(|| value.get("error"))
        .and_then(Value::as_str)
        .filter(|message| !message.trim().is_empty())
        .unwrap_or(fallback)
        .to_string()
}

fn start_install(weak: Weak<InstallerWindow>, config: ConnectionArgs, request: Value) {
    std::thread::spawn(move || {
        let result = post_json(&config, "/api/start", request);
        match result {
            Ok((status, value)) if (200..300).contains(&status) && value.get("started").and_then(Value::as_bool).unwrap_or(false) => {
                let _ = slint::invoke_from_event_loop({
                    let weak = weak.clone();
                    move || {
                        if let Some(window) = weak.upgrade() {
                            window.set_busy(true);
                            window.set_error_text(SharedString::from(""));
                            apply_step(&window, "Install");
                            window.set_event_log(SharedString::from("Installation started; waiting for service events…"));
                        }
                    }
                });
                stream_install_events(weak.clone(), config.clone());
                for _ in 0..1800 {
                    std::thread::sleep(Duration::from_secs(1));
                    let snapshot = get_json(&config, "/api/report");
                    let Ok((report_status, report)) = snapshot else { continue; };
                    if report_status != 200 { continue; }
                    let lifecycle = report.get("lifecycle").and_then(Value::as_str).unwrap_or("").to_string();
                    let phase = report.get("phase").and_then(Value::as_str).unwrap_or("").to_string();
                    let message = response_message(&report, "Installation is in progress…");
                    let terminal = matches!(lifecycle, "done" | "failed") || phase == "complete";
                    let progress = if terminal { 100.0 } else if phase == "secure_boot" { 90.0 } else if phase == "configure" { 75.0 } else if phase == "image" { 50.0 } else if phase == "storage" { 20.0 } else { 5.0 };
                    let _ = slint::invoke_from_event_loop({
                        let weak = weak.clone();
                        let lifecycle = lifecycle.clone();
                        move || {
                            if let Some(window) = weak.upgrade() {
                                window.set_progress(progress);
                                window.set_transaction_text(SharedString::from(message.as_str()));
                                window.set_event_log(SharedString::from(if lifecycle == "failed" { "Installation failed; inspect Rescue & diagnostics." } else if terminal { "Installation complete. Remove the installation media before rebooting." } else { "Installer service is applying the reviewed plan…" }));
                                if lifecycle == "failed" {
                                    window.set_error_text(SharedString::from(message.as_str()));
                                }
                                if terminal {
                                    window.set_busy(false);
                                    window.set_selected_step(SharedString::from(if lifecycle == "failed" { "Rescue" } else { "Done" }));
                                }
                            }
                        }
                    });
                    if terminal { break; }
                }
            }
            Ok((_status, value)) => {
                let message = response_message(&value, "Installer refused the request");
                let _ = slint::invoke_from_event_loop(move || {
                    if let Some(window) = weak.upgrade() {
                        window.set_busy(false);
                        window.set_error_text(SharedString::from(message));
                    }
                });
            }
            Err(error) => {
                let _ = slint::invoke_from_event_loop(move || {
                    if let Some(window) = weak.upgrade() {
                        window.set_busy(false);
                        window.set_error_text(SharedString::from(error));
                    }
                });
            }
        }
    });
}

fn post_action(weak: Weak<InstallerWindow>, config: ConnectionArgs, path: &'static str, body: Value) {
    std::thread::spawn(move || {
        let result = post_json(&config, path, body);
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                match result {
                    Ok((status, value)) if (200..300).contains(&status) => {
                        window.set_error_text(SharedString::from(""));
                        window.set_event_log(SharedString::from(response_message(&value, "Request completed")));
                    }
                    Ok((_status, value)) => window.set_error_text(SharedString::from(response_message(&value, "Installer rejected the request"))),
                    Err(error) => window.set_error_text(SharedString::from(error)),
                }
            }
        });
    });
}

fn rescue_probe(weak: Weak<InstallerWindow>, config: ConnectionArgs) {
    std::thread::spawn(move || {
        let result = get_json(&config, "/api/rescue/probe");
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                match result {
                    Ok((200, value)) => {
                        let guidance = value.get("rescue_guidance").map_or_else(|| "Rescue probe completed".to_string(), |item| response_message(item, "Rescue probe completed"));
                        let log = value.get("log_tail").and_then(Value::as_str).unwrap_or("(no installer log available)");
                        window.set_event_log(SharedString::from(format!("{guidance}\n\n{log}")));
                        window.set_error_text(SharedString::from(""));
                    }
                    Ok((_status, value)) => window.set_error_text(SharedString::from(response_message(&value, "Rescue probe failed"))),
                    Err(error) => window.set_error_text(SharedString::from(error)),
                }
            }
        });
    });
}

fn main() -> Result<(), slint::PlatformError> {
    let config = connection_args();
    let state = Arc::new(Mutex::new(InstallState::default()));
    let window = InstallerWindow::new()?;
    window.set_status_text(SharedString::from("Connecting to installer service…"));
    window.set_step_status(SharedString::from("Reading native step status…"));
    window.set_install_mode(SharedString::from("wipe"));
    window.set_kernel(SharedString::from("fedora"));
    window.set_hostname(SharedString::from("kyth"));
    window.set_timezone(SharedString::from("UTC"));
    window.set_locale(SharedString::from("en_US.UTF-8"));
    window.set_keymap(SharedString::from("us"));
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
    let disk_state = state.clone();
    let disk_weak = window.as_weak();
    let disk_config = config.clone();
    window.on_select_disk(move |disk| {
        if let Ok(mut state) = disk_state.lock() {
            state.disk = disk.to_string();
            state.target_partition.clear();
            state.free_region_start = 0;
            state.free_region_end = 0;
        }
        if let Some(window) = disk_weak.upgrade() {
            window.set_target_partition(SharedString::from(""));
            window.set_free_region_start(SharedString::from("0"));
            window.set_free_region_end(SharedString::from("0"));
        }
        refresh_storage(disk_weak.clone(), disk_config.clone(), disk.to_string());
    });
    let mode_state = state.clone();
    let mode_weak = window.as_weak();
    window.on_select_mode(move |mode| {
        if let Ok(mut state) = mode_state.lock() {
            state.install_mode = mode.to_string();
            if mode.as_str() != "alongside" {
                state.target_partition.clear();
            }
        }
        if mode.as_str() != "alongside" {
            if let Some(window) = mode_weak.upgrade() {
                window.set_target_partition(SharedString::from(""));
            }
        }
    });
    let target_state = state.clone();
    window.on_select_target_partition(move |partition| {
        if let Ok(mut state) = target_state.lock() {
            state.target_partition = partition.to_string();
        }
    });
    let free_state = state.clone();
    let free_weak = window.as_weak();
    window.on_select_free_region(move |region| {
        let mut values = region.split(" · ").next().unwrap_or("").split(':');
        let start = values.next().and_then(|value| value.parse::<u64>().ok()).unwrap_or(0);
        let end = values.next().and_then(|value| value.parse::<u64>().ok()).unwrap_or(0);
        if let Ok(mut state) = free_state.lock() {
            state.free_region_start = start;
            state.free_region_end = end;
        }
        if let Some(window) = free_weak.upgrade() {
            window.set_free_region_start(SharedString::from(start.to_string()));
            window.set_free_region_end(SharedString::from(end.to_string()));
        }
    });
    let kernel_state = state.clone();
    window.on_select_kernel(move |kernel| {
        if let Ok(mut state) = kernel_state.lock() {
            state.kernel = kernel.to_string();
        }
    });
    let start_weak = window.as_weak();
    let start_config = config.clone();
    let start_state = state.clone();
    window.on_start_install(move || {
        if let Some(window) = start_weak.upgrade() {
            let request = request_from_window(&window, &start_state);
            let ready = start_state.lock().map(|state| state.can_start()).unwrap_or(false);
            if !ready {
                window.set_error_text(SharedString::from("Select a valid target, complete the required confirmations, and choose a supported guided install mode."));
                return;
            }
            window.set_busy(true);
            window.set_error_text(SharedString::from(""));
            start_install(start_weak.clone(), start_config.clone(), request);
        }
    });
    let cancel_weak = window.as_weak();
    let cancel_config = config.clone();
    window.on_cancel_install(move || {
        post_action(cancel_weak.clone(), cancel_config.clone(), "/api/cancel", json!({}));
    });
    let reboot_weak = window.as_weak();
    let reboot_config = config.clone();
    window.on_reboot(move || {
        post_action(reboot_weak.clone(), reboot_config.clone(), "/api/reboot", json!({}));
    });
    let rescue_weak = window.as_weak();
    let rescue_config = config.clone();
    window.on_rescue_probe(move || {
        rescue_probe(rescue_weak.clone(), rescue_config.clone());
    });
    refresh_step(window.as_weak(), config.clone(), "Welcome".to_string());
    refresh_connection(weak, config);
    window.run()
}
