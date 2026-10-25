//! Port of `kyth_shared.system.probe`'s READ path — `kyth-probe.service`
//! The native probe service collects and writes the on-disk cache this reads;
//! the Hub itself only reads it. The collector preserves the compatibility
//! cache schema while keeping every child process bounded.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;

/// Holds an advisory `flock` on the cache lock file for the caller's scope.
/// Unlike a `create_new` marker file, the kernel releases this lock the
/// moment the holding file descriptor closes — including on SIGKILL/SIGABRT
/// — so a crashed writer can never leave the next run permanently unable to
/// acquire it.
struct ProbeCacheLock(std::fs::File);
impl Drop for ProbeCacheLock {
    fn drop(&mut self) {
        let _ = rustix::fs::flock(&self.0, rustix::fs::FlockOperation::NonBlockingUnlock);
    }
}

/// Cache contract shared with the legacy Python compatibility module — how
/// many seconds old a cached section may be before `read_section` refuses to
/// return it. The installed `kyth-probe.service` now uses this Rust module.
pub fn disk_ttl() -> HashMap<&'static str, f64> {
    HashMap::from([
        ("bootc-status-data", 90.0),
        ("bootc-status-text", 90.0),
        ("bootc-branch", 90.0),
        ("kernel-flavor", 600.0),
        ("flatpak-apps", 180.0),
        ("flatpak-updates", 180.0),
        ("nvidia-detect", 300.0),
        ("controllers-detect", 120.0),
        ("display-detect", 30.0),
        ("hardware-probes", 30.0),
        ("hardware-snapshot", 600.0),
        ("ntfs-drives", 30.0),
        ("secureboot-state", 300.0),
        ("hardware-summary", 30.0),
        ("network-summary", 60.0),
        ("audit-cache", 30.0),
        ("firmware-cache", 300.0),
    ])
}

/// How often the user timer refreshes (`kyth-probe-user.timer`): 10 minutes.
/// The user run reads fresh-enough system-cache sections instead of
/// re-collecting them (see `fresh_system_sections`), so a short interval
/// would only duplicate the system service's work every boot.
pub const USER_REFRESH_INTERVAL_SECS: u64 = 600;

/// Sections that need the network: skipped (never collected as null) when
/// there is no default route, so offline runs keep the last good values
/// instead of blanking them.
pub const NETWORKED_SECTIONS: &[&str] = &["flatpak-updates", "network-summary"];

/// True when the machine has a default route (v4 or v6): `/proc/net/route`
/// carries a `00000000` destination, or `/proc/net/ipv6_route` a zero prefix
/// with a non-loopback next hop. Pure over the two proc files so tests can
/// inject fixtures; [`has_default_route`] reads the live files.
///
/// Only the v4 file has a header line to skip: `/proc/net/ipv6_route` is
/// headerless, so skipping its first line would never examine the first
/// v6 route entry (which can be the default route itself).
pub fn has_default_route_in(route_v4: &str, route_v6: &str) -> bool {
    for line in route_v4.lines().skip(1) {
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.get(1) == Some(&"00000000") {
            return true;
        }
    }
    for line in route_v6.lines() {
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() >= 5
            && fields[0].chars().all(|char| char == '0')
            && fields[4] != "00000000000000000000000000000000"
        {
            return true;
        }
    }
    false
}

/// Live default-route check for collectors and the Hub.
pub fn has_default_route() -> bool {
    let v4 = std::fs::read_to_string("/proc/net/route").unwrap_or_default();
    let v6 = std::fs::read_to_string("/proc/net/ipv6_route").unwrap_or_default();
    has_default_route_in(&v4, &v6)
}

/// Sections the boot-time system probe (`kyth-probe --system`) defers: the
/// network-backed collectors stay off the boot-critical path (P1). The user
/// timer refreshes them within 10 minutes of login, and readers fall back
/// to a live query for a missing section.
pub fn deferred_system_sections() -> &'static [&'static str] {
    &["flatpak-updates"]
}

/// Fresh-enough system-cache sections for the user timer: the user run merges
/// these into its own cache instead of re-collecting expensive/system-owned
/// data (bootc status, flatpak listings, hardware). TTL-honored — stale or
/// missing sections are simply absent so the user run collects them itself.
pub fn fresh_system_sections() -> serde_json::Map<String, Value> {
    fresh_system_sections_in(&system_cache_path())
}

