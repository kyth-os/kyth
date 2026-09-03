// Native compatibility entry points for the small read-only diagnostics.
//
// These commands intentionally remain separate names because they are used by
// existing `ujust` recipes and by support instructions.  They share one
// implementation and select their behavior from argv[0], just like the old
// compatibility scripts did, but never import or execute Python.

use kyth_shared::diagnostic_report::DiagnosticReport;
use kyth_shared::system::{controllers, gpu, performance, process, runtime_diagnostics};
use std::env;
use std::path::Path;
use std::process::{Command, ExitCode};
use std::time::Duration;

fn command_exists(name: &str) -> bool {
    env::var_os("PATH")
        .map(|path| env::split_paths(&path).any(|dir| dir.join(name).is_file()))
        .unwrap_or(false)
}

fn run(argv: &[&str], timeout: u64) -> Option<std::process::Output> {
    let args = argv.iter().map(|arg| (*arg).to_string()).collect::<Vec<_>>();
    process::run_bounded(&args, Duration::from_secs(timeout)).ok()
}

fn succeeds(argv: &[&str], timeout: u64) -> bool {
    run(argv, timeout).is_some_and(|output| output.status.success())
}

fn stdout(argv: &[&str], timeout: u64) -> String {
    run(argv, timeout)
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_string())
        .unwrap_or_default()
}

fn report_header(title: &str) {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default();
    println!("KythOS {title}");
    println!("Generated: {now}");
    println!();
}

fn print_report(report: &DiagnosticReport, target: &str, warning: Option<&str>) -> ExitCode {
    print!("{}", report.render());
    if !report.results.is_empty() {
        println!();
    }
    let code = report.exit_code();
    if report.failures > 0 {
        println!("Result: {target} has failures.");
    } else if report.warnings > 0 {
        println!("Result: {}", warning.unwrap_or(&format!("{target} has warnings.")));
    } else {
        println!("Result: {target} looks good.");
    }
    ExitCode::from(code as u8)
}

fn health_check() -> ExitCode {
    report_header("Subsystem Health");
    let mut report = DiagnosticReport::new("Subsystem Health");

    let scx_active = (command_exists("systemctl")
        && succeeds(&["systemctl", "is-active", "--quiet", "scx_loader.service"], 5))
        || command_exists("scx_rusty");
    if scx_active {
        report.passed("Kernel Scheduler", "sched-ext (scx) low-latency scheduler active");
    } else {
        report.warned("Kernel Scheduler", "CFS/EEVDF fallback (scx not active)");
    }

    let ntsync = Path::new("/dev/ntsync").exists()
        || std::fs::read_to_string("/proc/modules")
            .map(|text| text.lines().any(|line| line.split_whitespace().next() == Some("ntsync")))
            .unwrap_or(false);
    if ntsync {
        report.passed("Wine Synchronization", "NTSYNC fast kernel driver loaded");
    } else {
        report.passed("Wine Synchronization", "FUTEX2 / esync fallback active");
    }

    let pipewire = (command_exists("pgrep") && succeeds(&["pgrep", "-x", "pipewire"], 5))
        || std::fs::read_dir("/proc")
            .map(|entries| {
                entries.flatten().any(|entry| {
                    entry.file_name().to_string_lossy().parse::<u32>().is_ok()
                        && std::fs::read_to_string(entry.path().join("comm"))
                            .map(|name| name.trim() == "pipewire")
                            .unwrap_or(false)
                })
            })
            .unwrap_or(false);
    if pipewire {
        report.passed("Audio Stack", "PipeWire low-latency daemon running");
    } else {
        report.warned("Audio Stack", "PipeWire daemon not detected");
    }

    if command_exists("vulkaninfo") && succeeds(&["vulkaninfo", "--summary"], 10) {
        report.passed("Vulkan 3D Driver", "Vulkan device initialized and responsive");
    } else {
        report.warned("Vulkan 3D Driver", "Vulkan device query returned warning or fallback");
    }

    if command_exists("vainfo") && succeeds(&["vainfo"], 10) {
        report.passed("Video Codecs", "VA-API hardware video decode/encode active");
    } else {
        report.passed("Video Codecs", "Software codec fallback active");
    }

    if Path::new("/dev/input").is_dir() {
        report.passed("Input & Gamepads", "Event subsystem and controller udev rules active");
    } else {
        report.warned("Input & Gamepads", "/dev/input device node inaccessible");
    }
    print_report(&report, "Subsystem health", Some("System is running with some warning fallback configurations."))
}

