//! Native Slint Hub shell.
//!
//! This binary is additive while the existing Tauri shell remains the
//! production fallback. It owns the native window and calls the shared Rust
//! read paths directly; page-by-page parity is migrated before packaging
//! switches away from Tauri.

slint::include_modules!();

use slint::{ComponentHandle, SharedString, Weak};
use std::process::Command;
use std::time::Duration;

fn home_next_action() -> String {
    let mut snapshot = serde_json::Map::new();
    for section in ["bootc-status-data", "flatpak-updates", "nvidia-detect", "controllers-detect"] {
        if let Some(value) = kyth_shared::system::probe::read_section(section) {
            snapshot.insert(section.to_string(), value);
        }
    }
    let state = kyth_shared::system::boot_health::read_default_state();
    let mut quarantined = state.quarantined.keys().cloned().collect::<Vec<_>>();
    quarantined.sort();
    let boot = kyth_shared::system::ai_plan::BootStateView {
        failures: state.failures,
        status: state.status,
        quarantined,
    };
    let plan = kyth_shared::system::ai_plan::generate_plan(&serde_json::Value::Object(snapshot), Some(&boot), None);
    plan.actions.first().map_or_else(
        || "Suggested next step · No action needed".to_string(),
        |action| format!("Suggested next step · {}", action.label),
    )
}

fn system_status() -> String {
    let recovery = kyth_shared::system::recovery_status::get_recovery_status();
    let boot = kyth_shared::system::boot_runtime::boot_runtime_checks();
    let failed = boot.iter().filter(|check| !check.passed).count();
    if !recovery.quarantined_digest.is_empty() {
        "Recovery attention required · quarantined image".to_string()
    } else if recovery.has_staged {
        "Update staged · restart when ready".to_string()
    } else if failed > 0 {
        format!("{failed} boot check(s) need attention")
    } else {
        "System checks look good".to_string()
    }
}

fn page_status(page: &str) -> String {
    match page {
        "Play" => {
            if kyth_shared::system::probe::read_section("gaming-library").is_some()
                || kyth_shared::system::probe::read_section("audit-cache").is_some()
            {
                "Gaming services are ready · open a section to inspect them".to_string()
            } else {
                "Gaming status is not cached yet · refresh the source sections".to_string()
            }
        }
        "Apps" => {
            if kyth_shared::system::probe::read_section("flatpak-apps").is_some() {
                "Application inventory is ready · updates stay policy-gated".to_string()
            } else {
                "Application inventory is not cached yet".to_string()
            }
        }
        "Updates" => {
            let status = kyth_shared::system::update_status::check_update_status();
            match status.check_state.as_str() {
                "available" => format!("Update available · {}", status.detail),
                "error" => format!("Update status unavailable · {}", status.detail),
                _ if status.staged => "Update staged · restart when ready".to_string(),
                _ => format!("No updates pending · {}", status.detail),
            }
        }
        "This PC" => {
            let hardware = kyth_shared::system::hardware_view::get_hardware_view_summary();
            let stack = kyth_shared::system::desktop_stack::desktop_stack_checks();
            let failed = stack.iter().filter(|check| !check.passed && !check.advisory).count();
            match (hardware, failed) {
                (Some(hardware), 0) if hardware.has_nvidia && hardware.is_hybrid => {
                    "Hardware ready · hybrid NVIDIA graphics detected".to_string()
                }
                (Some(_), 0) => "Hardware and desktop stack look good".to_string(),
                (Some(_), count) => format!("{count} desktop check(s) need attention"),
                (None, _) => "Hardware information is not available yet".to_string(),
            }
        }
        "Move In" => {
            if kyth_shared::system::probe::read_section("ntfs-drives").is_some()
                || kyth_shared::system::probe::read_section("network-summary").is_some()
            {
                "Migration sources are ready · review before importing anything".to_string()
            } else {
                "Migration sources are not cached yet".to_string()
            }
        }
        _ => system_status(),
    }
}

fn page_copy(page: &str) -> (&'static str, &'static str) {
    match page {
        "Play" => (
            "Gaming workspace",
            "Launchers, compatibility, controllers, and performance tools belong here.",
        ),
        "Apps" => (
            "Applications",
            "Browse trusted apps and install them with clear, policy-gated status.",
        ),
        "This PC" => (
            "This PC",
            "Hardware, drivers, display stack, and system diagnostics are collected here.",
        ),
        "Move In" => (
            "Move In",
            "Bring files and settings over safely with an explicit review before changes.",
        ),
        "Updates" => (
            "Updates",
            "See available, staged, and recovery-aware updates without opening a terminal.",
        ),
        _ => (
            "Your system at a glance",
            "Native status, recovery, and performance information stays in one calm workspace.",
        ),
    }
}

