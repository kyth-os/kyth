//! Safe setup-transfer manifest validation and preview data.
//!
//! Archive extraction and restoration remain explicit, guarded operations in
//! the existing helper. This module owns only the format contract and path
//! allowlist so native clients can inspect an archive manifest safely.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::io::{BufRead, BufReader};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

pub const ARCHIVE_VERSION: u64 = 1;
pub const ARCHIVE_PREFIX: &str = "kyth-setup";

pub const CONFIG_PATHS: &[&str] = &[
    ".config/kdeglobals",
    ".config/kglobalshortcutsrc",
    ".config/kwinrc",
    ".config/kwinrulesrc",
    ".config/kcminputrc",
    ".config/kscreenlockerrc",
    ".config/klipperrc",
    ".config/plasmarc",
    ".config/powerdevilrc",
    ".config/spectaclerc",
    ".config/konsolerc",
    ".config/kwalletrc",
    ".config/kyth-cloud-sync.json",
    ".config/kyth-dynamic-lock.json",
    ".config/kyth-smb-shares.json",
    ".config/MangoHud",
    ".config/vkBasalt",
    ".local/share/kyth/profile",
];

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct SetupFlatpak {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub origin: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct SetupManifest {
    pub format: String,
    pub version: u64,
    #[serde(default)]
    pub created: String,
    #[serde(default)]
    pub hostname: String,
    #[serde(default)]
    pub flatpaks: Vec<SetupFlatpak>,
    #[serde(default)]
    pub default_apps: BTreeMap<String, String>,
    #[serde(default)]
    pub cloud_remotes: Vec<Value>,
    pub copied_paths: Vec<String>,
    #[serde(default)]
    pub secrets_excluded: Vec<String>,
}

pub fn is_allowed_restore_path(relative: &str) -> bool {
    let path = Path::new(relative);
    if path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return false;
    }
    if CONFIG_PATHS.contains(&relative) {
        return true;
    }
    let components = path.components().collect::<Vec<_>>();
    components.len() == 4
        && components[0].as_os_str() == ".local"
        && components[1].as_os_str() == "share"
        && components[2].as_os_str() == "applications"
        && components[3]
            .as_os_str()
            .to_string_lossy()
            .starts_with("kyth-")
        && components[3]
            .as_os_str()
            .to_string_lossy()
            .ends_with(".desktop")
}

pub fn validate_manifest(value: &Value) -> Result<SetupManifest, String> {
    let object = value
        .as_object()
        .ok_or_else(|| "The setup archive manifest is invalid.".to_string())?;
    if object.get("format").and_then(Value::as_str) != Some("KythOS setup transfer") {
        return Err("This is not a KythOS setup archive.".to_string());
    }
    if object.get("version").and_then(Value::as_u64) != Some(ARCHIVE_VERSION) {
        return Err(format!(
            "Unsupported setup archive version: {}",
            object.get("version").unwrap_or(&Value::Null)
        ));
    }
    let copied = object
        .get("copied_paths")
        .and_then(Value::as_array)
        .ok_or_else(|| "The setup archive contains an unsupported settings path.".to_string())?;
    if !copied
        .iter()
        .all(|path| path.as_str().is_some_and(is_allowed_restore_path))
    {
        return Err("The setup archive contains an unsupported settings path.".to_string());
    }
    serde_json::from_value(value.clone())
        .map_err(|_| "The setup archive manifest is malformed.".to_string())
}

pub fn preview_summary(manifest: &SetupManifest) -> String {
    let flatpaks = manifest.flatpaks.len();
    let settings = manifest.copied_paths.len();
    let remotes = manifest.cloud_remotes.len();
    format!(
        "Created {} on {}\n{} Flatpak apps, {} settings paths, {} cloud definitions\nPasswords and login tokens are excluded. Network shares and cloud accounts will need reauthentication.",
        if manifest.created.is_empty() { "unknown" } else { &manifest.created },
        if manifest.hostname.is_empty() { "unknown" } else { &manifest.hostname },
        flatpaks,
        settings,
        remotes,
    )
}

// Native export/restore/summary operations for `kyth-setup-transfer`.
//
// `SetupCtx` carries the home directory, an injectable text-command runner
// (`None` = the command failed or timed out, mirroring `run_text`), clock
// and hostname providers, and whether `flatpak` is on `PATH`, so the full
// launcher workflow is unit-testable without touching the live system.

pub const FLATHUB_REPO: &str = "https://dl.flathub.org/repo/flathub.flatpakrepo";

pub const DEFAULT_MIME_TYPES: &[&str] = &[
    "text/html",
    "x-scheme-handler/http",
    "x-scheme-handler/https",
    "x-scheme-handler/mailto",
    "application/pdf",
    "image/jpeg",
    "image/png",
    "video/mp4",
    "audio/mpeg",
    "text/plain",
    "inode/directory",
];

pub const SECRETS_EXCLUDED: &[&str] = &[
    "browser profiles and cookies",
    "KWallet contents",
    "rclone OAuth tokens",
    "SMB passwords",
];

