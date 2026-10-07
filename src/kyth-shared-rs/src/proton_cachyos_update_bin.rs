//! Native replacement for the Python `kyth-proton-cachyos-update`
//! launcher.
//!
//! Fetches the latest GE-Proton release, verifies its checksum,
//! extracts it, and prunes old versions. Skipped on live ISOs. Exits `1`
//! with the launcher error lines on failure. `system/updater.py` stays
//! as the Phase 3 fixture.
//!
//! NOTE: the binary keeps its historical `proton_cachyos` name (unit files,
//! ujust recipes, install paths) to avoid churning systemd/CI plumbing;
//! the source of truth is GloriousEggroll/proton-ge-custom.

use std::env;
use std::path::{Path, PathBuf};
use std::time::Duration;

use kyth_shared::system::process::run_bounded;
use kyth_shared::system::release_fetch::{
    download_file, extract_archive, fetch_github_latest_release, find_release_asset,
    github_headers, prune_installations, read_secret_file, release_assets, validate_version,
    verify_checksum_file, TempWorkdir,
};

const REPO: &str = "GloriousEggroll/proton-ge-custom";
const VERSION_PATTERN: &str = r"GE-Proton[0-9]+-[0-9]+";

fn run(argv: &[String], timeout_secs: u64) -> Option<(i32, String)> {
    run_bounded(argv, Duration::from_secs(timeout_secs))
        .ok()
        .map(|output| {
            (
                output.status.code().unwrap_or(1),
                String::from_utf8_lossy(if output.status.success() {
                    &output.stdout
                } else {
                    &output.stderr
                })
                .into_owned(),
            )
        })
}

fn fail(message: String, work: Option<&TempWorkdir>) -> ! {
    // process::exit() skips destructors, so TempWorkdir's Drop never runs:
    // remove the workdir explicitly or every failed update leaks hundreds
    // of MB into /tmp.
    if let Some(work) = work {
        let _ = std::fs::remove_dir_all(work.path());
    }
    eprintln!("{message}");
    std::process::exit(1);
}

/// Only a version-stamped completion marker counts as "up to date" — a
/// bare directory may be an interrupted install.
fn is_complete_install(install_dir: &Path, folder: &str, ver: &str) -> bool {
    std::fs::read_to_string(install_dir.join(folder).join(".kyth-complete"))
        .map(|text| text.trim() == ver)
        .unwrap_or(false)
}

/// Parse a `GE-Proton<major>-<minor>` tag into (major, minor). Returns None
/// if the format does not match.
fn parse_ge_proton_version(ver: &str) -> Option<(u32, u32)> {
    let rest = ver.strip_prefix("GE-Proton")?;
    let (major, minor) = rest.split_once('-')?;
    Some((major.parse().ok()?, minor.parse().ok()?))
}

/// Find the currently installed GE-Proton version by scanning for a
/// version-stamped completion marker. Returns None if nothing is installed.
fn installed_ge_proton_version(install_dir: &Path) -> Option<String> {
    let entries = std::fs::read_dir(install_dir).ok()?;
    for entry in entries.flatten() {
        let folder = entry.file_name().to_string_lossy().into_owned();
        if !folder.starts_with("GE-Proton") {
            continue;
        }
        if let Ok(marker) = std::fs::read_to_string(entry.path().join(".kyth-complete")) {
            let ver = marker.trim().to_string();
            if !ver.is_empty() {
                return Some(ver);
            }
        }
    }
    None
}

/// Merge the installed Proton version into /var/lib/kyth/gaming-versions.json
/// so gaming_versions() resolves at runtime. Best-effort: a failure here
/// must not fail the install.
fn refresh_gaming_versions_cache(ver: &str) {
    let cache = Path::new("/var/lib/kyth/gaming-versions.json");
    let mut map: serde_json::Map<String, serde_json::Value> = std::fs::read_to_string(cache)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default();
    map.insert(
        "proton_cachyos_version".to_string(),
        serde_json::Value::String(ver.to_string()),
    );
    // Ensure the parent exists (unit's StateDirectory normally does this).
    if let Some(parent) = cache.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    match std::fs::write(cache, serde_json::to_string(&map).unwrap_or_default()) {
        Ok(()) => println!("Updated gaming versions cache: {ver}"),
        Err(error) => eprintln!("Failed to update gaming versions cache: {error}"),
    }
}