fn fresh_system_sections_in(system_path: &Path) -> serde_json::Map<String, Value> {
    let mut fresh = serde_json::Map::new();
    let Some(doc) = load_cache_file(system_path) else {
        return fresh;
    };
    let Some(sections) = doc.get("sections").and_then(Value::as_object) else {
        return fresh;
    };
    let now = now_unix();
    for (key, entry) in sections {
        let ttl = disk_ttl().get(key.as_str()).copied().unwrap_or(0.0);
        let ts = entry.get("ts").and_then(Value::as_f64).unwrap_or(-1.0);
        let age = now - ts;
        if age < 0.0 || age > ttl {
            continue;
        }
        if let Some(data) = entry.get("data").filter(|value| !value.is_null()) {
            fresh.insert(key.clone(), data.clone());
        }
    }
    fresh
}

/// Read one section from the SYSTEM cache only, honoring its TTL. What the
/// user timer and the Hub prefer before falling back to a live collection.
pub fn read_system_section(key: &str) -> Option<Value> {
    read_section_in(key, &[system_cache_path()])
}

fn user_runtime_cache_path() -> PathBuf {
    if let Ok(runtime) = std::env::var("XDG_RUNTIME_DIR") {
        return PathBuf::from(runtime).join("kyth").join("probe-cache.json");
    }
    let uid = rustix::process::getuid().as_raw();
    PathBuf::from(format!("/run/user/{uid}"))
        .join("kyth")
        .join("probe-cache.json")
}

fn user_home_cache_path() -> PathBuf {
    if let Ok(xdg) = std::env::var("XDG_CACHE_HOME") {
        return PathBuf::from(xdg).join("kyth").join("probe-cache.json");
    }
    let home = std::env::var("HOME").unwrap_or_default();
    PathBuf::from(home)
        .join(".cache")
        .join("kyth")
        .join("probe-cache.json")
}

fn system_cache_path() -> PathBuf {
    PathBuf::from("/var/cache/kyth/probe-cache.json")
}

/// Select the cache destination for the native probe service.  The system
/// service passes `system=true`; the user service keeps its cache under the
/// session runtime directory and falls back to the user's cache directory.
pub fn default_write_path(system: bool) -> PathBuf {
    if system || rustix::process::getuid().is_root() {
        return system_cache_path();
    }
    let runtime = user_runtime_cache_path();
    if runtime
        .parent()
        .map(|parent| std::fs::create_dir_all(parent).is_ok())
        .unwrap_or(false)
    {
        runtime
    } else {
        user_home_cache_path()
    }
}

/// File mode the cache at `path` must carry once written, or `None` to
/// leave the process-default mode. The SYSTEM cache is the exception: the
/// root `kyth-probe.service` runs under `UMask=0077`, so a plain
/// `File::create` lands mode 0600 root — and the user-session readers the
/// system cache exists for (the Hub, the user timer's
/// [`fresh_system_sections`]) then get EACCES, which `load_cache_file`
/// treats exactly like a missing file. The system cache therefore gets an
/// explicit 0644 (its contents are world-readable probe data by design).
/// User caches keep the default (0600 under the user unit's umask).
fn cache_file_mode(path: &Path) -> Option<u32> {
    if path == system_cache_path() {
        Some(0o644)
    } else {
        None
    }
}

/// Atomically replace a cache document.  Cache readers can therefore never
/// observe a partially serialized probe result, even when a service timeout
/// overlaps a Hub refresh.
pub fn write_cache_file(path: &Path, document: &Value) -> std::io::Result<()> {
    write_cache_file_with_mode(path, document, cache_file_mode(path))
}

fn write_cache_file_with_mode(
    path: &Path,
    document: &Value,
    mode: Option<u32>,
) -> std::io::Result<()> {
    let parent = path.parent().ok_or_else(|| {
        std::io::Error::new(std::io::ErrorKind::InvalidInput, "cache path has no parent")
    })?;
    if !document.is_object()
        || document
            .get("sections")
            .and_then(Value::as_object)
            .is_none()
    {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "probe cache document must contain an object sections field",
        ));
    }
    std::fs::create_dir_all(parent)?;
    let lock = path.with_extension(format!(
        "{}.lock",
        path.extension()
            .and_then(|extension| extension.to_str())
            .unwrap_or("cache")
    ));
    let lock_file = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .open(&lock)?;
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
    loop {
        match rustix::fs::flock(
            &lock_file,
            rustix::fs::FlockOperation::NonBlockingLockExclusive,
        ) {
            Ok(()) => break,
            Err(rustix::io::Errno::WOULDBLOCK) if std::time::Instant::now() < deadline => {
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            Err(error) => return Err(error.into()),
        }
    }
    let _guard = ProbeCacheLock(lock_file);
    let tmp = parent.join(format!(
        ".probe-{}-{}.json",
        std::process::id(),
        now_unix() as u128
    ));
    let payload = serde_json::to_vec(document)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))?;
    let result = (|| {
        let mut file = std::fs::File::create(&tmp)?;
        use std::io::Write;
        file.write_all(&payload)?;
        file.sync_all()?;
        if let Some(mode) = mode {
            // Set the mode on the temp file so the rename publishes the
            // cache with its final permissions atomically — readers never
            // observe the restrictive umask default first.
            use std::os::unix::fs::PermissionsExt;
            file.set_permissions(std::fs::Permissions::from_mode(mode))?;
        }
        std::fs::rename(&tmp, path)?;
        Ok::<(), std::io::Error>(())
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&tmp);
    }
    result
}