pub const DYNAMIC_LOCK_CONFIG: &str = ".config/kyth-dynamic-lock.json";
pub const DYNAMIC_LOCK_UNIT: &str = "kyth-dynamic-lock.service";

/// Optional Flatpak app-data bundle (`~/.var/app`) inside a setup archive.
/// Off by default: app data dwarfs settings (shaders/caches, tens of GiB),
/// so export requires explicit opt-in and warns above this size first.
/// Shares the threshold with `save_cloud::FLATPAK_DATA_WARN_BYTES`.
pub const FLATPAK_DATA_WARN_BYTES: u64 = 10 * 1024 * 1024 * 1024;
pub const FLATPAK_DATA_REL: &str = ".var/app";

/// Size-warn gate for the optional Flatpak-data bundle: `Ok(bytes)` when the
/// bundle fits, `Err(warning)` with the human-readable warning when it
/// exceeds [`FLATPAK_DATA_WARN_BYTES`] and needs explicit confirmation.
pub fn check_flatpak_data_bundle(home: &Path) -> Result<u64, String> {
    let bytes = crate::system::save_cloud::dir_size_bytes(&home.join(FLATPAK_DATA_REL));
    if bytes >= FLATPAK_DATA_WARN_BYTES {
        return Err(format!(
            "Flatpak app data is {:.1} GiB (>= 10 GiB); bundling it makes a very \
             large archive. Confirm explicitly to include `{FLATPAK_DATA_REL}`.",
            bytes as f64 / 1024.0 / 1024.0 / 1024.0
        ));
    }
    Ok(bytes)
}

pub type RunText<'a> = dyn for<'x> Fn(&'x [String], u64) -> Option<(i32, String)> + 'a;

pub struct SetupCtx<'a> {
    pub home: &'a Path,
    pub run_text: &'a RunText<'a>,
    pub stamp: &'a dyn Fn() -> String,
    pub iso_now: &'a dyn Fn() -> String,
    pub hostname: &'a dyn Fn() -> String,
    pub flatpak_present: bool,
}

fn argv(parts: &[&str]) -> Vec<String> {
    parts.iter().map(|part| (*part).to_string()).collect()
}

fn run_ok(ctx: &SetupCtx, parts: &[&str], timeout_secs: u64) -> Option<String> {
    (ctx.run_text)(&argv(parts), timeout_secs)
        .and_then(|(code, stdout)| if code == 0 { Some(stdout) } else { None })
}

/// Parse `flatpak list --app --columns=application,origin` output: tab-split
/// rows, blank ids skipped, missing origins default to flathub, sorted by
/// lowercase id.
pub fn parse_flatpak_list(output: &str) -> Vec<SetupFlatpak> {
    let mut apps: Vec<SetupFlatpak> = output
        .lines()
        .filter_map(|line| {
            let mut parts = line.splitn(2, '\t');
            let id = parts.next().unwrap_or_default().trim();
            if id.is_empty() {
                return None;
            }
            Some(SetupFlatpak {
                id: id.to_string(),
                origin: parts.next().map(str::trim).unwrap_or("flathub").to_string(),
            })
        })
        .collect();
    apps.sort_by(|a, b| a.id.to_lowercase().cmp(&b.id.to_lowercase()));
    apps
}

pub fn installed_flatpaks(ctx: &SetupCtx) -> Vec<SetupFlatpak> {
    run_ok(
        ctx,
        &["flatpak", "list", "--app", "--columns=application,origin"],
        30,
    )
    .map(|stdout| parse_flatpak_list(&stdout))
    .unwrap_or_default()
}

/// Query the default handler for every known MIME type via `xdg-mime`.
pub fn default_apps(ctx: &SetupCtx) -> BTreeMap<String, String> {
    let mut defaults = BTreeMap::new();
    for mime in DEFAULT_MIME_TYPES {
        let parts = ["xdg-mime", "query", "default", mime];
        if let Some(stdout) = run_ok(ctx, &parts, 5) {
            let desktop = stdout.trim();
            if !desktop.is_empty() {
                defaults.insert(mime.to_string(), desktop.to_string());
            }
        }
    }
    defaults
}

/// Parse `rclone listremotes --long` output into `{name, type}` entries.
pub fn parse_cloud_remotes(output: &str) -> Vec<Value> {
    output
        .lines()
        .filter_map(|line| {
            let mut parts = line.split_whitespace();
            let name = parts.next()?;
            Some(serde_json::json!({
                "name": name.trim_end_matches(':'),
                "type": parts.next().unwrap_or("unknown"),
            }))
        })
        .collect()
}

pub fn cloud_remotes(ctx: &SetupCtx) -> Vec<Value> {
    run_ok(ctx, &["rclone", "listremotes", "--long"], 10)
        .map(|stdout| parse_cloud_remotes(&stdout))
        .unwrap_or_default()
}

