//! Native Slint Hub shell.
//!
//! This binary is the production Hub surface. It owns the native window and
//! calls the shared Rust read paths directly; the Tauri/React shell remains
//! available only as an explicit rollback path while parity is completed.

slint::include_modules!();

use slint::{ComponentHandle, SharedString, Weak};
use std::process::Command;
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

static PENDING_CONFIRMATION: OnceLock<Mutex<Option<String>>> = OnceLock::new();

fn confirmation_store() -> &'static Mutex<Option<String>> {
    PENDING_CONFIRMATION.get_or_init(|| Mutex::new(None))
}

fn requires_confirmation(action: &str) -> bool {
    matches!(
        action,
        "upgrade"
            | "rollback"
            | "install-ms-fonts"
            | "gaming-mode"
            | "balanced-mode"
            | "firmware-update"
            | "install-ludusavi"
            | "setup-tailscale"
    )
}

/// Native actions use a small two-step confirmation gate. This keeps the
/// Slint shell safe without introducing a generic command or secret bridge.
fn confirmation_granted(action: &str) -> bool {
    let Ok(mut pending) = confirmation_store().lock() else { return false; };
    if pending.as_deref() == Some(action) {
        *pending = None;
        true
    } else {
        *pending = Some(action.to_string());
        false
    }
}

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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PageStatusBadge {
    Healthy,
    ActionReady,
    NeedsAttention,
    Checking,
}

impl PageStatusBadge {
    fn label(self) -> &'static str {
        match self {
            Self::Healthy => "HEALTHY",
            Self::ActionReady => "ACTION READY",
            Self::NeedsAttention => "NEEDS ATTENTION",
            Self::Checking => "CHECKING",
        }
    }
}

