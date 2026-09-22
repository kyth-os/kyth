//! Native replacement for the Python `kyth-proton-cachyos-update`
//! launcher.
//!
//! Fetches the latest Proton-CachyOS release, verifies its checksum,
//! extracts it, and prunes old versions. Skipped on live ISOs. Exits `1`
//! with the launcher error lines on failure. `system/updater.py` stays
//! as the Phase 3 fixture.

use std::env;
use std::path::{Path, PathBuf};
use std::time::Duration;

use kyth_shared::system::process::run_bounded;
use kyth_shared::system::release_fetch::{
    download_file, extract_archive, fetch_github_latest_release, find_release_asset,
    github_headers, prune_installations, read_secret_file, release_assets, validate_version,
    verify_checksum_file, TempWorkdir,
};

const REPO: &str = "CachyOS/proton-cachyos";
const VERSION_PATTERN: &str = r"cachyos-[0-9]+\.[0-9]+-[0-9]{8}-slr";

fn run(argv: &[String], timeout_secs: u64) -> Option<(i32, String)> {
    run_bounded(argv, Duration::from_secs(timeout_secs))
        .ok()
        .map(|output| {
            (
                output.status.code().unwrap_or(1),
                String::from_utf8_lossy(&output.stdout).into_owned(),
            )
        })
}

fn fail(message: String) -> ! {
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

fn main() -> std::process::ExitCode {
    if let Ok(cmdline) = std::fs::read_to_string("/proc/cmdline") {
        if cmdline
            .split_whitespace()
            .any(|arg| arg == "kyth.live" || arg == "kyth.live=1")
        {
            println!("Proton-CachyOS update disabled in live ISO environment.");
            return std::process::ExitCode::SUCCESS;
        }
    }
    let install_dir = PathBuf::from("/var/lib/kyth/proton-cachyos");
    println!("Fetching latest Proton-CachyOS release metadata...");
    let secret = read_secret_file(std::path::Path::new("/run/secrets/github_token"));
    let env_token = env::var("GITHUB_TOKEN").ok();
    let headers = github_headers(secret.as_deref(), env_token.as_deref());
    let release = match fetch_github_latest_release(&run, REPO, &headers) {
        Ok(release) => release,
        Err(error) => fail(format!(
            "Failed to fetch Proton-CachyOS release info: {error}"
        )),
    };
    let ver = release
        .get("tag_name")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    if ver.is_empty() {
        fail("Failed to parse Proton-CachyOS version tag from release JSON".to_string());
    }
    if validate_version(ver, VERSION_PATTERN, "Proton-CachyOS").is_err() {
        fail(format!("Unexpected Proton-CachyOS version format: {ver}"));
    }
    let assets = release_assets(&release);
    let tarball = find_release_asset(&assets, |name| name.ends_with("x86_64.tar.xz"));
    let checksum = find_release_asset(&assets, |name| name.ends_with("x86_64.sha512sum"));
    let (Some(tarball), Some(checksum)) = (tarball, checksum) else {
        fail("Failed to locate Proton-CachyOS release assets".to_string());
    };
    let folder = tarball
        .name
        .strip_suffix(".tar.xz")
        .or_else(|| tarball.name.strip_suffix(".xz"))
        .unwrap_or(&tarball.name)
        .to_string();
    // A bare dir check lies after interrupted installs (SIGKILL, power
    // loss, ENOSPC): the folder exists but is incomplete, and every later
    // run would print "already up to date" forever. Only a valid
    // completion marker counts; anything else is re-installed.
    if is_complete_install(&install_dir, &folder, ver) {
        println!("Proton-CachyOS {ver} is already up to date.");
        return std::process::ExitCode::SUCCESS;
    }
    if install_dir.join(&folder).is_dir() {
        println!("Proton-CachyOS {ver} found incomplete — re-installing...");
        std::fs::remove_dir_all(install_dir.join(&folder))
            .unwrap_or_else(|error| fail(format!("Failed to clear incomplete install: {error}")));
    }
    println!("Updating to Proton-CachyOS {ver}...");
    let work = match TempWorkdir::create("kyth-proton") {
        Ok(work) => work,
        Err(error) => fail(format!("Failed to download assets: {error}")),
    };
    let tarball_dest = work.path().join(&tarball.name);
    let sha512_dest = work.path().join(&checksum.name);
    let downloads = [
        (&tarball.url, &tarball_dest, &tarball.name),
        (&checksum.url, &sha512_dest, &checksum.name),
    ];
    for (url, dest, name) in downloads {
        println!("Downloading {name}...");
        if let Err(error) = download_file(&run, url, dest, &headers, 120) {
            fail(format!("Failed to download assets: {error}"));
        }
    }
    println!("Verifying checksum...");
    if let Err(error) = verify_checksum_file(&sha512_dest, &tarball_dest, "sha512") {
        fail(format!("Checksum verification failed: {error}"));
    }
    println!("Extracting to {}...", install_dir.display());
    if let Err(error) = extract_archive(&run, &tarball_dest, &install_dir) {
        // Never leave a partial version dir behind: the bare-dir check
        // above would otherwise declare it "up to date" forever.
        let _ = std::fs::remove_dir_all(install_dir.join(&folder));
        fail(format!("Extraction failed: {error}"));
    }
    // Completion marker (version-stamped): the only thing the up-to-date
    // short-circuit trusts.
    if let Err(error) = std::fs::write(
        install_dir.join(&folder).join(".kyth-complete"),
        format!("{ver}\n"),
    ) {
        let _ = std::fs::remove_dir_all(install_dir.join(&folder));
        fail(format!("Failed to record completed install: {error}"));
    }
    println!(
        "Proton-CachyOS {ver} installed to {}/",
        install_dir.display()
    );
    match prune_installations(&install_dir, "proton-cachyos-*", 2) {
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