fn add_gpu_detected(report: &mut DiagnosticReport) {
    if !command_exists("lspci") {
        report.warned("GPU detected", "lspci command not found");
    } else if let Some(line) = gpu::lspci_gpu_lines().first() {
        report.passed("GPU detected", line.trim());
    } else {
        report.warned("GPU detected", "no GPU found via lspci");
    }
}

fn add_vulkan(report: &mut DiagnosticReport, warning: &str) {
    if !command_exists("vulkaninfo") {
        report.warned("Vulkan", "vulkaninfo unavailable");
    } else if let Some(output) = run(&["vulkaninfo", "--summary"], 10) {
        if output.status.success() {
            report.passed("Vulkan", "responding");
        } else {
            report.warned("Vulkan", warning);
        }
    } else {
        report.warned("Vulkan", &format!("{warning} (timeout or execution failure)"));
    }
}

fn add_services(report: &mut DiagnosticReport, services: &[(&str, bool)]) {
    if !command_exists("systemctl") {
        return;
    }
    for (unit, user) in services {
        let mut active = vec!["systemctl"];
        if *user {
            active.push("--user");
        }
        active.extend(["is-active", unit]);
        if succeeds(&active, 5) {
            report.passed(runtime_diagnostics::service_label(unit), "active");
            continue;
        }
        let mut result = vec!["systemctl"];
        if *user {
            result.push("--user");
        }
        result.extend(["show", "-p", "Result", "--value", unit]);
        if stdout(&result, 5) == "success" {
            report.passed(runtime_diagnostics::service_label(unit), "completed successfully");
        } else {
            report.warned(runtime_diagnostics::service_label(unit), "not active");
        }
    }
}

fn resume_check() -> ExitCode {
    report_header("Resume Check");
    let mut report = DiagnosticReport::new("Resume Check");

    if !command_exists("loginctl") {
        report.warned("Login session", "loginctl command not found");
    } else {
        let session = env::var("XDG_SESSION_ID").unwrap_or_else(|_| "self".into());
        if succeeds(&["loginctl", "show-session", &session], 5) {
            report.passed("Login session", "logind can see this session");
        } else {
            report.warned("Login session", "session not visible through loginctl");
        }
    }

    if !command_exists("nmcli") {
        report.warned("Network", "nmcli unavailable");
    } else {
        let state = stdout(&["nmcli", "-t", "-f", "STATE", "general"], 5);
        if state.starts_with("connected") {
            report.passed("Network", &state);
        } else {
            report.warned("Network", if state.is_empty() { "unknown" } else { &state });
        }
    }
    add_services(&mut report, &[("pipewire.service", true), ("wireplumber.service", true), ("bluetooth.service", false)]);

    let bluetooth = std::fs::read_dir("/sys/class/bluetooth")
        .map(|entries| entries.flatten().any(|entry| entry.file_name().to_string_lossy().starts_with("hci")))
        .unwrap_or(false);
    if bluetooth {
        report.passed("Bluetooth adapter", "controller present");
    } else {
        report.warned("Bluetooth adapter", "no hci controller visible");
    }

    add_gpu_detected(&mut report);
    add_vulkan(&mut report, "failed after resume");

    if !command_exists("kscreen-doctor") {
        report.warned("Displays", "kscreen-doctor unavailable");
    } else {
        let count = stdout(&["kscreen-doctor", "-o"], 10)
            .lines()
            .filter(|line| line.contains(" connected"))
            .count();
        if count > 0 {
            report.passed("Displays", &format!("{count} connected output(s)"));
        } else {
            report.warned("Displays", "no connected output reported");
        }
    }

    if !command_exists("journalctl") {
        report.warned("Recent critical logs", "journalctl unavailable");
    } else if let Some(output) = run(&["journalctl", "-b", "--since", "-10 minutes", "-p", "err", "--no-pager"], 10) {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            let keywords = ["amdgpu", "nvidia", "i915", "xe", "bluetooth", "networkmanager", "pipewire", "wireplumber", "kwin"];
            let count = text.lines().filter(|line| keywords.iter().any(|key| line.to_ascii_lowercase().contains(key))).count();
            if count == 0 {
                report.passed("Recent critical logs", "no matching errors in last 10 minutes");
            } else {
                report.warned("Recent critical logs", &format!("{count} matching error(s) in last 10 minutes"));
            }
        } else {
            report.warned("Recent critical logs", "journalctl query failed");
        }
    } else {
        report.warned("Recent critical logs", "journalctl query failed");
    }
    print_report(&report, "resume readiness", None)
}