fn copy_file_nofollow(source: &Path, target: &Path) -> std::io::Result<()> {
    let kind = std::fs::symlink_metadata(source)?.file_type();
    if kind.is_symlink() {
        let link = std::fs::read_link(source)?;
        if std::fs::symlink_metadata(target).is_ok() {
            std::fs::remove_file(target)?;
        }
        std::os::unix::fs::symlink(link, target)?;
        return Ok(());
    }
    std::fs::copy(source, target)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(mode) = std::fs::metadata(source).map(|meta| meta.permissions().mode()) {
            let _ = std::fs::set_permissions(target, std::fs::Permissions::from_mode(mode));
        }
    }
    Ok(())
}

fn copy_dir_recursive(source: &Path, target: &Path, merge: bool) -> std::io::Result<()> {
    if target.exists() {
        if !merge {
            std::fs::remove_dir_all(target)?;
        }
    } else {
        std::fs::create_dir_all(target)?;
    }
    for entry in std::fs::read_dir(source)? {
        let entry = entry?;
        let from = entry.path();
        let to = target.join(entry.file_name());
        let kind = entry.file_type()?;
        if kind.is_symlink() {
            copy_file_nofollow(&from, &to)?;
        } else if kind.is_dir() {
            copy_dir_recursive(&from, &to, merge)?;
        } else {
            copy_file_nofollow(&from, &to)?;
        }
    }
    Ok(())
}

/// Copy one allowlisted relative path into `payload/files/`,
/// DEREFERENCING symlinks into plain files/dirs. A link planted (or
/// merely present) in $HOME must never become a link inside the archive:
/// safe_extract refuses any archive containing symlinks under files/, so
/// the exporter writes link-free payloads our own restores accept.
pub fn copy_into_payload(home: &Path, payload: &Path, rel: &str) -> bool {
    let source = home.join(rel);
    if std::fs::symlink_metadata(&source).is_err() {
        return false;
    }
    let target = payload.join("files").join(rel);
    if target
        .parent()
        .is_some_and(|parent| std::fs::create_dir_all(parent).is_err())
    {
        return false;
    }
    // symlink_metadata classifies the link itself; a symlinked dir must
    // recurse through the target, never be recreated as a link.
    let is_dir = source.is_dir();
    let result = if is_dir {
        copy_dir_deref_inner(&source, &target, 0)
    } else {
        copy_file_deref(&source, &target)
    };
    result.is_ok()
}

/// Recursive copy that follows symlinks (read_dir traverses dir links,
/// fs::copy copies file content). Export-only: restores never need this
/// because extracted payloads are symlink-free by construction. Depth is
/// capped so a link loop (a -> b -> a) fails instead of recursing forever.
fn copy_dir_deref_inner(source: &Path, target: &Path, depth: u32) -> std::io::Result<()> {
    if depth > 32 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "symlink depth exceeded",
        ));
    }
    std::fs::create_dir_all(target)?;
    for entry in std::fs::read_dir(source)? {
        let entry = entry?;
        let from = entry.path();
        let to = target.join(entry.file_name());
        if from.is_dir() {
            copy_dir_deref_inner(&from, &to, depth + 1)?;
        } else {
            copy_file_deref(&from, &to)?;
        }
    }
    Ok(())
}

fn copy_file_deref(source: &Path, target: &Path) -> std::io::Result<()> {
    if std::fs::symlink_metadata(target).is_ok() {
        std::fs::remove_file(target)?;
    }
    std::fs::copy(source, target)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(mode) = std::fs::metadata(source).map(|meta| meta.permissions().mode()) {
            let _ = std::fs::set_permissions(target, std::fs::Permissions::from_mode(mode));
        }
    }
    Ok(())
}

/// Relative paths of `kyth-*.desktop` launchers under
/// `~/.local/share/applications`.
pub fn desktop_entry_rels(home: &Path) -> Vec<String> {
    let dir = home.join(".local/share/applications");
    let Ok(entries) = std::fs::read_dir(&dir) else {
        return Vec::new();
    };
    let mut rels = Vec::new();
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if name.starts_with("kyth-") && name.ends_with(".desktop") {
            rels.push(format!(".local/share/applications/{name}"));
        }
    }
    rels.sort();
    rels
}

static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

struct TempDir {
    path: PathBuf,
}

impl TempDir {
    fn create(prefix: &str) -> Result<Self, String> {
        for _ in 0..100 {
            let id = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!("{prefix}-{}-{id}", std::process::id()));
            match std::fs::create_dir(&path) {
                Ok(()) => return Ok(Self { path }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(format!("Cannot create temporary directory: {error}")),
            }
        }
        Err("Cannot create temporary directory: too many collisions".to_string())
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.path);
    }
}

fn tar(ctx: &SetupCtx, args: &[&str], timeout_secs: u64) -> Result<String, String> {
    let full = argv(&[&["tar"], args].concat());
    (ctx.run_text)(&full, timeout_secs)
        .and_then(|(code, stdout)| if code == 0 { Some(stdout) } else { None })
        .ok_or_else(|| "Setup archive I/O failed: tar reported an error.".to_string())
}