fn page_cards(page: &str) -> [(&'static str, &'static str); 2] {
    match page {
        "Play" => [
            ("Gaming library", "Launchers detected"),
            ("Compatibility", "Ready to inspect"),
        ],
        "Apps" => [
            ("App Store", "Trusted software"),
            ("Work setup", "Fonts and printers"),
        ],
        "This PC" => [
            ("Hardware", "Inventory and drivers"),
            ("Diagnostics", "Read-only checks"),
        ],
        "Move In" => [
            ("Move files", "Other systems"),
            ("Network", "Shares and VPN"),
        ],
        "Updates" => [
            ("Deployment", "Image and packages"),
            ("Recovery", "Rollback readiness"),
        ],
        _ => [
            ("Recovery", "Safe by default"),
            ("Performance", "Ready when you are"),
        ],
    }
}

fn cached_array_len(section: &str) -> Option<usize> {
    kyth_shared::system::probe::read_section(section).and_then(|value| value.as_array().map(|items| items.len()))
}

fn page_values(page: &str) -> [String; 2] {
    match page {
        "Play" => {
            let launchers = kyth_shared::system::gaming_library::gaming_library_scan();
            let installed = launchers.iter().filter(|launcher| launcher.installed).count();
            let entries: usize = launchers.iter().filter_map(|launcher| launcher.library_count).sum();
            [format!("{installed} ready"), format!("{entries} library entries")]
        }
        "Apps" => {
            let installed = cached_array_len("flatpak-apps").map(|count| format!("{count} installed")).unwrap_or_else(|| "Not cached".into());
            let updates = kyth_shared::system::probe::read_section("flatpak-updates").and_then(|value| value.as_i64()).map(|count| format!("{count} available")).unwrap_or_else(|| "Not cached".into());
            [installed, updates]
        }
        "This PC" => {
            let capabilities = kyth_shared::system::hardware_view::get_hardware_view_summary().map(|view| view.capabilities.len()).unwrap_or(0);
            let failed = kyth_shared::system::desktop_stack::desktop_stack_checks().iter().filter(|check| !check.passed && !check.advisory).count();
            [format!("{capabilities} capabilities"), if failed == 0 { "All checks pass".into() } else { format!("{failed} need attention") }]
        }
        "Move In" => {
            let summary = kyth_shared::system::probe::read_section("network-summary");
            let shares = summary.as_ref().and_then(|value| value.get("smb_mounts")).and_then(|value| value.as_i64()).unwrap_or(0);
            let providers = summary.as_ref().and_then(|value| value.get("cloud_providers")).and_then(|value| value.as_array()).map(|items| items.len()).unwrap_or(0);
            [format!("{shares} shares"), format!("{providers} cloud providers")]
        }
        "Updates" => {
            let status = kyth_shared::system::update_status::check_update_status();
            [match status.check_state.as_str() { "available" => "Available".into(), "error" => "Unavailable".into(), _ => "Up to date".into() }, if status.rollback { "Rollback ready".into() } else if status.staged { "Restart required".into() } else { "No restart needed".into() }]
        }
        _ => {
            let recovery = kyth_shared::system::recovery_status::get_recovery_status();
            let boot = kyth_shared::system::boot_runtime::boot_runtime_checks();
            [if recovery.quarantined_digest.is_empty() { "Protected".into() } else { "Attention".into() }, format!("{} boot checks", boot.len())]
        }
    }
}

fn page_sections(page: &str) -> [&'static str; 10] {
    match page {
        "Play" => ["Gaming", "Performance", "Compatibility", "Controllers", "", "", "", "", "", ""],
        "Apps" => ["App Store", "Work Setup", "App Images", "Installed apps", "", "", "", "", "", ""],
        "This PC" => ["Guardian", "Hardware", "Plasma Wayland", "Diagnostics", "Repair", "NVIDIA", "Kernel", "Channels", "Recipes", "Feedback"],
        "Move In" => ["Move Files", "Cloud Storage", "Network Shares", "VPN", "", "", "", "", "", ""],
        "Updates" => ["Updates", "Deployment", "Recovery", "History", "", "", "", "", "", ""],
        _ => ["Recovery", "Performance", "Hardware", "Diagnostics", "", "", "", "", "", ""],
    }
}