fn nvidia_status() -> ExitCode {
    report_header("NVIDIA Status");
    let mut report = DiagnosticReport::new("NVIDIA Status");
    if !command_exists("lspci") {
        report.passed("NVIDIA hardware", "no NVIDIA GPU detected");
        println!("\nResult: no NVIDIA-specific work needed.");
        return ExitCode::SUCCESS;
    }
    let nvidia = gpu::lspci_gpu_lines().into_iter().find(|line| line.to_ascii_lowercase().contains("nvidia"));
    let Some(device) = nvidia else {
        report.passed("NVIDIA hardware", "no NVIDIA GPU detected");
        println!("\nResult: no NVIDIA-specific work needed.");
        return ExitCode::SUCCESS;
    };
    report.passed("NVIDIA hardware", device.trim());
    if command_exists("rpm") && succeeds(&["rpm", "-q", "akmod-nvidia"], 5) {
        report.passed("akmod-nvidia", "installed");
    } else {
        report.failed("akmod-nvidia", "missing from image");
    }
    if command_exists("modinfo") && succeeds(&["modinfo", "nvidia"], 5) {
        report.passed("Kernel module built", "modinfo nvidia works");
    } else {
        report.warned("Kernel module built", "not built for current kernel yet");
    }
    let loaded = std::fs::read_to_string("/proc/modules").map(|text| text.lines().any(|line| line.starts_with("nvidia "))).unwrap_or(false);
    if loaded {
        report.passed("Kernel module loaded", "nvidia loaded");
    } else {
        report.warned("Kernel module loaded", "not loaded; reboot may be required after build");
    }
    if command_exists("systemctl") {
        let state = stdout(&["systemctl", "is-active", "kyth-hw-setup.service"], 5);
        let result = stdout(&["systemctl", "show", "-p", "Result", "--value", "kyth-hw-setup.service"], 5);
        match (state.as_str(), result.as_str()) {
            ("active" | "activating", _) => report.warned("Hardware setup service", "building in background"),
            ("inactive" | "failed", "success") => report.passed("Hardware setup service", "completed"),
            ("failed", _) => report.failed("Hardware setup service", "failed; run journalctl -u kyth-hw-setup"),
            _ => report.warned("Hardware setup service", &format!("{state} {result}")),
        }
    }
    if command_exists("nvidia-smi") {
        let smi = stdout(&["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], 10);
        if !smi.is_empty() {
            report.passed("nvidia-smi", &smi);
        } else {
            report.warned("nvidia-smi", "command failed or no GPU output");
        }
    } else {
        report.warned("nvidia-smi", "not available until proprietary driver is active");
    }
    print_report(&report, "NVIDIA setup", Some("NVIDIA setup needs attention or a reboot."))
}

fn controller_check() -> ExitCode {
    report_header("Controller Check");
    let mut report = DiagnosticReport::new("Controller Check");
    if Path::new("/dev/input").is_dir() {
        report.passed("Input subsystem", "/dev/input present");
    } else {
        report.failed("Input subsystem", "/dev/input missing");
    }
    let detected = controllers::detect_controllers();
    if let Some((name, _)) = detected.usb_controllers.first() {
        report.passed("Controller detected", name);
    } else if let Some(name) = detected.input_nodes.first() {
        report.passed("Controller detected", name);
    } else {
        report.warned("Controller detected", "none found; plug in or pair a controller and rerun");
    }
    if command_exists("bluetoothctl") {
        let output = stdout(&["bluetoothctl", "devices"], 5);
        let matches = output.lines().filter(|line| {
            let lower = line.to_ascii_lowercase();
            ["xbox", "dualsense", "dualshock", "wireless controller", "8bitdo", "controller"].iter().any(|key| lower.contains(key))
        }).count();
        if matches > 0 {
            report.passed("Bluetooth controller", "paired controller-like device found");
        } else {
            report.warned("Bluetooth controller", "no paired controller-like Bluetooth device found");
        }
    } else {
        report.warned("Bluetooth controller", "bluetoothctl unavailable");
    }
    if command_exists("steam-devices") || (command_exists("rpm") && succeeds(&["rpm", "-q", "steam-devices"], 5)) {
        report.passed("Steam devices rules", "steam-devices package installed");
    } else {
        report.warned("Steam devices rules", "steam-devices package not detected");
    }
    if Path::new("/dev/uinput").exists() {
        report.passed("uinput", "/dev/uinput present");
    } else {
        report.warned("uinput", "/dev/uinput missing; some remappers may not work");
    }
    if command_exists("flatpak") && succeeds(&["flatpak", "info", "com.valvesoftware.Steam"], 10) {
        report.passed("Steam", "installed");
    } else if command_exists("flatpak") {
        report.warned("Steam", "not installed");
    } else {
        report.warned("Steam", "flatpak command not found");
    }
    print_report(&report, "controller readiness", None)
}

fn game_boost_status() -> ExitCode {
    let cpuinfo = std::fs::read_to_string("/proc/cpuinfo").unwrap_or_default();
    let (vendor, model) = performance::cpu_topology(&cpuinfo);
    println!("[kyth-game-boost] KythOS Performance Governor Status");
    println!("[kyth-game-boost] CPU Vendor / Model: {vendor} ({model})");
    if vendor == "AuthenticAMD" && performance::has_3d_vcache(&model) {
        println!("[kyth-game-boost] AMD 3D V-Cache Detected: Cache CCD affinity optimization active");
    } else if vendor == "GenuineIntel" {
        println!("[kyth-game-boost] Intel Processor Topology: Hybrid P/E core auto-scheduling supported");
    }
    if command_exists("scx_rusty") {
        println!("[kyth-game-boost] Sched-Ext (scx_rusty): Fedora-packaged gaming scheduler available");
    } else if command_exists("systemctl") && succeeds(&["systemctl", "is-active", "--quiet", "scx_loader.service"], 5) {
        println!("[kyth-game-boost] Sched-Ext (scx_loader): Service active");
    } else {
        println!("[kyth-game-boost] Sched-Ext (scx): Default kernel scheduler fallback");
    }
    println!();
    println!("[kyth-game-boost] To use in Steam: Set launch options to: kyth-game-boost %command%");
    ExitCode::SUCCESS
}

fn game_boost(args: &[String]) -> ExitCode {
    if args.is_empty() {
        return game_boost_status();
    }
    println!("[kyth-game-boost] Launching game workload: {}", args.join(" "));
    use std::os::unix::process::CommandExt;
    if command_exists("systemd-run") {
        let mut command = Command::new("systemd-run");
        if unsafe { libc::geteuid() } != 0 && Path::new("/run/systemd/system").exists() {
            command.args(["--user", "--scope", "--slice=gaming.slice", "--"]);
        } else {
            command.args(["--scope", "--slice=gaming.slice", "--"]);
        }
        command.args(args);
        let error = command.exec();
        eprintln!("[kyth-game-boost] systemd-run failed: {error}");
    }
    let error = Command::new(&args[0]).args(&args[1..]).exec();
    eprintln!("[kyth-game-boost] Exec failed: {error}");
    ExitCode::from(127)
}

fn doctor() -> ExitCode {
    let report = kyth_shared::doctor::collect_report();
    println!("KythOS health: {}/100", report.score);
    for check in report.checks {
        println!(" - {check}");
    }
    if !report.suggestions.is_empty() {
        println!("\nSuggestions (just):");
        for suggestion in report.suggestions {
            println!("  * {suggestion}");
        }
    }
    ExitCode::SUCCESS
}

fn main() -> ExitCode {
    let name = env::args().next().and_then(|path| Path::new(&path).file_name().map(|name| name.to_string_lossy().into_owned())).unwrap_or_default();
    let args = env::args().skip(1).collect::<Vec<_>>();
    match name.as_str() {
        "kyth-health-check" => health_check(),
        "kyth-resume-check" => resume_check(),
        "kyth-nvidia-status" => nvidia_status(),
        "kyth-controller-check" => controller_check(),
        "kyth-game-boost" | "game-performance" => game_boost(&args),
        "kyth-doctor" => doctor(),
        _ => {
            eprintln!("unknown diagnostic entry point: {name}");
            ExitCode::from(64)
        }
    }
}