/// Merge freshly collected sections into the shared cache document.
pub fn update_sections(
    sections: &serde_json::Map<String, Value>,
    path: Option<&Path>,
    system: bool,
) -> std::io::Result<PathBuf> {
    let target = path
        .map(Path::to_path_buf)
        .unwrap_or_else(|| default_write_path(system));
    let mut document = load_cache_file(&target)
        .unwrap_or_else(|| serde_json::json!({"version": 2, "generated_at": 0.0, "sections": {}}));
    let object = document.as_object_mut().ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "probe cache is not an object",
        )
    })?;
    let cache_sections = object
        .entry("sections")
        .or_insert_with(|| Value::Object(serde_json::Map::new()))
        .as_object_mut()
        .ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "probe sections are not an object",
            )
        })?;
    let now = now_unix();
    for (key, data) in sections {
        cache_sections.insert(key.clone(), serde_json::json!({"ts": now, "data": data}));
    }
    object.insert("version".into(), Value::from(2));
    object.insert("generated_at".into(), Value::from(now));
    write_cache_file(&target, &Value::Object(object.clone()))?;
    Ok(target)
}

fn command_output(program: &str, args: &[&str], timeout_secs: u64) -> Option<String> {
    let mut argv = vec![program.to_string()];
    argv.extend(args.iter().map(|arg| (*arg).to_string()));
    let output =
        crate::system::process::run_bounded(&argv, std::time::Duration::from_secs(timeout_secs))
            .ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).to_string())
}

fn collect_flatpak_apps() -> Value {
    let Some(output) = command_output("flatpak", &["list", "--app", "--columns=application"], 15)
    else {
        return Value::Null;
    };
    let mut apps = output
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    apps.sort();
    apps.dedup();
    Value::Array(apps.into_iter().map(Value::String).collect())
}

fn flatpak_updates_for_scope(scope: &'static str) -> Option<i64> {
    // `--app` mirrors update_availability::remote_ls_updates_argv: without
    // it, remote-ls also lists updatable runtimes, inflating the app count.
    command_output(
        "flatpak",
        &[
            "remote-ls",
            "--updates",
            "--app",
            scope,
            "--columns=application",
        ],
        30,
    )
    .map(|output| {
        output
            .lines()
            .filter(|line| !line.trim().is_empty())
            .count() as i64
    })
}

fn collect_flatpak_updates() -> Value {
    // P1/P9: the two network-backed scope queries run concurrently instead
    // of sequentially (30s timeout each); the boot-time system probe skips
    // this section entirely (see probe_bin --system).
    let (system, user) = std::thread::scope(|scope| {
        let system_handle = scope.spawn(|| flatpak_updates_for_scope("--system"));
        let user_handle = scope.spawn(|| flatpak_updates_for_scope("--user"));
        (
            system_handle.join().unwrap_or(None),
            user_handle.join().unwrap_or(None),
        )
    });
    // The section value is a bare count and cannot express "one scope
    // failed": folding a failed scope in as 0 would silently under-report.
    // A partial read is therefore a miss (Null), exactly like both failing.
    match (system, user) {
        (Some(system_count), Some(user_count)) => Value::from(system_count + user_count),
        _ => Value::Null,
    }
}

fn collect_hardware() -> Option<(Value, Value)> {
    let evaluation = crate::system::hardware_policy::evaluate_system().ok()?;
    let has_nvidia = evaluation
        .inventory
        .pci
        .iter()
        .any(|device| device.vendor == "10de" && device.class_code.starts_with("03"));
    let is_hybrid = evaluation
        .capabilities
        .iter()
        .any(|capability| capability == "gpu.hybrid" || capability == "gpu.offload");
    let capabilities = evaluation
        .capabilities
        .iter()
        .take(8)
        .cloned()
        .collect::<Vec<_>>();
    let profiles = evaluation
        .profiles
        .iter()
        .filter_map(|profile| profile.get("id").and_then(Value::as_str))
        .take(3)
        .map(str::to_string)
        .collect::<Vec<_>>();
    let summary = serde_json::json!({
        "has_nvidia": has_nvidia,
        "is_hybrid": is_hybrid,
        "capabilities": capabilities,
        "profiles": profiles,
    });
    Some((Value::Bool(has_nvidia), summary))
}