fn set_section_names(window: &HubWindow, sections: [&str; 10]) {
    window.set_section_one(SharedString::from(sections[0]));
    window.set_section_two(SharedString::from(sections[1]));
    window.set_section_three(SharedString::from(sections[2]));
    window.set_section_four(SharedString::from(sections[3]));
    window.set_section_five(SharedString::from(sections[4]));
    window.set_section_six(SharedString::from(sections[5]));
    window.set_section_seven(SharedString::from(sections[6]));
    window.set_section_eight(SharedString::from(sections[7]));
    window.set_section_nine(SharedString::from(sections[8]));
    window.set_section_ten(SharedString::from(sections[9]));
}

fn section_status(section: &str) -> (String, String) {
    match section {
        "Gaming" => {
            let launchers = kyth_shared::system::gaming_library::gaming_library_scan();
            let installed = launchers.iter().filter(|launcher| launcher.installed).count();
            let libraries: usize = launchers.iter().filter_map(|launcher| launcher.library_count).sum();
            (format!("{installed} gaming launcher(s) detected"), format!("{libraries} library entr{} found in local launcher data.", if libraries == 1 { "y" } else { "ies" }))
        }
        "Performance" => {
            let audit = kyth_shared::system::probe::read_section("audit-cache");
            let profile = audit.as_ref().and_then(|value| value.get("master")).and_then(serde_json::Value::as_str).unwrap_or("not cached");
            (format!("Performance profile · {profile}"), "Open the full performance page to inspect scheduler, power, audio, and tuning state.".into())
        }
        "Compatibility" => {
            let secure_boot = kyth_shared::system::probe::read_section("secureboot-state").and_then(|value| value.as_str().map(str::to_string)).unwrap_or_else(|| "not cached".into());
            let mesa = kyth_shared::system::probe::read_section("mesa_version").and_then(|value| value.as_str().map(str::to_string)).unwrap_or_else(|| "not cached".into());
            (format!("Secure Boot · {secure_boot}"), format!("Mesa driver information · {mesa}"))
        }
        "Controllers" => {
            let cached = kyth_shared::system::probe::read_section("controllers-detect");
            let count = cached.as_ref().and_then(|value| value.get("usb_controllers")).and_then(serde_json::Value::as_array).map_or(0, Vec::len);
            (format!("{count} controller(s) in the latest scan"), "Rescan from the controller section when a device is connected or resumed.".into())
        }
        "App Store" => {
            let installed = cached_array_len("flatpak-apps").unwrap_or(0);
            let updates = kyth_shared::system::probe::read_section("flatpak-updates").and_then(|value| value.as_i64()).unwrap_or(0);
            (format!("{installed} installed Flatpak(s)"), format!("{updates} update(s) reported · installs remain explicit and reviewable."))
        }
        "Work Setup" => {
            let (ready, detail) = kyth_shared::system::fonts_ready::fonts_ready();
            (if ready { "Workday essentials ready" } else { "Workday setup needs attention" }.into(), detail)
        }
        "App Images" => {
            let count = kyth_shared::system::software_catalog::appimages().len();
            (format!("{count} AppImage(s) discovered"), "AppImages are inspected locally; launching remains an explicit user action.".into())
        }
        "Installed apps" => {
            let count = kyth_shared::system::software_catalog::installed_flatpaks().len();
            (format!("{count} installed application(s)"), "Inventory is read-only until you explicitly choose an app action.".into())
        }
        "Guardian" => {
            let state = kyth_shared::guardian::load_state();
            let pending = kyth_shared::guardian::pending_recommendations(&state).len();
            (if pending == 0 { "Guardian is clear" } else { "Guardian has recommendations" }.into(), format!("{pending} pending item(s) · automatic repairs stay policy-gated."))
        }
        "Hardware" => match kyth_shared::system::hardware_view::get_hardware_view_summary() {
            Some(view) => (format!("{} hardware capability(ies)", view.capabilities.len()), if view.has_nvidia && view.is_hybrid { "Hybrid NVIDIA graphics detected." } else { "Hardware inventory is available." }.into()),
            None => ("Hardware inventory not cached".into(), "Refresh to read the current hardware view.".into()),
        },
        "Plasma Wayland" => {
            let checks = kyth_shared::system::desktop_stack::desktop_stack_checks();
            let failed = checks.iter().filter(|check| !check.passed && !check.advisory).count();
            (if failed == 0 { "Desktop stack looks good" } else { "Desktop stack needs attention" }.into(), format!("{} check(s) reported · advisory session checks are shown separately.", checks.len()))
        }
        "Diagnostics" => {
            let report = kyth_shared::doctor::collect_report();
            let suggestions = report.suggestions.len();
            (
                format!("KythOS health · {}/100", report.score),
                if suggestions == 0 {
                    "The latest read-only health evaluation has no suggested repairs.".into()
                } else {
                    format!("{suggestions} suggested follow-up(s) · repair actions remain explicit and policy-gated.")
                },
            )
        }
        "Move Files" => {
            let ntfs = kyth_shared::system::probe::read_section("ntfs-drives").and_then(|value| value.as_array().map(Vec::len)).unwrap_or(0);
            (format!("{ntfs} Windows drive(s) discovered"), "Files and saves are never copied without an explicit reviewed action.".into())
        }
        "Cloud Storage" => {
            let summary = kyth_shared::system::probe::read_section("network-summary");
            let count = summary.as_ref().and_then(|value| value.get("cloud_providers")).and_then(serde_json::Value::as_array).map_or(0, Vec::len);
            (format!("{count} cloud provider(s) configured"), "Credentials remain outside the native status surface.".into())
        }
        "Network Shares" => {
            let summary = kyth_shared::system::probe::read_section("network-summary");
            let count = summary.as_ref().and_then(|value| value.get("smb_mounts")).and_then(serde_json::Value::as_i64).unwrap_or(0);
            (format!("{count} SMB share(s) mounted"), "Browse and mount operations remain explicit network actions.".into())
        }
        "VPN" => {
            let summary = kyth_shared::system::probe::read_section("network-summary");
            let connected = summary.as_ref().and_then(|value| value.get("vpn_connected")).and_then(serde_json::Value::as_bool).unwrap_or(false);
            (if connected { "VPN connected" } else { "No active VPN reported" }.into(), "Refresh the network identity when a connection changes.".into())
        }
        "Updates" | "Deployment" => {
            let status = kyth_shared::system::update_status::check_update_status();
            (format!("Update state · {}", status.check_state), status.detail)
        }
        "Recovery" => {
            let recovery = kyth_shared::system::recovery_status::get_recovery_status();
            (kyth_shared::system::recovery_status::recovery_banner(&recovery), if recovery.quarantined_digest.is_empty() { "Rollback and staged deployment state are read from the shared recovery view.".into() } else { recovery.quarantine_detail })
        }
        "History" => {
            let count = kyth_shared::system::deployment_history::deployment_history().len();
            (format!("{count} deployment entr{}", if count == 1 { "y" } else { "ies" }), "Deployment history is read-only in the native surface.".into())
        }
        "NVIDIA" => match kyth_shared::system::hardware_view::get_hardware_view_summary() {
            Some(view) if view.has_nvidia => ("NVIDIA graphics detected".into(), if view.is_hybrid { "Hybrid graphics path is available for inspection." } else { "Open the driver section to inspect the installed stack." }.into()),
            Some(_) => ("No NVIDIA graphics detected".into(), "The native status surface found no NVIDIA device in the current hardware view.".into()),
            None => ("NVIDIA status not cached".into(), "Refresh to read the current hardware inventory.".into()),
        },
        "Kernel" => {
            let flavor = kyth_shared::system::bootc::current_kernel_flavor();
            (format!("Kernel flavor · {flavor}"), "Kernel switching remains an explicit reviewed action.".into())
        }
        "Channels" => {
            let branch = kyth_shared::system::bootc::current_branch().unwrap_or_else(|| "not cached".into());
            (format!("Update channel · {branch}"), "Channel changes are staged through the guarded update path.".into())
        }
        "Recipes" => ("Recipes ready to inspect".into(), "Native status never opens a terminal; recipe execution remains captured by the Hub runner.".into()),
        "Feedback" => ("Feedback is ready".into(), "Use the feedback page to prepare a report without exposing private diagnostics by default.".into()),
        _ => ("Section ready to inspect".into(), "Choose the corresponding native page for full details.".into()),
    }
}