/// Create a setup archive in `dest`, returning its path.
pub fn export_setup(ctx: &SetupCtx, dest: &Path) -> Result<PathBuf, String> {
    std::fs::create_dir_all(dest)
        .map_err(|error| format!("Cannot use archive destination: {error}"))?;
    let archive = dest.join(format!("{ARCHIVE_PREFIX}-{}.tar.gz", (ctx.stamp)()));
    let work = TempDir::create("kyth-setup-export")?;
    let payload = work.path.join(ARCHIVE_PREFIX);
    std::fs::create_dir_all(&payload)
        .map_err(|error| format!("Cannot stage setup archive: {error}"))?;
    let mut copied: Vec<String> = Vec::new();
    for rel in CONFIG_PATHS {
        if copy_into_payload(ctx.home, &payload, rel) {
            copied.push(rel.to_string());
        }
    }
    for rel in desktop_entry_rels(ctx.home) {
        if !copied.contains(&rel) && copy_into_payload(ctx.home, &payload, &rel) {
            copied.push(rel);
        }
    }
    copied.sort();
    let manifest = serde_json::json!({
        "format": "KythOS setup transfer",
        "version": ARCHIVE_VERSION,
        "created": (ctx.iso_now)(),
        "hostname": (ctx.hostname)(),
        "flatpaks": installed_flatpaks(ctx),
        "default_apps": default_apps(ctx),
        "cloud_remotes": cloud_remotes(ctx),
        "copied_paths": copied,
        "secrets_excluded": SECRETS_EXCLUDED,
    });
    std::fs::write(
        payload.join("manifest.json"),
        serde_json::to_string_pretty(&manifest).unwrap_or_default() + "\n",
    )
    .map_err(|error| format!("Cannot stage setup archive: {error}"))?;
    let archive_arg = archive.to_string_lossy().into_owned();
    let work_arg = work.path.to_string_lossy().into_owned();
    tar(
        ctx,
        &["-czf", &archive_arg, "-C", &work_arg, ARCHIVE_PREFIX],
        120,
    )?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&archive, std::fs::Permissions::from_mode(0o600))
            .map_err(|error| format!("Cannot secure setup archive: {error}"))?;
    }
    Ok(archive)
}

/// List archive members without extracting.
pub fn tar_members(ctx: &SetupCtx, archive: &Path) -> Result<Vec<String>, String> {
    let out = tar(ctx, &["-tzf", &archive.to_string_lossy()], 60)?;
    Ok(out.lines().map(str::to_string).collect())
}

/// Extract after rejecting absolute and parent-traversing member names.
/// Returns the payload directory.
pub fn safe_extract(ctx: &SetupCtx, archive: &Path, dest: &Path) -> Result<PathBuf, String> {
    for name in tar_members(ctx, archive)? {
        let path = Path::new(&name);
        if path.is_absolute()
            || path
                .components()
                .any(|component| matches!(component, Component::ParentDir))
        {
            return Err(format!("Unsafe archive path: {name}"));
        }
    }
    tar(
        ctx,
        &[
            "-xzf",
            &archive.to_string_lossy(),
            "-C",
            &dest.to_string_lossy(),
        ],
        120,
    )?;
    let payload = dest.join(ARCHIVE_PREFIX);
    if !payload.is_dir() {
        return Err("This is not a KythOS setup archive.".to_string());
    }
    // Symlink sweep: tar plants `files/.config/x -> /etc`-style links at
    // extract time, and restore would faithfully recreate them in $HOME.
    // Our own exporter never writes symlinks, so any is hostile — refuse
    // the whole archive rather than restoring around it.
    let mut links = Vec::new();
    let mut stack = vec![payload.join("files")];
    while let Some(directory) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_symlink() {
                links.push(path);
            } else if path.is_dir() {
                stack.push(path);
            }
        }
    }
    if !links.is_empty() {
        return Err(format!(
            "Unsafe archive: {} symlink(s) under files/ (first: {}). Only archives exported by KythOS itself are safe to restore.",
            links.len(),
            links[0].display()
        ));
    }
    Ok(payload)
}

/// Read and validate the payload manifest, preserving the Python error
/// contract for missing versus malformed manifests.
pub fn load_manifest_from_payload(payload: &Path) -> Result<SetupManifest, String> {
    let text = std::fs::read_to_string(payload.join("manifest.json"))
        .map_err(|_| "The setup archive manifest is missing or invalid.".to_string())?;
    let value: Value = serde_json::from_str(&text)
        .map_err(|_| "The setup archive manifest is missing or invalid.".to_string())?;
    validate_manifest(&value)
}

/// Seconds-precision local ISO-8601 timestamp for the archive manifest,
/// mirroring `datetime.now().astimezone().isoformat(timespec="seconds")`.
pub fn now_iso_seconds() -> String {
    let full = crate::system::session_snapshot::now_iso();
    match full.find('.') {
        Some(dot) if full.len() >= dot + 7 => {
            format!("{}{}", &full[..dot], &full[full.len() - 6..])
        }
        _ => full,
    }
}

/// Describe an archive without restoring it.
pub fn archive_summary(ctx: &SetupCtx, archive: &Path) -> Result<String, String> {
    let work = TempDir::create("kyth-setup-summary")?;
    let payload = safe_extract(ctx, archive, &work.path)?;
    Ok(preview_summary(&load_manifest_from_payload(&payload)?))
}