/// Collect the sections formerly emitted by `kyth_shared.system.probe`.
/// Every operation is bounded and failure is represented as JSON `null`, so a
/// missing optional utility cannot prevent the rest of the cache from being
/// refreshed.
pub fn collect_snapshot() -> serde_json::Map<String, Value> {
    collect_snapshot_skipping(&[])
}

/// [`collect_snapshot`], skipping `skip`: the user timer passes the keys it
/// already has fresh from the system cache so expensive sections (bootc,
/// flatpak, hardware) are not collected twice per cycle.
///
/// Independent sections are collected on worker threads (`std::thread::scope`
/// borrows the caller's stack, so no `'static` bounds leak into the
/// collectors): the cycle's wall time is the slowest section, not the sum.
/// A panicking section only drops its own keys — consistent with the
/// collector's "failure is JSON null" contract.
pub fn collect_snapshot_skipping(skip: &[&str]) -> serde_json::Map<String, Value> {
    collect_snapshot_streaming(skip, &mut |_| {})
}

/// [`collect_snapshot_skipping`], invoking `on_sections` with each worker
/// group's sections the moment that group completes (before the remaining
/// groups finish). The probe binary persists each batch via
/// [`update_sections`] as it arrives: collection is otherwise all-or-nothing
/// under the service's 120 s `TimeoutStartSec`, so a slow machine whose run
/// is killed mid-cycle would leave its cache unrefreshed forever — with
/// streaming persistence, the sections that did complete are durable, and
/// only the unfinished groups stay stale for the next cycle.
pub fn collect_snapshot_streaming(
    skip: &[&str],
    on_sections: &mut dyn FnMut(&serde_json::Map<String, Value>),
) -> serde_json::Map<String, Value> {
    let skipped = |key: &str| skip.contains(&key);
    // One active-operation (`ps`) scan shared by both bootc fetches, and one
    // default-route check shared by the networked sections (P2).
    let bootc_needed = !["bootc-status-data", "bootc-status-text", "bootc-branch"]
        .iter()
        .all(|key| skipped(key));
    let active = bootc_needed && crate::system::bootc_query::active_operation().is_some();
    let online = !(skipped("flatpak-updates") && skipped("network-summary")) && has_default_route();

    let mut sections = serde_json::Map::new();
    std::thread::scope(|scope| {
        let mut handles = Vec::new();

        if bootc_needed {
            handles.push(scope.spawn(|| {
                let mut out: Vec<(String, Value)> = Vec::new();
                let status_data = crate::system::bootc_query::fetch_status_data_with_active(active);
                // P2: the text form is only a fallback for bootc versions
                // whose JSON cannot resolve the image reference — the common
                // case runs one `bootc status`, not two.
                let reference = status_data
                    .as_ref()
                    .and_then(crate::system::bootc_query::image_reference_from_status);
                let status_text = if status_data.is_none() || reference.is_none() {
                    crate::system::bootc_query::fetch_status_text_with_active(active)
                } else {
                    String::new()
                };
                let reference = reference.or_else(|| {
                    crate::system::bootc_query::image_reference_from_status_with_output(
                        &status_data.clone().unwrap_or(Value::Null),
                        &status_text,
                    )
                });
                if !skipped("bootc-status-data") {
                    out.push((
                        "bootc-status-data".into(),
                        status_data.unwrap_or(Value::Null),
                    ));
                }
                if !skipped("bootc-status-text") && !status_text.is_empty() {
                    out.push(("bootc-status-text".into(), Value::String(status_text)));
                }
                if !skipped("bootc-branch") {
                    out.push((
                        "bootc-branch".into(),
                        crate::system::bootc_policy::branch_from_ref(reference.as_deref())
                            .map(Value::String)
                            .unwrap_or(Value::Null),
                    ));
                }
                out
            }));
        }

        if !skipped("kernel-flavor") {
            handles.push(scope.spawn(|| {
                vec![(
                    "kernel-flavor".to_string(),
                    Value::String(crate::system::bootc::current_kernel_flavor()),
                )]
            }));
        }

        if !skipped("flatpak-apps") {
            handles
                .push(scope.spawn(|| vec![("flatpak-apps".to_string(), collect_flatpak_apps())]));
        }

        if online {
            handles.push(scope.spawn(|| {
                let mut out: Vec<(String, Value)> = Vec::new();
                if !skipped("flatpak-updates") {
                    out.push(("flatpak-updates".to_string(), collect_flatpak_updates()));
                }
                if !skipped("network-summary") {
                    out.push((
                        "network-summary".to_string(),
                        serde_json::to_value(
                            crate::system::network_identity::get_network_identity(),
                        )
                        .unwrap_or(Value::Null),
                    ));
                }
                out
            }));
        }

        if !["nvidia-detect", "hardware-summary", "display-detect"]
            .iter()
            .all(|key| skipped(key))
        {
            handles.push(scope.spawn(|| {
                let mut out: Vec<(String, Value)> = Vec::new();
                if let Some((nvidia, hardware)) = collect_hardware() {
                    if !skipped("nvidia-detect") {
                        out.push(("nvidia-detect".to_string(), nvidia));
                    }
                    if !skipped("hardware-summary") {
                        out.push(("hardware-summary".to_string(), hardware.clone()));
                    }
                    if !skipped("display-detect") {
                        out.push(("display-detect".to_string(), hardware));
                    }
                } else {
                    for key in ["nvidia-detect", "hardware-summary", "display-detect"] {
                        if !skipped(key) {
                            out.push((key.to_string(), Value::Null));
                        }
                    }
                }
                out
            }));
        }

        if !skipped("controllers-detect") {
            handles.push(scope.spawn(|| {
                vec![(
                    "controllers-detect".to_string(),
                    serde_json::to_value(crate::system::controllers::detect_controllers())
                        .unwrap_or(Value::Null),
                )]
            }));
        }

        if !skipped("hardware-snapshot") {
            handles.push(scope.spawn(|| {
                vec![(
                    "hardware-snapshot".to_string(),
                    serde_json::to_value(crate::system::gpu::hardware_snapshot_section())
                        .unwrap_or(Value::Null),
                )]
            }));
        }

        for handle in handles {
            let completed = handle.join().unwrap_or_default();
            if completed.is_empty() {
                continue;
            }
            let mut batch = serde_json::Map::new();
            for (key, value) in completed {
                batch.insert(key.clone(), value.clone());
                sections.insert(key, value);
            }
            on_sections(&batch);
        }
    });
    sections
}