fn main() -> std::process::ExitCode {
    if let Ok(cmdline) = std::fs::read_to_string("/proc/cmdline") {
        if cmdline
            .split_whitespace()
            .any(|arg| arg == "kyth.live" || arg == "kyth.live=1")
        {
            println!("GE-Proton update disabled in live ISO environment.");
            return std::process::ExitCode::SUCCESS;
        }
    }
    let install_dir = PathBuf::from("/var/lib/kyth/proton-cachyos");
    println!("Fetching latest GE-Proton release metadata...");
    let secret = read_secret_file(std::path::Path::new("/run/secrets/github_token"));
    let env_token = env::var("GITHUB_TOKEN").ok();
    let headers = github_headers(secret.as_deref(), env_token.as_deref());
    let release = match fetch_github_latest_release(&run, REPO, &headers) {
        Ok(release) => release,
        Err(error) => fail(
            format!("Failed to fetch GE-Proton release info: {error}"),
            None,
        ),
    };
    let ver = release
        .get("tag_name")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    if ver.is_empty() {
        fail(
            "Failed to parse GE-Proton version tag from release JSON".to_string(),
            None,
        );
    }
    if validate_version(ver, VERSION_PATTERN, "GE-Proton").is_err() {
        fail(format!("Unexpected GE-Proton version format: {ver}"), None);
    }
    // Version-jump detection (log-and-hold): the checksum sidecar comes from
    // the same release as the tarball, so it only proves transport integrity.
    // A compromised upstream release (or a moved `latest` pointer) ships a
    // matching checksum for a trojaned Proton. Refuse downgrades and hold on
    // suspicious jumps until a human clears the hold.
    if let Some(installed) = installed_ge_proton_version(&install_dir) {
        if let (Some((new_major, new_minor)), Some((old_major, old_minor))) = (
            parse_ge_proton_version(ver),
            parse_ge_proton_version(&installed),
        ) {
            if (new_major, new_minor) < (old_major, old_minor) {
                fail(
                    format!(
                        "GE-Proton version {ver} is older than installed {installed} — refusing downgrade (possible release-pointer attack). Clear manually if intentional."
                    ),
                    None,
                );
            }
            let major_jump = new_major.saturating_sub(old_major);
            let minor_jump = new_minor.saturating_sub(old_minor);
            if major_jump > 1 || (major_jump == 0 && minor_jump > 5) {
                eprintln!(
                    "WARNING: GE-Proton version jump {installed} -> {ver} looks suspicious — holding update for manual review."
                );
                return std::process::ExitCode::SUCCESS;
            }
        }
    }
    let assets = release_assets(&release);
    let tarball = find_release_asset(&assets, |name| name.ends_with("x86_64.tar.gz"));
    let checksum = find_release_asset(&assets, |name| name.ends_with("x86_64.sha512sum"));
    let (Some(tarball), Some(checksum)) = (tarball, checksum) else {
        fail(
            "Failed to locate GE-Proton release assets".to_string(),
            None,
        );
    };
    let folder = tarball
        .name
        .strip_suffix(".tar.gz")
        .unwrap_or(&tarball.name)
        .to_string();
    // A bare dir check lies after interrupted installs (SIGKILL, power
    // loss, ENOSPC): the folder exists but is incomplete, and every later
    // run would print "already up to date" forever. Only a valid
    // completion marker counts; anything else is re-installed.
    if is_complete_install(&install_dir, &folder, ver) {
        println!("GE-Proton {ver} is already up to date.");
        return std::process::ExitCode::SUCCESS;
    }
    if install_dir.join(&folder).is_dir() {
        println!("GE-Proton {ver} found incomplete — re-installing...");
        std::fs::remove_dir_all(install_dir.join(&folder)).unwrap_or_else(|error| {
            fail(format!("Failed to clear incomplete install: {error}"), None)
        });
    }
    println!("Updating to GE-Proton {ver}...");
    let work = match TempWorkdir::create("kyth-proton") {
        Ok(work) => work,
        Err(error) => fail(format!("Failed to download assets: {error}"), None),
    };
    let tarball_dest = work.path().join(&tarball.name);
    let sha512_dest = work.path().join(&checksum.name);
    let downloads = [
        (&tarball.url, &tarball_dest, &tarball.name),
        (&checksum.url, &sha512_dest, &checksum.name),
    ];
    for (url, dest, name) in downloads {
        println!("Downloading {name}...");
        let limit = if dest == &tarball_dest {
            kyth_shared::system::release_fetch::MAX_ARCHIVE_BYTES
        } else {
            kyth_shared::system::release_fetch::MAX_CHECKSUM_BYTES
        };
        if let Err(error) = download_file(&run, url, dest, &headers, 120, limit) {
            fail(format!("Failed to download assets: {error}"), Some(&work));
        }
    }
    println!("Verifying checksum...");
    if let Err(error) = verify_checksum_file(&sha512_dest, &tarball_dest, "sha512") {
        fail(
            format!("Checksum verification failed: {error}"),
            Some(&work),
        );
    }
    println!("Extracting to {}...", install_dir.display());
    if let Err(error) = extract_archive(&run, &tarball_dest, &install_dir) {
        // Never leave a partial version dir behind: the bare-dir check
        // above would otherwise declare it "up to date" forever.
        let _ = std::fs::remove_dir_all(install_dir.join(&folder));
        fail(format!("Extraction failed: {error}"), Some(&work));
    }
    // Completion marker (version-stamped): the only thing the up-to-date
    // short-circuit trusts.
    if let Err(error) = std::fs::write(
        install_dir.join(&folder).join(".kyth-complete"),
        format!("{ver}\n"),
    ) {
        let _ = std::fs::remove_dir_all(install_dir.join(&folder));
        fail(
            format!("Failed to record completed install: {error}"),
            Some(&work),
        );
    }
    println!("GE-Proton {ver} installed to {}/", install_dir.display());
    // Publish the installed version where the runtime resolver looks.
    // gaming_versions() reads /var/lib/kyth/gaming-versions.json as its
    // writable fallback (the build-time /usr/share/kyth/config copy is
    // immutable). Merge with any existing file so we don't clobber umu.
    refresh_gaming_versions_cache(ver);
    // One-time migration: drop legacy Proton-CachyOS installs left behind by
    // the pre-GE-Proton updater. No-op once the directory is clean.
    match prune_installations(&install_dir, "proton-cachyos-*", 0) {
        Ok(removed) => {
            for old in &removed {
                if let Some(name) = old.file_name().map(|name| name.to_string_lossy()) {
                    println!("Removing legacy Proton-CachyOS version: {name}");
                }
            }
        }
        Err(error) => eprintln!("Failed to prune legacy Proton-CachyOS versions: {error}"),
    }
    match prune_installations(&install_dir, "GE-Proton*", 2) {
        Ok(removed) => {
            for old in &removed {
                if let Some(name) = old.file_name().map(|name| name.to_string_lossy()) {
                    println!("Removing old version: {name}");
                }
            }
        }
        Err(error) => eprintln!("Failed to prune old versions: {error}"),
    }
    std::process::ExitCode::SUCCESS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn complete_marker_gates_up_to_date() {
        let dir = tempfile::tempdir().unwrap();
        let folder = "proton-cachyos-test";
        std::fs::create_dir_all(dir.path().join(folder)).unwrap();
        // Bare dir, no marker: incomplete.
        assert!(!is_complete_install(dir.path(), folder, "cachyos-1-slr"));
        // Wrong-version marker: incomplete.
        std::fs::write(
            dir.path().join(folder).join(".kyth-complete"),
            "cachyos-0-slr\n",
        )
        .unwrap();
        assert!(!is_complete_install(dir.path(), folder, "cachyos-1-slr"));
        // Matching marker: complete.
        std::fs::write(
            dir.path().join(folder).join(".kyth-complete"),
            "cachyos-1-slr\n",
        )
        .unwrap();
        assert!(is_complete_install(dir.path(), folder, "cachyos-1-slr"));
    }
}