fn initial_page() -> String {
    let requested = std::env::args()
        .collect::<Vec<_>>()
        .windows(2)
        .find_map(|args| (args[0] == "--page").then(|| args[1].clone()));
    landing_for_page(requested.as_deref().unwrap_or("Home")).to_string()
}

fn landing_for_page(page: &str) -> &'static str {
    match page {
        "Play" | "Gaming" | "Performance" | "Compatibility" | "Controllers" => "Play",
        "Apps" | "App Store" | "Work Setup" => "Apps",
        "This PC" | "Guardian" | "Hardware" | "Plasma Wayland" | "Diagnostics" | "Repair" | "NVIDIA" | "Kernel" | "Channels" | "Just" | "Feedback" => "This PC",
        "Move In" | "Move Files" | "Cloud Storage" | "Network Shares" | "VPN" => "Move In",
        "Updates" => "Updates",
        _ => "Home",
    }
}

fn page_action_detail(recipe: &str, output: &std::process::Output) -> String {
    let mut text = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr);
    if !stderr.trim().is_empty() {
        if !text.is_empty() { text.push('\n'); }
        text.push_str(&stderr);
    }
    let text = kyth_shared::system::process::strip_ansi(text.trim());
    let detail = text.chars().take(500).collect::<String>();
    if !detail.trim().is_empty() {
        return if output.status.success() {
            format!("{recipe} complete · {}", detail.trim())
        } else {
            format!("{recipe} failed · {}", detail.trim())
        };
    }
    if output.status.success() {
        format!("{recipe} complete")
    } else {
        format!("{recipe} failed (exit code {})", output.status.code().unwrap_or(-1))
    }
}