fn page_status_badge(status: &str) -> PageStatusBadge {
    if status.is_empty() {
        return PageStatusBadge::Checking;
    }
    if status.contains("attention") || status.contains("unavailable") || status.contains("not cached") || status.contains("not available") {
        return PageStatusBadge::NeedsAttention;
    }
    if status.contains("staged") || status.contains("available") || status.contains("recommendation") {
        return PageStatusBadge::ActionReady;
    }
    PageStatusBadge::Healthy
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
    let snapshot = kyth_shared::system::hub_snapshot::collect();
    match page {
        "Play" => [
            format!("{} ready", snapshot.gaming.installed_launchers),
            if snapshot.gaming.session_count == 0 { format!("{} library entries", snapshot.gaming.library_entries) } else { format!("{} recent sessions", snapshot.gaming.session_count) },
        ],
        "Apps" => [
            format!("{} installed", snapshot.software.installed_flatpaks),
            format!("{} available", snapshot.software.available_flatpak_updates),
        ],
        "This PC" => [
            format!("Health {}/100", snapshot.doctor_score),
            if snapshot.guardian_pending == 0 { "Guardian clear".into() } else { format!("{} Guardian items", snapshot.guardian_pending) },
        ],
        "Move In" => [
            format!("{} Windows drives", snapshot.move_in.ntfs_drives),
            format!("{} cloud providers", snapshot.move_in.cloud_providers),
        ],
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

/// Actions exposed by the native shell are deliberately a fixed projection of
/// read/check operations and parameterless, reviewable just recipes. Anything
/// requiring arguments or privileged socket payloads stays on its fuller page
/// until it has a dedicated native control.
fn section_action(section: &str) -> Option<(&'static str, &'static str)> {
    match section {
        "Gaming" => Some(("gaming-stack-status", "Check gaming stack")),
        "Performance" => Some(("system-audit", "Run performance audit")),
        "Compatibility" => Some(("secureboot-status", "Check Secure Boot")),
        "Controllers" => Some(("controller-check", "Check controllers")),
        "Work Setup" => Some(("install-ms-fonts", "Install Office fonts")),
        "Hardware" => Some(("hardware-inventory", "Refresh hardware inventory")),
        "Plasma Wayland" => Some(("desktop-stack-status", "Check desktop stack")),
        "Diagnostics" => Some(("system-audit", "Run full system audit")),
        "Repair" => Some(("update-health", "Check update health")),
        "Recovery" => Some(("update-health", "Update health report")),
        "NVIDIA" => Some(("nvidia-status", "Read driver status")),
        "Move Files" => Some(("windows-verify", "Check Windows install")),
        "Cloud Storage" | "Network Shares" | "VPN" => Some(("network-status", "Refresh network status")),
        "Deployment" => Some(("update-health", "Check deployment health")),
        "History" => Some(("deployment-history", "Refresh deployment history")),
        "Kernel" => Some(("kernel-status", "Read kernel status")),
        "Channels" => Some(("channel-status", "Read update channel")),
        _ => None,
    }
}

fn set_section_action(window: &HubWindow, section: &str) {
    let (action, label) = section_action(section).unwrap_or(("", ""));
    window.set_section_action_id(SharedString::from(action));
    window.set_section_action_label(SharedString::from(label));
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
            let preview = audit.as_ref().map(|value| {
                kyth_shared::system::perf_audit::format_audit(&value)
                    .lines()
                    .skip(1)
                    .take(4)
                    .collect::<Vec<_>>()
                    .join(" · ")
            });
            let preset = kyth_shared::system::role_preset::load(kyth_shared::system::role_preset::config_path(None::<&str>));
            let preset_detail = format!("Preset preview · {} · {} Flatpak(s) · {} Distrobox(es) · {} editor extension(s)", preset.profile.as_str(), preset.flatpaks.len(), preset.distroboxes.len(), preset.vscode_extensions.len());
            (
                format!("Performance profile · {profile}"),
                preview.map_or_else(
                    || preset_detail.clone(),
                    |preview| format!("{preset_detail} · {preview} · Open the full performance page for the remaining audit buckets."),
                ),
            )
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
            let history = kyth_shared::system::deployment_history::deployment_history();
            let count = history.len();
            let detail = history.iter().filter(|item| item.available).map(|item| format!("{}: {}", item.label, item.short_digest.as_deref().unwrap_or("unknown digest"))).collect::<Vec<_>>().join(" · ");
            (format!("{count} deployment entr{}", if count == 1 { "y" } else { "ies" }), if detail.is_empty() { "No deployment entries are currently available.".into() } else { detail })
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

fn hardware_capabilities_text() -> String {
    match kyth_shared::system::hardware_view::get_hardware_view_summary() {
        Some(view) => {
            let graphics = match (view.has_nvidia, view.is_hybrid) {
                (true, true) => "Hybrid NVIDIA graphics",
                (true, false) => "NVIDIA graphics",
                _ => "Integrated/default graphics",
            };
            let capabilities = if view.capabilities.is_empty() {
                "no additional capabilities reported".to_string()
            } else {
                view.capabilities.join(" · ")
            };
            format!("Capabilities · {graphics} · {capabilities}")
        }
        None => "Capabilities · Hardware capability summary is not cached.".to_string(),
    }
}

fn gaming_launchers_text() -> String {
    let launchers = kyth_shared::system::gaming_library::gaming_library_scan();
    let inventory = launchers
        .iter()
        .map(|launcher| {
            let state = if launcher.installed { "installed" } else { "not installed" };
            let library = launcher
                .library_count
                .map_or_else(|| "library not scanned".to_string(), |count| format!("{count} game(s)"));
            format!("{}: {state}, {library}", launcher.label)
        })
        .collect::<Vec<_>>();
    let anti_cheat = kyth_shared::system::gaming_compat::anti_cheat_table()
        .iter()
        .map(|entry| format!("{}: {}", entry.game, entry.status))
        .collect::<Vec<_>>()
        .join(" · ");
    if inventory.is_empty() {
        "Launchers · No launcher inventory reported.".to_string()
    } else {
        format!("Launchers · {}\nCompatibility · {}\nMigration · verify library titles in ProtonDB before moving saves.", inventory.join(" · "), anti_cheat)
    }
}

fn software_catalog_text() -> String {
    let installed = kyth_shared::system::software_catalog::installed_flatpaks();
    let appimages = kyth_shared::system::software_catalog::appimages();
    let packs = kyth_shared::system::software_catalog::starter_packs();
    let image_names = appimages.iter().take(3).map(|image| image.name.as_str()).collect::<Vec<_>>().join(", ");
    let pack_names = packs.iter().map(|pack| pack.name.as_str()).collect::<Vec<_>>().join(", ");
    format!("Catalog · {} installed Flatpak(s) · {} AppImage(s) · {} starter packs\nAppImages · {}\nPacks · {}", installed.len(), appimages.len(), packs.len(), if image_names.is_empty() { "none discovered" } else { image_names.as_str() }, pack_names)
}

fn appstream_search_view(query: &str) -> (String, String, String) {
    let results = kyth_shared::system::software_catalog::appstream_search(query);
    if results.is_empty() {
        return ("No catalog results found, or the catalog is unavailable.".to_string(), String::new(), String::new());
    }
    let first = &results[0];
    let text = results.iter().take(10).map(|app| format!("{} · {} — {}", app.id, app.name, app.summary)).collect::<Vec<_>>().join("\n");
    (text, first.id.clone(), format!("Install {}", first.name))
}

fn run_appstream_install(weak: Weak<HubWindow>, app_id: String, label: String) {
    let confirmation_key = format!("install-flatpak:{app_id}");
    if !confirmation_granted(&confirmation_key) {
        let status_weak = weak.clone();
        let _ = slint::invoke_from_event_loop(move || if let Some(window) = status_weak.upgrade() {
            window.set_action_busy(false);
            window.set_action_status(SharedString::from("Installing an application changes this user profile · click Install again to confirm"));
        });
        return;
    }
    let Some(argv) = kyth_shared::system::software_catalog::flatpak_install_argv(&app_id) else {
        let _ = slint::invoke_from_event_loop(move || if let Some(window) = weak.upgrade() {
            window.set_action_busy(false);
            window.set_action_status(SharedString::from("The catalog returned an invalid application id."));
        });
        return;
    };
    let refresh_weak = weak.clone();
    let refresh_page = weak
        .upgrade()
        .map(|window| window.get_selected_page().to_string())
        .unwrap_or_else(|| "Apps".to_string());
    let _ = slint::invoke_from_event_loop({
        let weak = weak.clone();
        let label = label.clone();
        move || if let Some(window) = weak.upgrade() {
            window.set_action_busy(true);
            window.set_action_status(SharedString::from(format!("{label}…")));
        }
    });
    std::thread::spawn(move || {
        let result = kyth_shared::system::process::run_bounded(&argv, Duration::from_secs(600));
        let detail = match result {
            Ok(output) => page_action_detail(&label, &output),
            Err(error) => format!("{label} could not start · {error}"),
        };
        let _ = slint::invoke_from_event_loop(move || if let Some(window) = weak.upgrade() {
            window.set_action_busy(false);
            window.set_action_status(SharedString::from(detail));
        });
        refresh_status(refresh_weak.clone(), refresh_page);
        refresh_section(refresh_weak, "App Store".to_string());
    });
}

fn guardian_status_text() -> String {
    let state = kyth_shared::guardian::load_state();
    let recommendations = kyth_shared::guardian::pending_recommendations(&state);
    let pending = recommendations.len();
    let quarantined = kyth_shared::system::boot_health::read_default_state().quarantined.len();
    let names = recommendations.iter().take(3).map(|item| item.recipe_id.as_str()).collect::<Vec<_>>().join(", ");
    if names.is_empty() {
        format!("Guardian · clear · {quarantined} quarantined item(s)")
    } else {
        format!("Guardian · {pending} pending · {quarantined} quarantined · {names}")
    }
}

fn recipes_text() -> String {
    let recipes = kyth_shared::system::just::just_list();
    if recipes.is_empty() {
        return "Recipes · The system recipe list is unavailable right now.".to_string();
    }
    let rows = recipes
        .iter()
        .take(30)
        .map(|recipe| {
            let params = if recipe.params.is_empty() { String::new() } else { format!(" {}", recipe.params) };
            let comment = if recipe.comment.is_empty() { String::new() } else { format!(" — {}", recipe.comment) };
            format!("{}{}{}", recipe.name, params, comment)
        })
        .collect::<Vec<_>>();
    format!("Recipes · {} available (showing up to 30)\n{}", recipes.len(), rows.join("\n"))
}

fn initial_page() -> String {
    let requested = initial_requested_page();
    landing_for_page(requested.as_deref().unwrap_or("Home")).to_string()
}

fn initial_requested_page() -> Option<String> {
    std::env::args()
        .collect::<Vec<_>>()
        .windows(2)
        .find_map(|args| (args[0] == "--page").then(|| args[1].clone()))
}

/// Resolve a section deep link to the native tab that should be selected.
///
/// The React shell encodes section links as `?section=...`; the native
/// launcher has the same single `--page` argument, so section keys are
/// selected here after the destination is resolved. Keep the `Just` alias
/// because older desktop entries used that registry key while the native
/// label is "Recipes".
fn initial_section(page: &str) -> String {
    let sections = page_sections(page);
    let requested = initial_requested_page();
    let selected = match requested.as_deref() {
        Some("Just") if page == "This PC" => "Recipes",
        Some("Update") if page == "Updates" => "Updates",
        Some(requested) => sections
            .iter()
            .copied()
            .find(|section| *section == requested)
            .unwrap_or(sections[0]),
        None => sections[0],
    };
    selected.to_string()
}

fn landing_for_page(page: &str) -> &'static str {
    match page {
        "Play" | "Gaming" | "Performance" | "Compatibility" | "Controllers" => "Play",
        "Apps" | "App Store" | "Work Setup" => "Apps",
        "This PC" | "Guardian" | "Hardware" | "Plasma Wayland" | "Diagnostics" | "Repair" | "NVIDIA" | "Kernel" | "Channels" | "Just" | "Feedback" => "This PC",
        "Move In" | "Move Files" | "Cloud Storage" | "Network Shares" | "VPN" => "Move In",
        "Update" | "Updates" => "Updates",
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
    if action == "guardian" {
        let _ = slint::invoke_from_event_loop({
            let weak = weak.clone();
            move || if let Some(window) = weak.upgrade() {
                window.set_action_busy(true);
                window.set_action_status(SharedString::from("Checking Guardian policy…"));
            }
        });
        std::thread::spawn(move || {
            let state = kyth_shared::guardian::load_state();
            let result = kyth_shared::guardian::pending_recommendations(&state).first()
                .map(|item| kyth_shared::guardian::execute_recipe(&item.recipe_id))
                .unwrap_or_else(|| Err("No pending Guardian repair is available.".to_string()));
            let detail = result.unwrap_or_else(|error| format!("Guardian repair not run · {error}"));
            let _ = slint::invoke_from_event_loop(move || if let Some(window) = weak.upgrade() {
                window.set_action_busy(false);
                window.set_action_status(SharedString::from(detail));
            });
        });
        return;
    }
    if matches!(
        action.as_str(),
        "desktop-stack-status" | "network-status" | "deployment-history" | "kernel-status" | "channel-status"
    ) {
        let Some(window) = weak.upgrade() else { return; };
        let page = window.get_selected_page().to_string();
        let section = window.get_selected_section().to_string();
        window.set_action_busy(true);
        window.set_action_status(SharedString::from("Refreshing native status…"));
        let status_weak = weak.clone();
        std::thread::spawn(move || {
            let _ = slint::invoke_from_event_loop(move || if let Some(window) = status_weak.upgrade() {
                window.set_action_busy(false);
                window.set_action_status(SharedString::from("Native status refreshed."));
            });
        });
        refresh_status(weak.clone(), page);
        refresh_section(weak, section);
        return;
    }
    if requires_confirmation(&action) && !confirmation_granted(&action) {
        let message = format!("{action} is a system-changing action · click the same button again to confirm");
        let _ = slint::invoke_from_event_loop(move || if let Some(window) = weak.upgrade() {
            window.set_action_busy(false);
            window.set_action_status(SharedString::from(message));
        });
        return;
    }
    let (recipe, label) = match action.as_str() {
        "upgrade" => ("upgrade", "Starting update…"),
        "rollback" => ("rollback", "Starting rollback…"),
        "gaming-stack-status" => ("gaming-stack-status", "Checking gaming stack…"),
        "system-audit" => ("system-audit", "Running system audit…"),
        "install-ms-fonts" => ("install-ms-fonts", "Installing Office fonts…"),
        "update-health" => ("update-health", "Updating health report…"),
        "nvidia-status" => ("nvidia-status", "Reading NVIDIA status…"),
        "secureboot-status" => ("secureboot-status", "Reading Secure Boot status…"),
        "controller-check" => ("controller-check", "Checking controller stack…"),
        "hardware-inventory" => ("hardware-inventory", "Refreshing hardware inventory…"),
        "desktop-stack-status" => ("desktop-stack-status", "Checking desktop stack…"),
        "network-status" => ("network-status", "Refreshing network status…"),
        "deployment-history" => ("deployment-history", "Refreshing deployment history…"),
        "kernel-status" => ("kernel-status", "Reading kernel status…"),
        "channel-status" => ("channel-status", "Reading update channel…"),
        "gaming-mode" => ("gaming-mode", "Switching to gaming profile…"),
        "balanced-mode" => ("balanced-mode", "Restoring balanced profile…"),
        "firmware-update" => ("firmware-update", "Applying firmware updates…"),
        "install-ludusavi" => ("install-ludusavi", "Installing save migration tools…"),
        "setup-tailscale" => ("setup-tailscale", "Setting up Tailscale…"),
        _ => {
            let _ = slint::invoke_from_event_loop(move || {
                if let Some(window) = weak.upgrade() {
                    window.set_action_busy(false);
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
                window.set_action_busy(false);
                window.set_action_status(SharedString::from("bootc is not installed on this system."));
            }
        });
        return;
    }
    let Some(argv) = kyth_shared::system::just::command_for(recipe, &[]) else {
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                window.set_action_busy(false);
                window.set_action_status(SharedString::from("Native action is not allowlisted."));
            }
        });
        return;
    };
    let _ = slint::invoke_from_event_loop({
        let weak = weak.clone();
        move || {
            if let Some(window) = weak.upgrade() {
                window.set_action_busy(true);
                window.set_action_status(SharedString::from(label));
            }
        }
    });
    let refresh_weak = weak.clone();
    let refresh_page = weak
        .upgrade()
        .map(|window| window.get_selected_page().to_string())
        .unwrap_or_else(|| "Updates".to_string());
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
                window.set_action_busy(false);
                window.set_action_status(SharedString::from(detail));
            }
        });
        refresh_status(refresh_weak, refresh_page);
    });
}