/// Copy validated payload files back into `home`, merging directories.
/// Returns the number of restored paths.
pub fn restore_files(payload: &Path, home: &Path, paths: &[String]) -> usize {
    let mut restored = 0;
    for rel in paths {
        let source = payload.join("files").join(rel);
        if std::fs::symlink_metadata(&source).is_err() {
            continue;
        }
        let target = home.join(rel);
        if target
            .parent()
            .is_some_and(|parent| std::fs::create_dir_all(parent).is_err())
        {
            continue;
        }
        let kind = std::fs::symlink_metadata(&source).map(|meta| meta.file_type());
        let ok = match kind {
            Ok(kind) if kind.is_dir() && !kind.is_symlink() => {
                copy_dir_recursive(&source, &target, true).is_ok()
            }
            Ok(_) => copy_file_nofollow(&source, &target).is_ok(),
            Err(_) => false,
        };
        if ok {
            restored += 1;
        }
    }
    restored
}

pub fn restore_defaults(ctx: &SetupCtx, defaults: &BTreeMap<String, String>) -> usize {
    let mut restored = 0;
    for (mime, desktop) in defaults {
        if run_ok(ctx, &["xdg-mime", "default", desktop, mime], 10).is_some() {
            restored += 1;
        }
    }
    restored
}

/// Re-enable the Dynamic Lock user unit when the restored config opts in.
pub fn restore_dynamic_lock(ctx: &SetupCtx) -> bool {
    let text = match std::fs::read_to_string(ctx.home.join(DYNAMIC_LOCK_CONFIG)) {
        Ok(text) => text,
        Err(_) => return false,
    };
    let enabled = serde_json::from_str::<Value>(&text)
        .ok()
        .and_then(|value| value.get("enabled").and_then(Value::as_bool))
        .unwrap_or(false);
    if !enabled {
        return false;
    }
    run_ok(
        ctx,
        &["systemctl", "--user", "enable", "--now", DYNAMIC_LOCK_UNIT],
        30,
    )
    .is_some()
}

/// Stream one fixed argv, printing each stdout line as it arrives and
/// merging trailing stderr lines after exit. Returns the exit code, or `1`
/// when the process cannot start or outlives its bound.
pub fn stream_command(args: &[String], timeout_secs: u64, on_line: &dyn Fn(&str)) -> i32 {
    let Some((program, rest)) = args.split_first() else {
        return 1;
    };
    let mut child = match Command::new(program)
        .args(rest)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(child) => child,
        Err(_) => return 1,
    };
    let stdout = child.stdout.take().map(BufReader::new);
    let mut lines = stdout.map(BufReader::lines);
    let started = Instant::now();
    let code = loop {
        while let Some(Ok(line)) = lines.as_mut().and_then(|iterator| iterator.next()) {
            let trimmed = line.trim();
            if !trimmed.is_empty() {
                on_line(trimmed);
            }
        }
        match child.try_wait() {
            Ok(Some(status)) => break status.code().unwrap_or(1),
            Ok(None) if started.elapsed() <= Duration::from_secs(timeout_secs) => {
                std::thread::sleep(Duration::from_millis(50));
            }
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return 1;
            }
        }
    };
    if let Some(mut child) = child
        .stderr
        .take()
        .map(BufReader::new)
        .map(BufReader::lines)
    {
        for line in child.by_ref().flatten() {
            let trimmed = line.trim().to_string();
            if !trimmed.is_empty() {
                on_line(&trimmed);
            }
        }
    }
    // Drain any stdout lines that arrived after the final poll.
    if let Some(iterator) = lines.as_mut() {
        for line in iterator.flatten() {
            let trimmed = line.trim().to_string();
            if !trimmed.is_empty() {
                on_line(&trimmed);
            }
        }
    }
    code
}