fn run_page_action(weak: Weak<HubWindow>, action: String) {
    let (recipe, label) = match action.as_str() {
        "upgrade" => ("upgrade", "Starting update…"),
        "rollback" => ("rollback", "Starting rollback…"),
        _ => {
            let _ = slint::invoke_from_event_loop(move || {
                if let Some(window) = weak.upgrade() {
                    window.set_action_status(SharedString::from("Unknown native action."));
                }
            });
            return;
        }
    };
    if recipe == "upgrade"
        && !std::path::Path::new("/usr/bin/bootc").exists()
        && !std::path::Path::new("/usr/bin/rpm-ostree").exists()
    {
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                window.set_action_status(SharedString::from("bootc is not installed on this system."));
            }
        });
        return;
    }
    let Some(argv) = kyth_shared::system::just::command_for(recipe, &[]) else {
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                window.set_action_status(SharedString::from("Native action is not allowlisted."));
            }
        });
        return;
    };
    let _ = slint::invoke_from_event_loop({
        let weak = weak.clone();
        move || {
            if let Some(window) = weak.upgrade() {
                window.set_action_status(SharedString::from(label));
            }
        }
    });
    let refresh_weak = weak.clone();
    std::thread::spawn(move || {
        let mut command = Command::new(&argv[0]);
        command.args(&argv[1..]);
        let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
        let sanitized = kyth_shared::commands::environment_for(
            kyth_shared::commands::EnvironmentPolicy::Sanitized,
            &inherited,
        );
        command.env_clear().envs(sanitized);
        kyth_shared::system::just::configure_command(&mut command);
        if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
            command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
        }
        let result = kyth_shared::system::process::run_bounded_command(command, Duration::from_secs(900));
        let detail = match result {
            Ok(output) => page_action_detail(recipe, &output),
            Err(error) => format!("{recipe} could not start · {error}"),
        };
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                window.set_action_status(SharedString::from(detail));
            }
        });
        refresh_status(refresh_weak, "Updates".to_string());
    });
}

fn refresh_status(weak: Weak<HubWindow>, page: String) {
    std::thread::spawn(move || {
        let result = page_status(&page);
        let (summary, detail) = page_copy(&page);
        let cards = page_cards(&page);
        let values = page_values(&page);
        let next_action = (page == "Home").then(home_next_action).unwrap_or_else(|| "Suggested next step · Open a section to review details".to_string());
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                if window.get_selected_page().as_str() != page {
                    return;
                }
                window.set_page_summary(SharedString::from(summary));
                window.set_page_detail(SharedString::from(detail));
                window.set_card_one_title(SharedString::from(cards[0].0));
                window.set_card_one_value(SharedString::from(values[0].as_str()));
                window.set_card_one_detail(SharedString::from(cards[0].1));
                window.set_card_two_title(SharedString::from(cards[1].0));
                window.set_card_two_value(SharedString::from(values[1].as_str()));
                window.set_card_two_detail(SharedString::from(cards[1].1));
                window.set_next_action_text(SharedString::from(next_action));
                window.set_status_text(SharedString::from(result));
            }
        });
    });
}

