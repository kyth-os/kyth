//! Native dispatcher for migrated tunable profiles.
//!
//! The registry still contains non-native entries whose bespoke Rust ports are
//! not complete. The native binary owns the migrated sysctl and module-specific
//! profiles while the compatibility dispatcher remains the fallback for the rest.

use kyth_shared::system::{
    ananicy,
    btrfs_autotune,
    btrfs_perf,
    bore,
    extended_preferences::{self, ThpConfig},
    net_latency,
    scheduler_arbiter,
    sysctl_profiles,
    tunable_registry,
    tuning_profile::Profile,
    zswap,
};
use std::env;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Duration;

fn invoked_name() -> String {
    env::args()
        .next()
        .and_then(|path| Path::new(&path).file_name().map(|name| name.to_string_lossy().into_owned()))
        .unwrap_or_default()
}

fn resolve_name(argv0: &str, args: &[String]) -> Result<(String, Vec<String>), String> {
    if argv0 == "kyth-tunable-rs" {
        let Some(name) = args.first() else {
            return Err("Usage: kyth-tunable-rs <tunable> [status|gaming|balanced|apply]".into());
        };
        return Ok((name.clone(), args[1..].to_vec()));
    }
    Ok((argv0.strip_prefix("kyth-").unwrap_or(argv0).to_string(), args.to_vec()))
}

fn test_mode() -> bool {
    env::var("KYTH_TEST_MODE").ok().as_deref() == Some("1")
        && env::var_os("XDG_CONFIG_HOME").is_some()
}

fn native_sysctl(name: &str) -> bool {
    let config = format!("{name}.toml");
    sysctl_profiles::known_profiles().any(|(candidate, _)| candidate == config)
}

fn native_bespoke(name: &str) -> bool {
    matches!(name, "bore" | "net-tune" | "thp-tune" | "zswap")
}

fn native_other(name: &str) -> bool {
    matches!(
        name,
        "ananicy"
            | "btrfs-autotune"
            | "btrfs-tune"
            | "epp-ac"
            | "gaming-cfs"
            | "pcie"
            | "pipewire-gaming"
            | "psi-gaming"
            | "mimalloc"
            | "mimalloc-run"
            | "sccache"
            | "shader-cache-size"
            | "wine-sync"
    )
}

fn native_implemented(name: &str) -> bool {
    native_sysctl(name) || native_bespoke(name) || native_other(name)
}

fn native_tunable_names() -> Vec<String> {
    tunable_registry::list_tunables(None::<&Path>)
        .into_iter()
        .filter(|spec| native_implemented(&spec.name))
        .map(|spec| spec.name)
        .collect()
}

fn run_sysctl_system() {
    if test_mode() {
        return;
    }
    let argv = ["sysctl".to_string(), "--system".to_string()];
    let _ = kyth_shared::system::process::run_bounded(&argv, Duration::from_secs(15));
}

fn ensure_root(name: &str, args: &[String]) -> Result<(), ExitCode> {
    if test_mode() {
        return Ok(());
    }
    if unsafe { libc::geteuid() } == 0 {
        return Ok(());
    }
    use std::os::unix::process::CommandExt;
    let mut command = std::process::Command::new("sudo");
    command.args(["-A", &format!("/usr/bin/kyth-{name}")]);
    command.args(args);
    let error = command.exec();
    eprintln!("kyth-{name}: cannot acquire root: {error}");
    Err(ExitCode::from(1))
}

fn generated_path(test_subdirectory: &str, filename: &str, production: &str) -> PathBuf {
    if test_mode() {
        if let Some(config) = env::var_os("XDG_CONFIG_HOME") {
            return PathBuf::from(config).join("kyth").join(test_subdirectory).join(filename);
        }
    }
    PathBuf::from(production)
}