const CACHEABLE_SECTIONS: &[&str] = &[
    "bootc-status-data",
    "bootc-status-text",
    "bootc-branch",
    "kernel-flavor",
    "flatpak-apps",
    "flatpak-updates",
    "nvidia-detect",
    "controllers-detect",
    "display-detect",
    "hardware-snapshot",
    "hardware-summary",
    "network-summary",
];

pub fn cacheable_sections_to_skip<'a>(keys: &[&'a str]) -> Vec<&'a str> {
    keys.iter()
        .copied()
        .filter(|key| CACHEABLE_SECTIONS.contains(key))
        .collect()
}

pub fn merge_fresh_sections(
    sections: &mut serde_json::Map<String, Value>,
    fresh: serde_json::Map<String, Value>,
) {
    sections.extend(fresh);
}

/// Same precedence as the compatibility module's `cache_read_paths` for a
/// logged-in desktop user. The system service writes the shared system path;
/// readers always accept it as the final fallback.
pub fn cache_read_paths() -> Vec<PathBuf> {
    vec![
        user_runtime_cache_path(),
        user_home_cache_path(),
        system_cache_path(),
    ]
}

fn load_cache_file(path: &Path) -> Option<Value> {
    let raw = std::fs::read_to_string(path).ok()?;
    let data: Value = serde_json::from_str(&raw).ok()?;
    if !data.is_object() {
        return None;
    }
    data.get("sections")?.as_object()?;
    Some(data)
}

fn now_unix() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// Port of `probe.py`'s `read_section(key, max_age=None, paths=None)` —
/// reads whatever `kyth-probe.service` (or a prior Hub session) already
/// cached for `key`, picking the freshest entry within its TTL across the
/// candidate paths. `paths` overrides `cache_read_paths()`, same as the
/// Python original's optional param — tests use this instead of mutating
/// process-global env vars.
pub fn read_section_in(key: &str, paths: &[PathBuf]) -> Option<Value> {
    let ttl = *disk_ttl().get(key)?;
    let now = now_unix();
    let mut best: Option<(f64, Value)> = None;
    for path in paths {
        let Some(doc) = load_cache_file(path) else {
            continue;
        };
        let Some(entry) = doc.get("sections").and_then(|s| s.get(key)) else {
            continue;
        };
        let Some(entry_obj) = entry.as_object() else {
            continue;
        };
        let Some(ts) = entry_obj.get("ts").and_then(Value::as_f64) else {
            continue;
        };
        // A cached `null` means the collector had nothing to report (e.g. a
        // failed `bootc status --json`), not a real value — callers such as
        // `check_update_status()` chain `.or_else(fetch_status_data)` on this
        // result to retry live, and a `Some(Value::Null)` here would defeat
        // that fallback for the section's entire TTL window.
        let Some(data) = entry_obj.get("data").filter(|value| !value.is_null()) else {
            continue;
        };
        let age = now - ts;
        if age < 0.0 || age > ttl {
            continue;
        }
        if best
            .as_ref()
            .map(|(best_ts, _)| ts > *best_ts)
            .unwrap_or(true)
        {
            best = Some((ts, data.clone()));
        }
    }
    best.map(|(_, data)| data)
}