fn refresh_section(weak: Weak<HubWindow>, section: String) {
    std::thread::spawn(move || {
        let (status, detail) = section_status(&section);
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                if window.get_selected_section().as_str() != section {
                    return;
                }
                window.set_section_status(SharedString::from(status));
                window.set_section_detail(SharedString::from(detail));
            }
        });
    });
}

fn main() -> Result<(), slint::PlatformError> {
    let page = initial_page();
    let window = HubWindow::new()?;
    window.set_selected_page(SharedString::from(page.as_str()));
    let sections = page_sections(&page);
    set_section_names(&window, sections);
    window.set_selected_section(SharedString::from(sections[0]));
    let (summary, detail) = page_copy(&page);
    let cards = page_cards(&page);
    window.set_page_summary(SharedString::from(summary));
    window.set_page_detail(SharedString::from(detail));
    window.set_card_one_title(SharedString::from(cards[0].0));
    window.set_card_one_value(SharedString::from("Reading…"));
    window.set_card_one_detail(SharedString::from(cards[0].1));
    window.set_card_two_title(SharedString::from(cards[1].0));
    window.set_card_two_value(SharedString::from("Reading…"));
    window.set_card_two_detail(SharedString::from(cards[1].1));
    window.set_next_action_text(SharedString::from("Suggested next step · Reading local policy…"));
    window.set_status_text(SharedString::from("Reading system status…"));
    window.set_action_status(SharedString::from(""));
    window.set_section_status(SharedString::from("Reading section status…"));
    window.set_section_detail(SharedString::from("Native section status is read in the background."));

    let action_weak = window.as_weak();
    window.on_page_action(move |action| {
        run_page_action(action_weak.clone(), action.to_string());
    });

    let refresh_weak = window.as_weak();
    window.on_refresh(move || {
        if let Some(window) = refresh_weak.upgrade() {
            let page = window.get_selected_page().to_string();
            let section = window.get_selected_section().to_string();
            window.set_status_text(SharedString::from("Refreshing system status…"));
            window.set_section_status(SharedString::from("Refreshing section status…"));
            refresh_status(refresh_weak.clone(), page);
            refresh_section(refresh_weak.clone(), section);
        }
    });
    let navigation_weak = window.as_weak();
    window.on_navigate(move |page| {
        if let Some(window) = navigation_weak.upgrade() {
            let (summary, detail) = page_copy(page.as_str());
            let cards = page_cards(page.as_str());
            let sections = page_sections(page.as_str());
            window.set_card_one_value(SharedString::from("Reading…"));
            window.set_card_two_value(SharedString::from("Reading…"));
            set_section_names(&window, sections);
            window.set_selected_section(SharedString::from(sections[0]));
            window.set_page_summary(SharedString::from(summary));
            window.set_page_detail(SharedString::from(detail));
            window.set_card_one_title(SharedString::from(cards[0].0));
            window.set_card_one_detail(SharedString::from(cards[0].1));
            window.set_card_two_title(SharedString::from(cards[1].0));
            window.set_card_two_detail(SharedString::from(cards[1].1));
            window.set_next_action_text(SharedString::from("Suggested next step · Reading local policy…"));
            window.set_status_text(SharedString::from("Reading system status…"));
            window.set_action_status(SharedString::from(""));
            window.set_section_status(SharedString::from("Reading section status…"));
            window.set_section_detail(SharedString::from("Native section status is read in the background."));
            refresh_status(navigation_weak.clone(), page.to_string());
            refresh_section(navigation_weak.clone(), sections[0].to_string());
        }
    });
    let section_weak = window.as_weak();
    window.on_select_section(move |section| {
        if let Some(window) = section_weak.upgrade() {
            window.set_selected_section(section.clone());
            window.set_section_status(SharedString::from("Reading section status…"));
            window.set_section_detail(SharedString::from("Native section status is read in the background."));
            refresh_section(section_weak.clone(), section.to_string());
        }
    });
    refresh_status(window.as_weak(), page);
    refresh_section(window.as_weak(), sections[0].to_string());
    window.run()
}