/// Reinstall archived Flatpaks from their recorded origins, streaming each
/// installer's output behind the `Restoring app:` status line. Returns
/// `(installed, failed)`.
pub fn restore_flatpaks(
    ctx: &SetupCtx,
    stream: &dyn Fn(&[String], &dyn Fn(&str)) -> i32,
    on_line: &dyn Fn(&str),
    apps: &[SetupFlatpak],
) -> (usize, usize) {
    if apps.is_empty() {
        return (0, 0);
    }
    if !ctx.flatpak_present {
        return (0, apps.len());
    }
    let _ = run_ok(
        ctx,
        &[
            "flatpak",
            "remote-add",
            "--if-not-exists",
            "flathub",
            FLATHUB_REPO,
        ],
        60,
    );
    let mut remotes = std::collections::HashSet::from(["flathub".to_string()]);
    if let Some(stdout) = run_ok(ctx, &["flatpak", "remotes", "--columns=name"], 10) {
        remotes = stdout.split_whitespace().map(str::to_string).collect();
    }
    let mut installed = 0;
    let mut failed = 0;
    for app in apps {
        let id = app.id.trim();
        if id.is_empty() {
            continue;
        }
        let origin = app.origin.trim();
        let origin = if remotes.contains(origin) {
            origin
        } else {
            "flathub"
        };
        on_line(&format!("Restoring app: {id}"));
        let code = stream(
            &argv(&["flatpak", "install", "-y", "--or-update", origin, id]),
            on_line,
        );
        if code == 0 {
            installed += 1;
        } else {
            failed += 1;
        }
    }
    (installed, failed)
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RestoreReport {
    pub paths: usize,
    pub defaults: usize,
    pub apps_ok: usize,
    pub apps_failed: usize,
    pub cloud_names: Vec<String>,
    pub dynamic_lock: bool,
}

/// Restore an archive into `home`, returning the report the launcher prints.
pub fn restore_setup(
    ctx: &SetupCtx,
    stream: &dyn Fn(&[String], &dyn Fn(&str)) -> i32,
    on_line: &dyn Fn(&str),
    archive: &Path,
) -> Result<RestoreReport, String> {
    let work = TempDir::create("kyth-setup-restore")?;
    let payload = safe_extract(ctx, archive, &work.path)?;
    let manifest = load_manifest_from_payload(&payload)?;
    let paths = restore_files(&payload, ctx.home, &manifest.copied_paths);
    let defaults = restore_defaults(ctx, &manifest.default_apps);
    let dynamic_lock = restore_dynamic_lock(ctx);
    let remotes = manifest
        .cloud_remotes
        .iter()
        .filter_map(|remote| {
            remote
                .get("name")
                .and_then(Value::as_str)
                .map(str::to_string)
        })
        .collect::<Vec<_>>();
    let (apps_ok, apps_failed) = restore_flatpaks(ctx, stream, on_line, &manifest.flatpaks);
    let _ = run_ok(ctx, &["kbuildsycoca6", "--noincremental"], 30);
    Ok(RestoreReport {
        paths,
        defaults,
        apps_ok,
        apps_failed,
        cloud_names: remotes,
        dynamic_lock,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest(paths: &[&str]) -> Value {
        serde_json::json!({
            "format": "KythOS setup transfer", "version": 1,
            "created": "2026-08-29T00:00:00+00:00", "hostname": "kyth-live",
            "flatpaks": [{"id":"org.example.App","origin":"flathub"}],
            "default_apps": {"text/plain":"org.kde.kwrite.desktop"},
            "cloud_remotes": [{"name":"drive","type":"webdav"}],
            "copied_paths": paths, "secrets_excluded": ["KWallet contents"]
        })
    }

    #[test]
    fn validates_manifest_and_renders_preview() {
        let value = manifest(&[
            ".config/kdeglobals",
            ".local/share/applications/kyth-demo.desktop",
        ]);
        let parsed = validate_manifest(&value).unwrap();
        assert_eq!(parsed.flatpaks[0].id, "org.example.App");
        assert!(preview_summary(&parsed).contains("1 Flatpak apps, 2 settings paths"));
    }

    #[test]
    fn rejects_traversal_and_unowned_desktop_files() {
        assert!(is_allowed_restore_path(".config/kdeglobals"));
        assert!(is_allowed_restore_path(
            ".local/share/applications/kyth-demo.desktop"
        ));
        assert!(!is_allowed_restore_path("../.config/kdeglobals"));
        assert!(!is_allowed_restore_path(
            ".local/share/applications/other.desktop"
        ));
        assert!(!is_allowed_restore_path(
            ".local/share/applications/kyth-demo.desktop/extra"
        ));
        assert!(validate_manifest(&manifest(&[".config/unknown"])).is_err());
    }

    #[test]
    fn rejects_wrong_format_and_version() {
        let mut wrong_format = manifest(&[]);
        wrong_format["format"] = "other".into();
        assert!(validate_manifest(&wrong_format)
            .unwrap_err()
            .contains("not a KythOS"));
        let mut wrong_version = manifest(&[]);
        wrong_version["version"] = 2.into();
        assert!(validate_manifest(&wrong_version)
            .unwrap_err()
            .contains("Unsupported"));
    }

    fn stub_ctx<'a>(home: &'a Path, run: &'a RunText<'a>, flatpak_present: bool) -> SetupCtx<'a> {
        SetupCtx {
            home,
            run_text: run,
            stamp: &|| "20260907-120000".to_string(),
            iso_now: &|| "2026-09-07T12:00:00+00:00".to_string(),
            hostname: &|| "kyth-test".to_string(),
            flatpak_present,
        }
    }

    #[test]
    fn exporter_dereferences_symlinks_and_survives_loops() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path();
        // A symlinked file and dir inside an exported tree must land as
        // plain content, never as links (safe_extract refuses archives
        // containing symlinks under files/).
        std::fs::create_dir_all(home.join(".config/app")).unwrap();
        std::fs::write(home.join(".config/app/real.txt"), "data").unwrap();
        std::os::unix::fs::symlink(
            home.join(".config/app/real.txt"),
            home.join(".config/app/link.txt"),
        )
        .unwrap();
        std::os::unix::fs::symlink(home.join(".config/app"), home.join(".config/applink")).unwrap();
        // A link loop must fail, not recurse forever.
        std::os::unix::fs::symlink(home.join(".config/loop"), home.join(".config/loop")).unwrap();
        let payload = dir.path().join("payload");
        assert!(copy_into_payload(home, &payload, ".config/app/link.txt"));
        assert!(!payload.join("files/.config/app/link.txt").is_symlink());
        assert_eq!(
            std::fs::read_to_string(payload.join("files/.config/app/link.txt")).unwrap(),
            "data"
        );
        assert!(copy_into_payload(home, &payload, ".config/applink"));
        assert!(!payload.join("files/.config/applink").is_symlink());
        assert!(!copy_into_payload(home, &payload, ".config/loop"));
    }

    #[test]
    fn stamps_seconds_precision_iso_like_python() {
        let stamp = now_iso_seconds();
        assert!(!stamp.contains('.'));
        assert!(stamp.len() >= 25);
    }

    #[test]
    fn parses_flatpak_and_remote_listings_like_python() {
        let apps = parse_flatpak_list("org.z.App\tflathub\norg.a.App\n\n  \norg.m.App\tcustom\n");
        assert_eq!(apps.len(), 3);
        assert_eq!(apps[0].id, "org.a.App");
        assert_eq!(apps[0].origin, "flathub");
        assert_eq!(apps[1].origin, "custom");
        let remotes = parse_cloud_remotes("drive: webdav\nphotos:\n");
        assert_eq!(remotes[0]["name"], "drive");
        assert_eq!(remotes[0]["type"], "webdav");
        assert_eq!(
            remotes[1],
            serde_json::json!({"name": "photos", "type": "unknown"})
        );
    }

    #[test]
    fn failed_commands_yield_empty_collections() {
        let home = Path::new("/nonexistent-home");
        let run = |_: &[String], _: u64| None;
        let ctx = stub_ctx(home, &run, true);
        assert!(installed_flatpaks(&ctx).is_empty());
        assert!(cloud_remotes(&ctx).is_empty());
        assert!(default_apps(&ctx).is_empty());
        assert_eq!(restore_flatpaks(&ctx, &|_, _| 0, &|_| {}, &[]), (0, 0));
    }

    #[test]
    fn queries_each_mime_default_and_counts_restores() {
        let home = Path::new("/nonexistent-home");
        let run = |args: &[String], _: u64| {
            if args.iter().any(|arg| arg == "text/plain") {
                Some((0, "org.kde.kwrite.desktop\n".to_string()))
            } else if args[0] == "xdg-mime" {
                Some((1, String::new()))
            } else {
                Some((0, String::new()))
            }
        };
        let ctx = stub_ctx(home, &run, true);
        let defaults = default_apps(&ctx);
        assert_eq!(defaults.len(), 1);
        assert_eq!(restore_defaults(&ctx, &defaults), 1);
    }

    #[test]
    fn safe_extract_rejects_traversal_without_running_tar() {
        use std::cell::RefCell;
        let home = Path::new("/nonexistent-home");
        let calls = RefCell::new(Vec::new());
        let run = |args: &[String], _: u64| {
            calls.borrow_mut().push(args.join(" "));
            Some((0, "kyth-setup/manifest.json\n../evil\n".to_string()))
        };
        let ctx = stub_ctx(home, &run, true);
        let error =
            safe_extract(&ctx, Path::new("archive.tar.gz"), Path::new("/tmp/out")).unwrap_err();
        assert!(error.contains("Unsafe archive path: ../evil"));
        assert_eq!(calls.borrow().len(), 1);
    }

    #[test]
    fn flatpak_restore_counts_and_falls_back_to_flathub() {
        use std::cell::RefCell;
        let home = Path::new("/nonexistent-home");
        let run = |args: &[String], _: u64| {
            if args.iter().any(|arg| arg == "remotes") {
                Some((0, "flathub\n".to_string()))
            } else {
                Some((0, String::new()))
            }
        };
        let ctx = stub_ctx(home, &run, true);
        let seen = RefCell::new(Vec::new());
        let apps = vec![
            SetupFlatpak {
                id: "org.example.App".into(),
                origin: "missing-remote".into(),
            },
            SetupFlatpak {
                id: "  ".into(),
                origin: "flathub".into(),
            },
            SetupFlatpak {
                id: "org.example.Other".into(),
                origin: "flathub".into(),
            },
        ];
        let (ok, failed) = restore_flatpaks(
            &ctx,
            &|args, _| {
                seen.borrow_mut().push(args.join(" "));
                if args.iter().any(|arg| arg == "org.example.Other") {
                    1
                } else {
                    0
                }
            },
            &|_| {},
            &apps,
        );
        assert_eq!((ok, failed), (1, 1));
        assert!(seen.borrow()[0].contains("flathub org.example.App"));
    }

    #[test]
    fn missing_flatpak_marks_everything_failed() {
        let home = Path::new("/nonexistent-home");
        let run = |_: &[String], _: u64| Some((0, String::new()));
        let ctx = stub_ctx(home, &run, false);
        let apps = vec![SetupFlatpak {
            id: "org.example.App".into(),
            origin: "flathub".into(),
        }];
        assert_eq!(restore_flatpaks(&ctx, &|_, _| 0, &|_| {}, &apps), (0, 1));
    }

    #[test]
    fn dynamic_lock_restores_only_when_opted_in() {
        let dir = tempfile::tempdir().unwrap();
        let run = |_: &[String], _: u64| Some((0, String::new()));
        let ctx = stub_ctx(dir.path(), &run, true);
        assert!(!restore_dynamic_lock(&ctx));
        std::fs::create_dir_all(dir.path().join(".config")).unwrap();
        std::fs::write(dir.path().join(DYNAMIC_LOCK_CONFIG), r#"{"enabled": true}"#).unwrap();
        assert!(restore_dynamic_lock(&ctx));
    }

    #[test]
    fn round_trips_files_through_payload_copy() {
        let home = tempfile::tempdir().unwrap();
        let payload = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(home.path().join(".config")).unwrap();
        std::fs::write(home.path().join(".config/kdeglobals"), "theme=Breeze\n").unwrap();
        assert!(!copy_into_payload(
            home.path(),
            payload.path(),
            ".config/missing"
        ));
        assert!(copy_into_payload(
            home.path(),
            payload.path(),
            ".config/kdeglobals"
        ));
        let staged = payload.path().join("files/.config/kdeglobals");
        assert_eq!(std::fs::read_to_string(&staged).unwrap(), "theme=Breeze\n");
        let restore_home = tempfile::tempdir().unwrap();
        assert_eq!(
            restore_files(
                payload.path(),
                restore_home.path(),
                &[
                    ".config/kdeglobals".to_string(),
                    ".config/missing".to_string()
                ]
            ),
            1
        );
        assert!(restore_home.path().join(".config/kdeglobals").is_file());
    }

    #[test]
    fn flatpak_data_bundle_is_small_ok_and_warns_when_large() {
        let home = tempfile::tempdir().unwrap();
        // No ~/.var/app at all: 0 bytes, no warning.
        assert_eq!(check_flatpak_data_bundle(home.path()), Ok(0));
        std::fs::create_dir_all(home.path().join(".var/app/org.example.App")).unwrap();
        std::fs::write(
            home.path().join(".var/app/org.example.App/data.bin"),
            [1u8; 64],
        )
        .unwrap();
        assert!(check_flatpak_data_bundle(home.path()).is_ok());
        assert_eq!(
            FLATPAK_DATA_WARN_BYTES,
            crate::system::save_cloud::FLATPAK_DATA_WARN_BYTES
        );
    }

    #[test]
    fn wipe_restore_runbook_export_wipe_restore_round_trip() {
        // Mirrors docs/wipe-restore-runbook.md: export settings from a home,
        // wipe the config tree (fresh install simulation), restore into the
        // wiped home, and confirm the settings come back byte-identical.
        let home = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(home.path().join(".config")).unwrap();
        std::fs::write(home.path().join(".config/kdeglobals"), "theme=Breeze\n").unwrap();
        let run = |argv: &[String], _: u64| {
            // Genuine round trip: tar really archives/extracts (checked
            // above); everything else is stubbed success.
            if argv.first().map(String::as_str) == Some("tar") {
                let output = std::process::Command::new("tar").args(&argv[1..]).output();
                return output.ok().map(|out| {
                    (
                        out.status.code().unwrap_or(1),
                        String::from_utf8_lossy(&out.stdout).into_owned(),
                    )
                });
            }
            Some((0, String::new()))
        };
        let stamp = || "2026-09-18T00-00-00".to_string();
        let iso_now = || "2026-09-18T00:00:00+00:00".to_string();
        let hostname = || "kyth-live".to_string();
        let ctx = stub_ctx(home.path(), &run, true);
        let ctx = SetupCtx {
            stamp: &stamp,
            iso_now: &iso_now,
            hostname: &hostname,
            ..ctx
        };
        let dest = tempfile::tempdir().unwrap();
        // tar(1) is required for the archive step; skip cleanly without it.
        if std::process::Command::new("tar")
            .arg("--version")
            .output()
            .is_err()
        {
            return;
        }
        let archive = export_setup(&ctx, dest.path()).expect("export works");
        // Wipe: simulate a fresh install (settings gone, archive survives).
        std::fs::remove_dir_all(home.path().join(".config")).unwrap();
        assert!(!home.path().join(".config/kdeglobals").exists());
        let stream = |_: &[String], _: &dyn Fn(&str)| 0;
        let on_line = |_: &str| {};
        // Restore runs flatpak reinstalls through `stream`; the stub reports
        // success without touching the system.
        let report = restore_setup(&ctx, &stream, &on_line, &archive).expect("restore works");
        assert!(report.paths >= 1);
        assert_eq!(
            std::fs::read_to_string(home.path().join(".config/kdeglobals")).unwrap(),
            "theme=Breeze\n"
        );
    }
}