fn refresh_status(weak: Weak<HubWindow>, page: String) {
    std::thread::spawn(move || {
        let result = page_status(&page);
        let badge = page_status_badge(&result).label().to_string();
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
                window.set_status_badge(SharedString::from(badge));
            }
        });
    });
}

fn refresh_section(weak: Weak<HubWindow>, section: String) {
    std::thread::spawn(move || {
        let (status, detail) = section_status(&section);
        let capabilities = (section == "Hardware").then(hardware_capabilities_text).unwrap_or_default();
        let launchers = (section == "Gaming").then(gaming_launchers_text).unwrap_or_default();
        let software = (section == "App Store").then(software_catalog_text).unwrap_or_default();
        let guardian = (section == "Guardian").then(guardian_status_text).unwrap_or_default();
        let recipes = (section == "Recipes").then(recipes_text).unwrap_or_default();
        let _ = slint::invoke_from_event_loop(move || {
            if let Some(window) = weak.upgrade() {
                if window.get_selected_section().as_str() != section {
                    return;
                }
                window.set_section_status(SharedString::from(status));
                window.set_section_detail(SharedString::from(detail));
                window.set_hardware_capabilities(SharedString::from(capabilities));
                window.set_gaming_launchers(SharedString::from(launchers));
                window.set_software_catalog(SharedString::from(software));
                window.set_guardian_status(SharedString::from(guardian));
                window.set_recipes_text(SharedString::from(recipes));
            }
        });
    });
}