fn dispatch_zswap(action: &str) -> ExitCode {
    let config_path = zswap::config_path(None::<&Path>);
    let sysctl_path = generated_path("sysctl.d", "99-kyth-zswap.conf", "/etc/sysctl.d/99-kyth-zswap.conf");
    let modprobe_path = generated_path("modprobe.d", "99-kyth-zswap.conf", "/etc/modprobe.d/99-kyth-zswap.conf");
    match action {
        "status" => {
            let config = zswap::load(&config_path);
            let active = zswap::status(&sysctl_path);
            println!("profile={} active={} kind=sysctl", config.profile, active);
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("zswap", &[action.to_string()]) {
                return code;
            }
            let mut config = zswap::load(&config_path);
            config.profile = if action == "gaming" { "kyth" } else { "balanced" }.into();
            if let Err(error) = zswap::save(&config_path, &config)
                .and_then(|_| zswap::generate(&config, &sysctl_path, &modprobe_path).map(|_| ()))
            {
                eprintln!("kyth-zswap: {error}");
                return ExitCode::from(1);
            }
            run_sysctl_system();
            println!("zswap {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("zswap", &[action.to_string()]) {
                return code;
            }
            let config = zswap::load(&config_path);
            if let Err(error) = zswap::generate(&config, &sysctl_path, &modprobe_path) {
                eprintln!("kyth-zswap: {error}");
                return ExitCode::from(1);
            }
            run_sysctl_system();
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-zswap [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_bore(action: &str) -> ExitCode {
    let config_path = bore::config_path(None::<&Path>);
    let drop_in = generated_path("sysctl.d", "99-kyth-bore.conf", "/etc/sysctl.d/99-kyth-bore.conf");
    match action {
        "status" => {
            let config = bore::load(&config_path);
            println!("profile={} active={} kind=sysctl", config.profile, bore::status(&drop_in));
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("bore", &[action.to_string()]) { return code; }
            let mut config = bore::load(&config_path);
            config.profile = if action == "gaming" { "gaming" } else { "balanced" }.into();
            let scx_active = !test_mode() && scheduler_arbiter::detect_scx_active();
            if let Err(error) = bore::save(&config_path, &config)
                .and_then(|_| bore::generate(&config, &drop_in, scx_active).map(|_| ()))
            {
                eprintln!("kyth-bore: {error}");
                return ExitCode::from(1);
            }
            run_sysctl_system();
            println!("bore {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("bore", &[action.to_string()]) { return code; }
            let config = bore::load(&config_path);
            let scx_active = !test_mode() && scheduler_arbiter::detect_scx_active();
            if let Err(error) = bore::generate(&config, &drop_in, scx_active) {
                eprintln!("kyth-bore: {error}");
                return ExitCode::from(1);
            }
            run_sysctl_system();
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-bore [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_net_tune(action: &str) -> ExitCode {
    let config_path = net_latency::config_path(None::<&Path>);
    let drop_in = generated_path("sysctl.d", "99-kyth-net-latency.conf", "/etc/sysctl.d/99-kyth-net-latency.conf");
    match action {
        "status" => {
            let config = net_latency::load(&config_path);
            println!("profile={} active={} kind=sysctl", if config.enabled { "gaming" } else { "balanced" }, net_latency::status(&drop_in));
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("net-tune", &[action.to_string()]) { return code; }
            let mut config = net_latency::load(&config_path);
            config.enabled = action == "gaming";
            if let Err(error) = net_latency::save(&config_path, &config)
                .and_then(|_| net_latency::generate(&config, &drop_in).map(|_| ()))
            {
                eprintln!("kyth-net-tune: {error}");
                return ExitCode::from(1);
            }
            run_sysctl_system();
            println!("net-tune {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("net-tune", &[action.to_string()]) { return code; }
            let config = net_latency::load(&config_path);
            if let Err(error) = net_latency::generate(&config, &drop_in) {
                eprintln!("kyth-net-tune: {error}");
                return ExitCode::from(1);
            }
            run_sysctl_system();
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-net-tune [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_ananicy(action: &str) -> ExitCode {
    let config_path = ananicy::config_path(None::<&Path>);
    let rule = generated_path("ananicy.d", "99-kyth-gaming.conf", "/etc/ananicy.d/99-kyth-gaming.conf");
    match action {
        "status" => {
            let config = ananicy::load(&config_path);
            println!("profile={} active={} kind=other", config.profile, ananicy::status(&rule));
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("ananicy", &[action.to_string()]) { return code; }
            let mut config = ananicy::load(&config_path);
            config.profile = if action == "gaming" { "kyth" } else { "balanced" }.into();
            if let Err(error) = ananicy::save(&config_path, &config)
                .and_then(|_| ananicy::generate(&config, &rule).map(|_| ()))
            {
                eprintln!("kyth-ananicy: {error}");
                return ExitCode::from(1);
            }
            println!("ananicy {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("ananicy", &[action.to_string()]) { return code; }
            let config = ananicy::load(&config_path);
            if let Err(error) = ananicy::generate(&config, &rule) {
                eprintln!("kyth-ananicy: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-ananicy [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_btrfs_autotune(action: &str) -> ExitCode {
    let config_path = btrfs_autotune::config_path(None::<&Path>);
    let script = generated_path("libexec", "kyth-btrfs-autotune", "/usr/libexec/kyth-btrfs-autotune");
    match action {
        "status" => {
            let config = btrfs_autotune::load(&config_path);
            println!("enabled={} active={} kind=other", config.enabled, btrfs_autotune::status(&script));
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("btrfs-autotune", &[action.to_string()]) { return code; }
            let mut config = btrfs_autotune::load(&config_path);
            config.enabled = action == "gaming";
            if let Err(error) = btrfs_autotune::save(&config_path, config)
                .and_then(|_| btrfs_autotune::generate(config, &script).map(|_| ()))
            {
                eprintln!("kyth-btrfs-autotune: {error}");
                return ExitCode::from(1);
            }
            println!("btrfs-autotune {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("btrfs-autotune", &[action.to_string()]) { return code; }
            let config = btrfs_autotune::load(&config_path);
            if let Err(error) = btrfs_autotune::generate(config, &script) {
                eprintln!("kyth-btrfs-autotune: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-btrfs-autotune [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_btrfs_tune(action: &str) -> ExitCode {
    let config_path = btrfs_perf::config_path(None::<&Path>);
    let root_dropin = generated_path(
        "systemd/root.mount.d",
        "99-kyth-btrfs.conf",
        btrfs_perf::DEFAULT_DROP_IN,
    );
    let generate_destination = test_mode().then_some(root_dropin.as_path());
    match action {
        "status" => {
            let config = btrfs_perf::load(&config_path);
            println!("profile={} active={} kind=other", config.profile, btrfs_perf::status(&root_dropin));
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("btrfs-tune", &[action.to_string()]) { return code; }
            let mut config = btrfs_perf::load(&config_path);
            config.profile = if action == "gaming" { "kyth" } else { "balanced" }.into();
            if let Err(error) = btrfs_perf::save(&config_path, &config)
                .and_then(|_| btrfs_perf::generate(&config, generate_destination).map(|_| ()))
            {
                eprintln!("kyth-btrfs-tune: {error}");
                return ExitCode::from(1);
            }
            println!("btrfs-tune {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("btrfs-tune", &[action.to_string()]) { return code; }
            let config = btrfs_perf::load(&config_path);
            if let Err(error) = btrfs_perf::generate(&config, generate_destination) {
                eprintln!("kyth-btrfs-tune: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-btrfs-tune [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn module_config_path(filename: &str, production: &str) -> PathBuf {
    if test_mode() {
        if let Some(config) = env::var_os("XDG_CONFIG_HOME") {
            return PathBuf::from(config).join("kyth").join(filename);
        }
    }
    PathBuf::from(production)
}

fn write_optional(path: &Path, content: Option<&str>) -> std::io::Result<()> {
    if let Some(content) = content {
        kyth_shared::atomic_io::atomic_write_text(path, content, Some(0o644))?;
    } else {
        match std::fs::remove_file(path) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
    }
    Ok(())
}

fn dispatch_mimalloc(action: &str) -> ExitCode {
    let config_path = module_config_path("mimalloc.toml", "/etc/kyth/mimalloc.toml");
    let environment = generated_path("environment.d", "99-kyth-mimalloc.conf", "/etc/environment.d/99-kyth-mimalloc.conf");
    match action {
        "status" => {
            let config = extended_preferences::load_mimalloc(&config_path);
            println!("enabled={} global={} per_game={} active={} kind=other", config.enabled, config.global, config.per_game, extended_preferences::mimalloc_status(&config, environment.is_file()));
            ExitCode::SUCCESS
        }
        "on" | "gaming" => {
            if let Err(code) = ensure_root("mimalloc", &[action.to_string()]) { return code; }
            let config = extended_preferences::MimallocConfig { enabled: true, global: false, per_game: true };
            if let Err(error) = extended_preferences::save_mimalloc(&config_path, &config)
                .and_then(|_| extended_preferences::generate_mimalloc_env(&config, &environment).map(|_| ()))
            {
                eprintln!("kyth-mimalloc: {error}");
                return ExitCode::from(1);
            }
            println!("mimalloc per-game enabled");
            ExitCode::SUCCESS
        }
        "off" | "balanced" => {
            if let Err(code) = ensure_root("mimalloc", &[action.to_string()]) { return code; }
            let config = extended_preferences::MimallocConfig { enabled: false, global: false, per_game: true };
            if let Err(error) = extended_preferences::save_mimalloc(&config_path, &config)
                .and_then(|_| extended_preferences::generate_mimalloc_env(&config, &environment).map(|_| ()))
            {
                eprintln!("kyth-mimalloc: {error}");
                return ExitCode::from(1);
            }
            println!("mimalloc disabled");
            ExitCode::SUCCESS
        }
        "global" => {
            if let Err(code) = ensure_root("mimalloc", &[action.to_string()]) { return code; }
            let config = extended_preferences::MimallocConfig { enabled: true, global: true, per_game: true };
            if let Err(error) = extended_preferences::save_mimalloc(&config_path, &config)
                .and_then(|_| extended_preferences::generate_mimalloc_env(&config, &environment).map(|_| ()))
            {
                eprintln!("kyth-mimalloc: {error}");
                return ExitCode::from(1);
            }
            println!("mimalloc global enabled");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("mimalloc", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_mimalloc(&config_path);
            if let Err(error) = extended_preferences::generate_mimalloc_env(&config, &environment) {
                eprintln!("kyth-mimalloc: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-mimalloc [status|on|off|global|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_mimalloc_run(args: &[String]) -> ExitCode {
    if matches!(args.first().map(String::as_str), Some("--help" | "-h")) {
        println!("Usage: kyth-mimalloc-run [--status] -- <command> [args...]");
        return ExitCode::SUCCESS;
    }
    if args.first().map(String::as_str) == Some("--status") {
        let config_path = module_config_path("mimalloc.toml", "/etc/kyth/mimalloc.toml");
        let environment = generated_path("environment.d", "99-kyth-mimalloc.conf", "/etc/environment.d/99-kyth-mimalloc.conf");
        let config = extended_preferences::load_mimalloc(&config_path);
        println!("enabled={} global={} per_game={} status={}", config.enabled, config.global, config.per_game, extended_preferences::mimalloc_status(&config, environment.is_file()));
        return ExitCode::SUCCESS;
    }
    let command_args = if args.first().map(String::as_str) == Some("--") { &args[1..] } else { args };
    let Some(program) = command_args.first() else {
        eprintln!("Usage: kyth-mimalloc-run [--status] -- <command> [args...]");
        return ExitCode::from(1);
    };
    let mut command = std::process::Command::new(program);
    command.args(&command_args[1..]);
    let library = extended_preferences::find_mimalloc_library();
    if Path::new(&library).is_file() {
        let preload = match env::var("LD_PRELOAD") {
            Ok(existing) if !existing.is_empty() => format!("{library}:{existing}"),
            _ => library,
        };
        command.env("LD_PRELOAD", preload).env("MIMALLOC_LARGE_OS_PAGES", "1");
    }
    match command.status() {
        Ok(status) => ExitCode::from(status.code().unwrap_or(1).try_into().unwrap_or(1)),
        Err(error) => {
            eprintln!("kyth-mimalloc-run: {error}");
            ExitCode::from(1)
        }
    }
}

fn dispatch_sccache(action: &str) -> ExitCode {
    let config_path = module_config_path("sccache.toml", "/etc/kyth/sccache.toml");
    let environment = generated_path("environment.d", "99-kyth-sccache.conf", "/etc/environment.d/99-kyth-sccache.conf");
    let service = generated_path("systemd", "sccache.service", "/etc/systemd/system/sccache.service");
    match action {
        "status" => {
            let config = extended_preferences::load_sccache(&config_path);
            println!("enabled={} size={} active={} kind=other", config.enabled, config.size, extended_preferences::sccache_status(&environment));
            ExitCode::SUCCESS
        }
        "on" | "gaming" => {
            if let Err(code) = ensure_root("sccache", &[action.to_string()]) { return code; }
            let config = extended_preferences::SccacheConfig { enabled: true, size: extended_preferences::load_sccache(&config_path).size };
            if let Err(error) = extended_preferences::save_sccache(&config_path, &config)
                .and_then(|_| extended_preferences::generate_sccache(&config, &environment, &service).map(|_| ()))
            {
                eprintln!("kyth-sccache: {error}");
                return ExitCode::from(1);
            }
            println!("sccache on");
            ExitCode::SUCCESS
        }
        "off" | "balanced" => {
            if let Err(code) = ensure_root("sccache", &[action.to_string()]) { return code; }
            let config = extended_preferences::SccacheConfig { enabled: false, size: extended_preferences::load_sccache(&config_path).size };
            if let Err(error) = extended_preferences::save_sccache(&config_path, &config)
                .and_then(|_| extended_preferences::generate_sccache(&config, &environment, &service).map(|_| ()))
            {
                eprintln!("kyth-sccache: {error}");
                return ExitCode::from(1);
            }
            println!("sccache off");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("sccache", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_sccache(&config_path);
            if let Err(error) = extended_preferences::generate_sccache(&config, &environment, &service) {
                eprintln!("kyth-sccache: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-sccache [status|on|off|apply]");
            ExitCode::from(1)
        }
    }
}

fn detect_vram_gb() -> u64 {
    let Ok(entries) = std::fs::read_dir("/sys/class/drm") else { return 8; };
    for entry in entries.flatten() {
        let path = entry.path().join("device/mem_info_vram_total");
        if let Ok(value) = std::fs::read_to_string(path) {
            if let Ok(bytes) = value.trim().parse::<u64>() {
                return bytes / 1024 / 1024 / 1024;
            }
        }
    }
    8
}

fn dispatch_shader_cache_size(action: &str) -> ExitCode {
    let config_path = module_config_path("shader-cache-size.toml", "/etc/kyth/shader-cache-size.toml");
    let environment = generated_path("environment.d", "99-kyth-shader-size.conf", "/etc/environment.d/99-kyth-shader-size.conf");
    match action {
        "status" => {
            let config = extended_preferences::load_shader_size(&config_path);
            let resolved = extended_preferences::resolve_shader_size(&config, detect_vram_gb());
            println!("mode={} size={} resolved={} active={} kind=other", config.mode, config.size, resolved, extended_preferences::shader_size_status(&environment));
            ExitCode::SUCCESS
        }
        "auto" | "gaming" | "balanced" => {
            if let Err(code) = ensure_root("shader-cache-size", &[action.to_string()]) { return code; }
            let config = extended_preferences::ShaderSizeConfig { mode: "auto".into(), size: extended_preferences::load_shader_size(&config_path).size };
            if let Err(error) = extended_preferences::save_shader_size(&config_path, &config)
                .and_then(|_| extended_preferences::generate_shader_size(&config, detect_vram_gb(), &environment).map(|_| ()))
            {
                eprintln!("kyth-shader-cache-size: {error}");
                return ExitCode::from(1);
            }
            println!("shader cache auto");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("shader-cache-size", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_shader_size(&config_path);
            if let Err(error) = extended_preferences::generate_shader_size(&config, detect_vram_gb(), &environment) {
                eprintln!("kyth-shader-cache-size: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-shader-cache-size [status|auto|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_wine_sync(action: &str) -> ExitCode {
    let config_path = module_config_path("wine-sync.toml", "/etc/kyth/wine-sync.toml");
    let environment = generated_path("environment.d", "99-kyth-wine-sync.conf", "/etc/environment.d/99-kyth-wine-sync.conf");
    match action {
        "status" => {
            let config = extended_preferences::load_wine_sync(&config_path);
            let (ntsync, futex2) = extended_preferences::probe_wine_sync();
            let active = std::fs::read_to_string(&environment).ok();
            println!("mode={} probe_ntsync={} probe_futex2={} env={} kind=other", config.mode, ntsync, futex2, extended_preferences::wine_sync_status(active.as_deref()));
            ExitCode::SUCCESS
        }
        "auto" | "ntsync" | "fsync" | "esync" | "off" => {
            if let Err(code) = ensure_root("wine-sync", &[action.to_string()]) { return code; }
            let config = extended_preferences::WineSyncConfig { mode: action.into() };
            if let Err(error) = extended_preferences::save_wine_sync(&config_path, &config)
                .and_then(|_| extended_preferences::generate_wine_env(&config, &environment).map(|_| ()))
            {
                eprintln!("kyth-wine-sync: {error}");
                return ExitCode::from(1);
            }
            println!("wine sync {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("wine-sync", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_wine_sync(&config_path);
            if let Err(error) = extended_preferences::generate_wine_env(&config, &environment) {
                eprintln!("kyth-wine-sync: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-wine-sync [status|auto|ntsync|fsync|esync|off|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_epp_ac(action: &str) -> ExitCode {
    let config_path = module_config_path("epp-ac.toml", "/etc/kyth/epp-ac.toml");
    let rule = generated_path("udev/rules.d", "61-kyth-epp-ac.rules", "/etc/udev/rules.d/61-kyth-epp-ac.rules");
    match action {
        "status" => {
            let config = extended_preferences::load_epp_ac(&config_path);
            println!("enabled={} active={} kind=other", config.enabled, if rule.is_file() { "enabled" } else { "off" });
            ExitCode::SUCCESS
        }
        "gaming" => {
            if let Err(code) = ensure_root("epp-ac", &[action.to_string()]) { return code; }
            let config = extended_preferences::EppAcConfig { enabled: true };
            if let Err(error) = extended_preferences::save_epp_ac(&config_path, &config)
                .and_then(|_| write_optional(&rule, extended_preferences::epp_ac_rule(&config)))
            {
                eprintln!("kyth-epp-ac: {error}");
                return ExitCode::from(1);
            }
            println!("epp-ac gaming");
            ExitCode::SUCCESS
        }
        "balanced" => {
            if let Err(code) = ensure_root("epp-ac", &[action.to_string()]) { return code; }
            let config = extended_preferences::EppAcConfig { enabled: false };
            if let Err(error) = extended_preferences::save_epp_ac(&config_path, &config)
                .and_then(|_| write_optional(&rule, None))
            {
                eprintln!("kyth-epp-ac: {error}");
                return ExitCode::from(1);
            }
            println!("epp-ac balanced");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("epp-ac", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_epp_ac(&config_path);
            if let Err(error) = write_optional(&rule, extended_preferences::epp_ac_rule(&config)) {
                eprintln!("kyth-epp-ac: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-epp-ac [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_gaming_cfs(action: &str) -> ExitCode {
    let config_path = module_config_path("gaming-cfs.toml", "/etc/kyth/gaming-cfs.toml");
    let dropin = generated_path("systemd/gaming.slice.d", "99-kyth-cfs.conf", "/etc/systemd/system/gaming.slice.d/99-kyth-cfs.conf");
    match action {
        "status" => {
            let config = extended_preferences::load_gaming_cfs(&config_path);
            println!("profile={} active={} kind=other", config.profile, if dropin.is_file() { "gaming" } else { "balanced" });
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("gaming-cfs", &[action.to_string()]) { return code; }
            let config = extended_preferences::GamingCfsConfig { profile: action.into() };
            if let Err(error) = extended_preferences::save_gaming_cfs(&config_path, &config)
                .and_then(|_| write_optional(&dropin, extended_preferences::gaming_cfs_dropin(&config)))
            {
                eprintln!("kyth-gaming-cfs: {error}");
                return ExitCode::from(1);
            }
            println!("gaming-cfs {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("gaming-cfs", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_gaming_cfs(&config_path);
            if let Err(error) = write_optional(&dropin, extended_preferences::gaming_cfs_dropin(&config)) {
                eprintln!("kyth-gaming-cfs: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-gaming-cfs [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_pcie(action: &str) -> ExitCode {
    let config_path = module_config_path("pcie.toml", "/etc/kyth/pcie.toml");
    let rule = generated_path("udev/rules.d", "61-kyth-pcie.rules", "/etc/udev/rules.d/61-kyth-pcie.rules");
    match action {
        "status" => {
            let config = extended_preferences::load_pcie(&config_path);
            println!("profile={} active={} kind=other", config.profile, if rule.is_file() { "gaming" } else { "balanced" });
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("pcie", &[action.to_string()]) { return code; }
            let config = extended_preferences::PcieConfig { profile: action.into() };
            if let Err(error) = extended_preferences::save_pcie(&config_path, &config)
                .and_then(|_| extended_preferences::generate_pcie(&config, &rule).map(|_| ()))
            {
                eprintln!("kyth-pcie: {error}");
                return ExitCode::from(1);
            }
            println!("pcie {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("pcie", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_pcie(&config_path);
            if let Err(error) = extended_preferences::generate_pcie(&config, &rule) {
                eprintln!("kyth-pcie: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-pcie [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_pipewire_gaming(action: &str) -> ExitCode {
    let config_path = module_config_path("pipewire-gaming.toml", "/etc/kyth/pipewire-gaming.toml");
    let destination = generated_path("wireplumber/main.lua.d", "99-kyth-gaming.lua", "/etc/wireplumber/main.lua.d/99-kyth-gaming.lua");
    match action {
        "status" => {
            let config = extended_preferences::load_pipewire_gaming(&config_path);
            println!("profile={} active={} kind=other", config.profile, if destination.is_file() { "gaming" } else { "balanced" });
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("pipewire-gaming", &[action.to_string()]) { return code; }
            let config = extended_preferences::PipewireGamingConfig { profile: action.into(), quantum: 128 };
            if let Err(error) = extended_preferences::save_pipewire_gaming(&config_path, &config)
                .and_then(|_| extended_preferences::generate_pipewire_gaming(&config, &destination).map(|_| ()))
            {
                eprintln!("kyth-pipewire-gaming: {error}");
                return ExitCode::from(1);
            }
            println!("pipewire-gaming {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("pipewire-gaming", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_pipewire_gaming(&config_path);
            if let Err(error) = extended_preferences::generate_pipewire_gaming(&config, &destination) {
                eprintln!("kyth-pipewire-gaming: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-pipewire-gaming [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_psi_gaming(action: &str) -> ExitCode {
    let config_path = module_config_path("psi.toml", "/etc/kyth/psi.toml");
    let dropin = generated_path("systemd/gaming.slice.d", "99-kyth-psi.conf", "/etc/systemd/system/gaming.slice.d/99-kyth-psi.conf");
    match action {
        "status" => {
            let config = extended_preferences::load_psi(&config_path);
            println!("profile={} active={} kind=other", config.profile, if dropin.is_file() { "gaming" } else { "balanced" });
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("psi-gaming", &[action.to_string()]) { return code; }
            let config = extended_preferences::PsiConfig { profile: action.into() };
            if let Err(error) = extended_preferences::save_psi(&config_path, &config)
                .and_then(|_| extended_preferences::generate_psi(&config, &dropin).map(|_| ()))
            {
                eprintln!("kyth-psi-gaming: {error}");
                return ExitCode::from(1);
            }
            println!("psi-gaming {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("psi-gaming", &[action.to_string()]) { return code; }
            let config = extended_preferences::load_psi(&config_path);
            if let Err(error) = extended_preferences::generate_psi(&config, &dropin) {
                eprintln!("kyth-psi-gaming: {error}");
                return ExitCode::from(1);
            }
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-psi-gaming [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn dispatch_thp_tune(action: &str) -> ExitCode {
    let config_path = if test_mode() {
        env::var_os("XDG_CONFIG_HOME")
            .map(|path| PathBuf::from(path).join("kyth/thp.toml"))
            .unwrap_or_else(|| PathBuf::from("/etc/kyth/thp.toml"))
    } else {
        PathBuf::from("/etc/kyth/thp.toml")
    };
    let drop_in = generated_path("sysctl.d", "99-kyth-thp.conf", "/etc/sysctl.d/99-kyth-thp.conf");
    match action {
        "status" => {
            let config = extended_preferences::load_thp(&config_path);
            let active = if drop_in.is_file() { "kyth" } else { "balanced" };
            println!("profile={} active={} kind=sysctl", config.profile, active);
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root("thp-tune", &[action.to_string()]) {
                return code;
            }
            let mut config = extended_preferences::load_thp(&config_path);
            config.profile = if action == "gaming" { "kyth" } else { "balanced" }.into();
            if let Err(error) = extended_preferences::save_thp(&config_path, &config)
                .and_then(|_| {
                    let content = extended_preferences::thp_dropin(&config);
                    match content {
                        Some(content) => kyth_shared::atomic_io::atomic_write_text(&drop_in, &content, Some(0o644)).map(|_| ()),
                        None => match std::fs::remove_file(&drop_in) {
                            Ok(()) => Ok(()),
                            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
                            Err(error) => Err(error),
                        },
                    }
                })
            {
                eprintln!("kyth-thp-tune: {error}");
                return ExitCode::from(1);
            }
            run_sysctl_system();
            println!("thp-tune {action}");
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root("thp-tune", &[action.to_string()]) {
                return code;
            }
            let config: ThpConfig = extended_preferences::load_thp(&config_path);
            let result = match extended_preferences::thp_dropin(&config) {
                Some(content) => kyth_shared::atomic_io::atomic_write_text(&drop_in, &content, Some(0o644)).map(|_| ()),
                None => match std::fs::remove_file(&drop_in) {
                    Ok(()) => Ok(()),
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
                    Err(error) => Err(error),
                },
            };
            if let Err(error) = result {
                eprintln!("kyth-thp-tune: {error}");
                return ExitCode::from(1);
            }
            run_sysctl_system();
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-thp-tune [status|gaming|balanced|apply]");
            ExitCode::from(1)
        }
    }
}

fn list() -> ExitCode {
    for spec in tunable_registry::list_tunables(None::<&Path>) {
        println!("{}", spec.name);
    }
    ExitCode::SUCCESS
}

fn list_native() -> ExitCode {
    for name in native_tunable_names() {
        println!("{name}");
    }
    ExitCode::SUCCESS
}

fn dispatch(name: &str, args: &[String]) -> ExitCode {
    let Some(spec) = tunable_registry::get_spec(name, None::<&Path>) else {
        eprintln!("Unknown tunable: {name} (try kyth-tunable --list)");
        return ExitCode::from(1);
    };
    let action = args.first().map(String::as_str).unwrap_or("status");
    if native_other(&spec.name) {
        return match spec.name.as_str() {
            "ananicy" => dispatch_ananicy(action),
            "btrfs-autotune" => dispatch_btrfs_autotune(action),
            "btrfs-tune" => dispatch_btrfs_tune(action),
            "epp-ac" => dispatch_epp_ac(action),
            "gaming-cfs" => dispatch_gaming_cfs(action),
            "pcie" => dispatch_pcie(action),
            "pipewire-gaming" => dispatch_pipewire_gaming(action),
            "psi-gaming" => dispatch_psi_gaming(action),
            "mimalloc" => dispatch_mimalloc(action),
            "mimalloc-run" => dispatch_mimalloc_run(args),
            "sccache" => dispatch_sccache(action),
            "shader-cache-size" => dispatch_shader_cache_size(action),
            "wine-sync" => dispatch_wine_sync(action),
            _ => ExitCode::from(2),
        };
    }
    if spec.kind != "sysctl" || !native_implemented(&spec.name) {
        eprintln!("kyth-{}: native Rust implementation is not ready; use the compatibility dispatcher", spec.name);
        return ExitCode::from(2);
    }
    if spec.name == "bore" {
        return dispatch_bore(action);
    }
    if spec.name == "net-tune" {
        return dispatch_net_tune(action);
    }
    if spec.name == "zswap" {
        return dispatch_zswap(action);
    }
    if spec.name == "thp-tune" {
        return dispatch_thp_tune(action);
    }
    let config = format!("{}.toml", spec.name);
    match action {
        "status" => {
            let profile = sysctl_profiles::load(&config, None);
            let active = sysctl_profiles::status(&config, None).as_str();
            println!("profile={} active={} kind={}", profile.as_str(), active, spec.kind);
            ExitCode::SUCCESS
        }
        "gaming" | "balanced" => {
            if let Err(code) = ensure_root(&spec.name, args) {
                return code;
            }
            let profile = if action == "gaming" { Profile::Gaming } else { Profile::Balanced };
            if let Err(error) = sysctl_profiles::save(&config, None, profile)
                .and_then(|_| sysctl_profiles::generate(&config, None, None, Some(profile)).map(|_| ()))
            {
                eprintln!("kyth-{}: {error}", spec.name);
                return ExitCode::from(1);
            }
            run_sysctl_system();
            println!("{} {action}", spec.name);
            ExitCode::SUCCESS
        }
        "apply" => {
            if let Err(code) = ensure_root(&spec.name, args) {
                return code;
            }
            if let Err(error) = sysctl_profiles::generate(&config, None, None, None) {
                eprintln!("kyth-{}: {error}", spec.name);
                return ExitCode::from(1);
            }
            run_sysctl_system();
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("Usage: kyth-{} [status|gaming|balanced|apply]", spec.name);
            ExitCode::from(1)
        }
    }
}

fn main() -> ExitCode {
    let args = env::args().skip(1).collect::<Vec<_>>();
    if args.first().map(String::as_str) == Some("--list") {
        return list();
    }
    if args.first().map(String::as_str) == Some("--list-native") {
        return list_native();
    }
    let argv0 = invoked_name();
    let Ok((name, action)) = resolve_name(&argv0, &args) else {
        eprintln!("Usage: kyth-tunable-rs <tunable> [status|gaming|balanced|apply]");
        return ExitCode::from(1);
    };
    dispatch(&name, &action)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_has_expected_complete_split() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../build_files/config/tunables.toml");
        let specs = kyth_shared::system::tunable_registry::list_tunables(Some(&path));
        assert_eq!(specs.len(), 94);
        assert_eq!(
            specs.iter().filter(|spec| spec.kind == "sysctl").count(),
            49
        );
        assert_eq!(specs.iter().filter(|spec| spec.kind == "other").count(), 45);
    }

    #[test]
    fn resolves_direct_and_compat_invocations() {
        assert_eq!(resolve_name("kyth-swappiness", &[]).unwrap().0, "swappiness");
        assert_eq!(resolve_name("kyth-tunable-rs", &["swappiness".into(), "status".into()]).unwrap(), ("swappiness".into(), vec!["status".into()]));
    }

    #[test]
    fn native_boundary_matches_the_rust_sysctl_registry() {
        assert!(native_sysctl("swappiness"));
        assert!(native_sysctl("tcp-fastopen"));
        assert!(!native_sysctl("gaming-master"));
    }

    #[test]
    fn native_list_is_exactly_the_implemented_sysctl_subset() {
        let names = native_tunable_names();
        assert_eq!(names.len(), 62);
        assert!(names.iter().any(|name| name == "swappiness"));
        assert!(names.iter().any(|name| name == "thp-collapse"));
        assert!(names.iter().any(|name| name == "thp-tune"));
        assert!(names.iter().any(|name| name == "zswap"));
        assert!(names.iter().any(|name| name == "bore"));
        assert!(names.iter().any(|name| name == "net-tune"));
        assert!(names.iter().any(|name| name == "ananicy"));
        assert!(names.iter().any(|name| name == "btrfs-autotune"));
        assert!(names.iter().any(|name| name == "btrfs-tune"));
        assert!(names.iter().any(|name| name == "epp-ac"));
        assert!(names.iter().any(|name| name == "gaming-cfs"));
        assert!(names.iter().any(|name| name == "pcie"));
        assert!(names.iter().any(|name| name == "pipewire-gaming"));
        assert!(names.iter().any(|name| name == "psi-gaming"));
        assert!(names.iter().any(|name| name == "mimalloc"));
        assert!(names.iter().any(|name| name == "mimalloc-run"));
        assert!(names.iter().any(|name| name == "sccache"));
        assert!(names.iter().any(|name| name == "shader-cache-size"));
        assert!(names.iter().any(|name| name == "wine-sync"));
        assert!(!names.iter().any(|name| name == "gaming-master"));
    }
}