/// `read_section_in` against the real `cache_read_paths()` — what every
/// non-test caller wants.
pub fn read_section(key: &str) -> Option<Value> {
    read_section_in(key, &cache_read_paths())
}

/// Return a cache document with selected sections removed.
///
/// This is the pure transformation used by hotplug and post-mutation
/// invalidation. The caller owns serialization, locking, and persistence.
/// With `keys == None`, only known disk-backed sections are removed; unrelated
/// metadata is preserved just like the Python probe service.
pub fn invalidate_sections(
    document: &Value,
    keys: Option<&[&str]>,
    updated_at: f64,
) -> Option<Value> {
    let mut document = document.as_object()?.clone();
    let sections = document.get_mut("sections")?.as_object_mut()?;
    let remove_all = keys.is_none();
    let requested = keys.map(|keys| {
        keys.iter()
            .copied()
            .collect::<std::collections::HashSet<_>>()
    });
    let before = sections.len();
    sections.retain(|key, _| {
        if remove_all {
            !disk_ttl().contains_key(key.as_str())
        } else {
            !requested
                .as_ref()
                .is_some_and(|keys| keys.contains(key.as_str()))
        }
    });
    if sections.len() == before {
        return None;
    }
    document.insert("generated_at".into(), Value::from(updated_at));
    Some(Value::Object(document))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::fs;

    #[test]
    fn a_fully_fresh_cache_skips_all_expensive_snapshot_sections() {
        let sections = collect_snapshot_skipping(CACHEABLE_SECTIONS);
        assert!(sections.is_empty());
    }

    #[test]
    fn deferred_system_sections_are_all_skippable_cache_keys() {
        // P1: every deferred section must be a known cacheable key, or the
        // boot probe could not actually skip it.
        for section in deferred_system_sections() {
            assert!(
                CACHEABLE_SECTIONS.contains(section),
                "{section} is deferred but not a cacheable section"
            );
        }
        assert!(deferred_system_sections().contains(&"flatpak-updates"));
    }

    #[test]
    fn skipped_sections_never_appear_in_the_parallel_snapshot() {
        // Exercises the threaded collector: skipped keys must be absent even
        // when every other section is collected live.
        let sections = collect_snapshot_skipping(deferred_system_sections());
        assert!(!sections.contains_key("flatpak-updates"));
    }

    #[test]
    fn fresh_system_cache_values_override_collected_values() {
        let mut collected = serde_json::Map::new();
        collected.insert("bootc-branch".into(), json!("collected"));
        collected.insert("controllers-detect".into(), json!(["live"]));
        let fresh = serde_json::Map::from_iter([("bootc-branch".into(), json!("system-cache"))]);

        merge_fresh_sections(&mut collected, fresh);

        assert_eq!(collected["bootc-branch"], "system-cache");
        assert_eq!(collected["controllers-detect"], json!(["live"]));
    }

    #[test]
    fn only_fresh_cacheable_keys_are_selected_for_skipping() {
        let requested = ["bootc-branch", "controllers-detect", "custom"];
        assert_eq!(
            cacheable_sections_to_skip(&requested),
            vec!["bootc-branch", "controllers-detect"]
        );
    }

    #[test]
    fn missing_cache_returns_none() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        assert_eq!(read_section_in("bootc-branch", &[path]), None);
    }

    #[test]
    fn unknown_key_returns_none() {
        assert_eq!(read_section_in("not-a-real-key", &[]), None);
    }

    #[test]
    fn reads_a_fresh_cache_entry() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let now = now_unix();
        let doc = json!({
            "version": 2, "generated_at": now,
            "sections": { "bootc-branch": { "ts": now, "data": "testing" } },
        });
        fs::write(&path, serde_json::to_string(&doc).unwrap()).unwrap();
        assert_eq!(
            read_section_in("bootc-branch", &[path]),
            Some(json!("testing"))
        );
    }

    #[test]
    fn a_cached_null_is_treated_as_a_miss_so_callers_can_fall_back_to_a_live_query() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let now = now_unix();
        let doc = json!({
            "version": 2, "generated_at": now,
            "sections": { "bootc-status-data": { "ts": now, "data": null } },
        });
        fs::write(&path, serde_json::to_string(&doc).unwrap()).unwrap();
        assert_eq!(read_section_in("bootc-status-data", &[path]), None);
    }

    #[test]
    fn stale_entry_past_its_ttl_is_ignored() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        // bootc-branch's TTL is 90s.
        let old = now_unix() - 200.0;
        let doc = json!({
            "version": 2, "generated_at": old,
            "sections": { "bootc-branch": { "ts": old, "data": "testing" } },
        });
        fs::write(&path, serde_json::to_string(&doc).unwrap()).unwrap();
        assert_eq!(read_section_in("bootc-branch", &[path]), None);
    }

    #[test]
    fn picks_the_freshest_entry_across_candidate_paths() {
        let dir = tempfile::tempdir().unwrap();
        let now = now_unix();
        let older_path = dir.path().join("older.json");
        let newer_path = dir.path().join("newer.json");
        fs::write(
            &older_path,
            serde_json::to_string(&json!({
                "version": 2, "sections": { "bootc-branch": { "ts": now - 50.0, "data": "stale-value" } },
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(
            &newer_path,
            serde_json::to_string(&json!({
                "version": 2, "sections": { "bootc-branch": { "ts": now, "data": "fresh-value" } },
            }))
            .unwrap(),
        )
        .unwrap();
        // Deliberately listed newest-last, to prove this picks the freshest
        // entry rather than the first match.
        assert_eq!(
            read_section_in("bootc-branch", &[older_path, newer_path]),
            Some(json!("fresh-value"))
        );
    }

    #[test]
    fn invalidates_selected_sections_without_touching_unrelated_cache_data() {
        let document = json!({
            "version": 2,
            "generated_at": 1,
            "sections": {
                "controllers-detect": {"ts": 1, "data": []},
                "custom": {"ts": 1, "data": "keep"}
            }
        });
        let updated = invalidate_sections(&document, Some(&["controllers-detect"]), 42.0).unwrap();
        assert!(updated["sections"].get("controllers-detect").is_none());
        assert_eq!(updated["sections"]["custom"]["data"], "keep");
        assert_eq!(updated["generated_at"], 42.0);
        assert!(invalidate_sections(&updated, Some(&["controllers-detect"]), 43.0).is_none());
    }

    #[test]
    fn invalidates_all_known_sections_but_preserves_unknown_sections() {
        let document = json!({"sections":{"audit-cache":{},"custom":{}},"metadata":"keep"});
        let updated = invalidate_sections(&document, None, 9.0).unwrap();
        assert!(updated["sections"].get("audit-cache").is_none());
        assert!(updated["sections"].get("custom").is_some());
        assert_eq!(updated["metadata"], "keep");
    }

    #[test]
    fn writes_a_cache_document_atomically() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let document = json!({"sections":{"bootc-branch":{"ts":1,"data":"testing"}}});
        write_cache_file(&path, &document).unwrap();
        assert_eq!(load_cache_file(&path), Some(document));
    }

    #[test]
    fn updates_sections_in_the_existing_cache_format() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let mut sections = serde_json::Map::new();
        sections.insert("bootc-branch".into(), json!("testing"));
        update_sections(&sections, Some(&path), false).unwrap();
        let written = load_cache_file(&path).unwrap();
        assert_eq!(written["version"], 2);
        assert_eq!(written["sections"]["bootc-branch"]["data"], "testing");
    }

    #[test]
    fn update_sections_writes_an_atomic_versioned_document() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let mut sections = serde_json::Map::new();
        sections.insert("network-summary".into(), json!({"vpn_connected": false}));
        update_sections(&sections, Some(&path), false).unwrap();
        let written: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
        assert_eq!(written["version"], 2);
        assert!(written["generated_at"].as_f64().unwrap() > 0.0);
        assert_eq!(
            written["sections"]["network-summary"]["data"]["vpn_connected"],
            false
        );
    }

    #[test]
    fn default_route_found_in_v4_table() {
        let v4 = "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n\
                  eth0\t00000000\t0101A8C0\t0003\t0\t0\t100\t00000000\n";
        assert!(has_default_route_in(v4, ""));
    }

    #[test]
    fn v4_header_alone_is_not_a_default_route() {
        let v4 = "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n\
                  eth0\t0001A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\n";
        assert!(!has_default_route_in(v4, ""));
    }

    #[test]
    fn default_route_found_as_first_v6_entry() {
        // /proc/net/ipv6_route has NO header: the default route can be the
        // very first line. The old .skip(1) on the v6 table never examined
        // it and reported offline on v6-only-default machines.
        let v6 = "00000000000000000000000000000000 00 00000000000000000000000000000000 00 \
                  fe800000000000000000000000000001 000000c0 00000000 00000000 00000001 eth0\n";
        assert!(has_default_route_in("", v6));
    }

    #[test]
    fn v6_default_route_after_other_entries_is_found() {
        let v6 = "fe800000000000000000000000000000 40 00000000000000000000000000000000 00 \
                  00000000000000000000000000000000 000000c0 00000000 00000000 00000001 eth0\n\
                  00000000000000000000000000000000 00 00000000000000000000000000000000 00 \
                  fe800000000000000000000000000001 000000c0 00000000 00000000 00000001 eth0\n";
        assert!(has_default_route_in("", v6));
    }

    #[test]
    fn v6_zero_prefix_with_loopback_next_hop_is_not_a_default_route() {
        let v6 = "00000000000000000000000000000000 00 00000000000000000000000000000000 00 \
                  00000000000000000000000000000000 000000c0 00000000 00000000 00000001 lo\n";
        assert!(!has_default_route_in("", v6));
    }

    #[test]
    fn only_the_system_cache_path_gets_the_world_readable_mode() {
        // S-H2: the root probe service writes under UMask=0077; the system
        // cache must be forced to 0644 or user-session readers get EACCES.
        // User caches keep the default mode (None = leave as created).
        assert_eq!(cache_file_mode(&system_cache_path()), Some(0o644));
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(cache_file_mode(&dir.path().join("probe-cache.json")), None);
    }

    #[test]
    fn write_cache_file_with_mode_applies_the_mode_before_publishing() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let document = json!({"sections":{"bootc-branch":{"ts":1,"data":"testing"}}});
        write_cache_file_with_mode(&path, &document, Some(0o644)).unwrap();
        let mode = fs::metadata(&path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o644);
        assert_eq!(load_cache_file(&path), Some(document));
    }

    #[test]
    fn streaming_collection_reports_each_completed_group() {
        // F6: the streamed batches must partition exactly the sections the
        // collection returns, so probe_bin's incremental persistence can
        // neither lose nor invent a section relative to the final write.
        let mut batches: Vec<serde_json::Map<String, Value>> = Vec::new();
        let sections = collect_snapshot_streaming(deferred_system_sections(), &mut |batch| {
            batches.push(batch.clone())
        });
        assert!(!sections.contains_key("flatpak-updates"));
        assert!(!batches.is_empty(), "live collection produced no batches");
        let streamed: Vec<&String> = batches.iter().flat_map(|batch| batch.keys()).collect();
        assert_eq!(
            streamed.len(),
            sections.len(),
            "each section must be streamed exactly once"
        );
        for key in &streamed {
            assert!(sections.contains_key(*key), "streamed unknown key {key}");
            assert_eq!(
                batches.iter().find_map(|batch| batch.get(*key)).unwrap(),
                &sections[*key],
                "streamed value for {key} differs from the returned section"
            );
        }
    }

    /// A prior writer killed by SIGKILL/SIGABRT (e.g. a systemd unit hitting
    /// its timeout) leaves its lock file on disk with no flock held on it.
    /// The next run must still succeed instead of treating the leftover file
    /// as evidence that a writer is still active.
    #[test]
    fn write_cache_file_recovers_from_a_stale_unlocked_lock_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let lock = path.with_extension("json.lock");
        std::fs::write(&lock, b"").unwrap();
        let document = json!({"sections": {"bootc-branch": {"ts": 1.0, "data": "testing"}}});
        write_cache_file(&path, &document).unwrap();
        let written = load_cache_file(&path).unwrap();
        assert_eq!(written["sections"]["bootc-branch"]["data"], "testing");
    }

    /// A prior writer killed mid-write (SIGKILL/SIGABRT) never releases its
    /// flock explicitly. This must still not block the next writer: the
    /// kernel drops the lock the instant the dead process's file descriptors
    /// close, which happens on any exit path, including a signal.
    #[test]
    fn write_cache_file_recovers_from_a_lock_held_by_a_crashed_process() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("probe-cache.json");
        let lock = path.with_extension("json.lock");
        std::fs::create_dir_all(dir.path()).unwrap();

        // SAFETY: the child only locks a file descriptor and calls _exit,
        // never touching Rust state shared with the parent or the test
        // harness's other threads. It opens the lock file itself, after the
        // fork, so its file descriptor is its own open file description —
        // exactly like a real crashed process, and unlike an fd inherited
        // from the parent, which would keep the flock alive past the
        // child's exit because the parent still holds that same
        // description open.
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0, "fork failed");
        if pid == 0 {
            let lock_file = std::fs::OpenOptions::new()
                .write(true)
                .create(true)
                .truncate(false)
                .open(&lock)
                .expect("child failed to open lock file");
            rustix::fs::flock(&lock_file, rustix::fs::FlockOperation::LockExclusive)
                .expect("child failed to acquire flock");
            unsafe { libc::_exit(0) };
        }
        let mut status = 0;
        assert!(unsafe { libc::waitpid(pid, &mut status, 0) } == pid);
        assert_eq!(
            status, 0,
            "child failed to acquire the flock before exiting"
        );

        let document = json!({"sections": {"bootc-branch": {"ts": 1.0, "data": "testing"}}});
        write_cache_file(&path, &document).unwrap();
        let written = load_cache_file(&path).unwrap();
        assert_eq!(written["sections"]["bootc-branch"]["data"], "testing");
    }
}