fn main() -> Result<(), slint::PlatformError> {
    let page = initial_page();
    let section = initial_section(&page);
    let window = HubWindow::new()?;
    window.set_selected_page(SharedString::from(page.as_str()));
    let sections = page_sections(&page);
    set_section_names(&window, sections);
    window.set_selected_section(SharedString::from(section.as_str()));
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
    set_section_action(&window, &section);
    window.set_next_action_text(SharedString::from("Suggested next step · Reading local policy…"));
    window.set_status_text(SharedString::from("Reading system status…"));
    window.set_action_status(SharedString::from(""));
    window.set_action_busy(false);
    window.set_status_badge(SharedString::from("CHECKING"));
    window.set_section_status(SharedString::from("Reading section status…"));
    window.set_section_detail(SharedString::from("Native section status is read in the background."));
    window.set_hardware_capabilities(SharedString::from("Capabilities · Reading hardware view…"));
    window.set_gaming_launchers(SharedString::from("Launchers · Reading gaming inventory…"));
    window.set_software_catalog(SharedString::from("Catalog · Reading software inventory…"));
    window.set_guardian_status(SharedString::from("Guardian · Reading recommendations…"));
    window.set_recipes_text(SharedString::from("Recipes · Reading available actions…"));
    window.set_appstream_install_id(SharedString::from(""));
    window.set_appstream_install_label(SharedString::from(""));

    let action_weak = window.as_weak();
    window.on_page_action(move |action| {
        run_page_action(action_weak.clone(), action.to_string());
    });
    let section_action_weak = window.as_weak();
    window.on_section_action(move |action| {
        run_page_action(section_action_weak.clone(), action.to_string());
    });
    let search_weak = window.as_weak();
    window.on_appstream_search(move |query| {
        let weak = search_weak.clone();
        let query = query.to_string();
        std::thread::spawn(move || {
            let (results, install_id, install_label) = appstream_search_view(&query);
            let _ = slint::invoke_from_event_loop(move || if let Some(window) = weak.upgrade() {
                window.set_appstream_results(SharedString::from(results));
                window.set_appstream_install_id(SharedString::from(install_id));
                window.set_appstream_install_label(SharedString::from(install_label));
            });
        });
    });
    let install_weak = window.as_weak();
    window.on_appstream_install(move |app_id| {
        let app_id = app_id.to_string();
        run_appstream_install(install_weak.clone(), app_id.clone(), format!("Installing {app_id}"));
    });

    let refresh_weak = window.as_weak();
    window.on_refresh(move || {
        if let Some(window) = refresh_weak.upgrade() {
            let page = window.get_selected_page().to_string();
            let section = window.get_selected_section().to_string();
            window.set_status_text(SharedString::from("Refreshing system status…"));
            window.set_status_badge(SharedString::from("CHECKING"));
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
            set_section_action(&window, sections[0]);
            window.set_next_action_text(SharedString::from("Suggested next step · Reading local policy…"));
            window.set_status_text(SharedString::from("Reading system status…"));
            window.set_action_status(SharedString::from(""));
            window.set_action_busy(false);
            window.set_status_badge(SharedString::from("CHECKING"));
            window.set_section_status(SharedString::from("Reading section status…"));
            window.set_section_detail(SharedString::from("Native section status is read in the background."));
            window.set_hardware_capabilities(SharedString::from("Capabilities · Reading hardware view…"));
            window.set_gaming_launchers(SharedString::from("Launchers · Reading gaming inventory…"));
            window.set_software_catalog(SharedString::from("Catalog · Reading software inventory…"));
            window.set_guardian_status(SharedString::from("Guardian · Reading recommendations…"));
            window.set_recipes_text(SharedString::from("Recipes · Reading available actions…"));
            window.set_appstream_install_id(SharedString::from(""));
            window.set_appstream_install_label(SharedString::from(""));
            refresh_status(navigation_weak.clone(), page.to_string());
            refresh_section(navigation_weak.clone(), sections[0].to_string());
        }
    });
    let section_weak = window.as_weak();
    window.on_select_section(move |section| {
        if let Some(window) = section_weak.upgrade() {
            window.set_selected_section(section.clone());
            set_section_action(&window, section.as_str());
            window.set_section_status(SharedString::from("Reading section status…"));
            window.set_section_detail(SharedString::from("Native section status is read in the background."));
            window.set_hardware_capabilities(SharedString::from("Capabilities · Reading hardware view…"));
            window.set_gaming_launchers(SharedString::from("Launchers · Reading gaming inventory…"));
            window.set_software_catalog(SharedString::from("Catalog · Reading software inventory…"));
            window.set_guardian_status(SharedString::from("Guardian · Reading recommendations…"));
            window.set_recipes_text(SharedString::from("Recipes · Reading available actions…"));
            window.set_appstream_install_id(SharedString::from(""));
            window.set_appstream_install_label(SharedString::from(""));
            window.set_action_status(SharedString::from(""));
            window.set_action_busy(false);
            refresh_section(section_weak.clone(), section.to_string());
        }
    });
    refresh_status(window.as_weak(), page);
    refresh_section(window.as_weak(), section);
    window.run()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deep_links_land_on_the_same_native_workspace() {
        assert_eq!(landing_for_page("Performance"), "Play");
        assert_eq!(landing_for_page("App Store"), "Apps");
        assert_eq!(landing_for_page("Repair"), "This PC");
        assert_eq!(landing_for_page("VPN"), "Move In");
        assert_eq!(landing_for_page("Updates"), "Updates");
        assert_eq!(landing_for_page("unknown"), "Home");
    }

    #[test]
    fn every_native_workspace_has_a_primary_section_and_updates_are_separate() {
        for page in ["Home", "Play", "Apps", "This PC", "Move In", "Updates"] {
            assert!(!page_sections(page)[0].is_empty(), "{page} has no primary section");
        }
        assert_eq!(&page_sections("Updates")[..5], ["Updates", "Deployment", "Recovery", "History", ""]);
        assert_eq!(page_sections("This PC")[9], "Feedback");
    }

    #[test]
    fn native_status_badges_are_honest_about_cached_state() {
        assert_eq!(page_status_badge("System checks look good").label(), "HEALTHY");
        assert_eq!(page_status_badge("Update staged · restart when ready").label(), "ACTION READY");
        assert_eq!(page_status_badge("Update status unavailable · source failed").label(), "NEEDS ATTENTION");
        assert_eq!(page_status_badge("2 desktop check(s) need attention").label(), "NEEDS ATTENTION");
        assert_eq!(page_status_badge("Application inventory is not cached yet").label(), "NEEDS ATTENTION");
        assert_eq!(page_status_badge("").label(), "CHECKING");
    }

    #[test]
    fn native_section_actions_are_fixed_and_parameterless() {
        assert_eq!(section_action("Gaming"), Some(("gaming-stack-status", "Check gaming stack")));
        assert_eq!(section_action("Compatibility"), Some(("secureboot-status", "Check Secure Boot")));
        assert_eq!(section_action("Controllers"), Some(("controller-check", "Check controllers")));
        assert_eq!(section_action("Hardware"), Some(("hardware-inventory", "Refresh hardware inventory")));
        assert_eq!(section_action("Diagnostics"), Some(("system-audit", "Run full system audit")));
        assert_eq!(section_action("Plasma Wayland"), Some(("desktop-stack-status", "Check desktop stack")));
        assert_eq!(section_action("Move Files"), Some(("windows-verify", "Check Windows install")));
        assert_eq!(section_action("VPN"), Some(("network-status", "Refresh network status")));
        assert_eq!(section_action("Channels"), Some(("channel-status", "Read update channel")));
    }

    #[test]
    fn system_changing_actions_are_confirmation_gated() {
        for action in ["upgrade", "rollback", "gaming-mode", "balanced-mode", "firmware-update", "setup-tailscale"] {
            assert!(requires_confirmation(action), "{action} must require confirmation");
        }
        assert!(!requires_confirmation("system-audit"));
        assert!(!requires_confirmation("hardware-inventory"));
    }
}
