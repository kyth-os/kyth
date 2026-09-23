//! Native replacement for the Python `kyth-rclone-update` launcher.
//!
//! Installs or updates the rclone binary from official releases with
//! SHA256 verification. `RCLONE_VERSION` overrides the live tag lookup.
//! Exits `1` with the launcher error lines on failure.
//! `system/updater.py` stays as the Phase 3 fixture.

use std::env;
use std::path::{Path, PathBuf};
use std::time::Duration;

use kyth_shared::system::process::run_bounded;
use kyth_shared::system::release_fetch::{
    download_file, extract_archive, fetch_github_latest_release, github_headers, read_secret_file,
    validate_version, verify_checksum_file, TempWorkdir,
};

const REPO: &str = "rclone/rclone";
const VERSION_PATTERN: &str = r"v[0-9]+\.[0-9]+\.[0-9]+";
const RCLONE_BIN: &str = "/usr/local/bin/rclone";

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

#[cfg(unix)]
fn set_executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755));
}

#[cfg(not(unix))]
fn set_executable(_path: &Path) {}

fn installed_version() -> Option<String> {
    if !Path::new(RCLONE_BIN).is_file() {
        return None;
    }
    let (_, stdout) = run(&[RCLONE_BIN.to_string(), "--version".to_string()], 30)?;
    let mut parts = stdout.lines().next()?.split_whitespace();
    if parts.next()? != "rclone" {
        return None;
    }
    let tagged = parts.next()?;
    if !tagged.starts_with('v') {
        return None;
    }
    Some(tagged.trim_start_matches('v').to_string())
}

fn main() -> std::process::ExitCode {
    let mut rclone_ver = env::var("RCLONE_VERSION").unwrap_or_default();
    if rclone_ver.is_empty() {
        println!("Fetching latest rclone release metadata...");
        let secret = read_secret_file(Path::new("/run/secrets/github_token"));
        let env_token = env::var("GITHUB_TOKEN").ok();
        let headers = github_headers(secret.as_deref(), env_token.as_deref());
        match fetch_github_latest_release(&run, REPO, &headers) {
            Ok(release) => {
                rclone_ver = release
                    .get("tag_name")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or("")
                    .to_string();
            }
            Err(error) => fail(format!(
                "ERROR: Could not determine latest rclone release tag: {error}"
            )),
        }
    }
    if rclone_ver.is_empty() {
        fail("ERROR: Could not determine latest rclone release tag".to_string());
    }
    if validate_version(&rclone_ver, VERSION_PATTERN, "rclone").is_err() {
        fail(format!(
            "ERROR: Unexpected rclone version format: {rclone_ver}"
        ));
    }
    let target_ver = rclone_ver.trim_start_matches('v').to_string();
    if let Some(installed) = installed_version() {
        if installed == target_ver {
            println!("rclone already current: v{installed}");
            return std::process::ExitCode::SUCCESS;
        }
    }
    let basename = format!("rclone-{rclone_ver}-linux-amd64");
    let zip_name = format!("{basename}.zip");
    let base_url = format!("https://downloads.rclone.org/{rclone_ver}");
    let work = match TempWorkdir::create("kyth-rclone") {
        Ok(work) => work,
        Err(error) => fail(format!("ERROR: Failed to download rclone assets: {error}")),
    };
    let headers = std::collections::BTreeMap::new();
    let zip_dest = work.path().join(&zip_name);
    let sums_dest = work.path().join("SHA256SUMS");
    let sums_name = "SHA256SUMS".to_string();
    for (file, dest) in [(&zip_name, &zip_dest), (&sums_name, &sums_dest)] {
        println!("rclone: downloading {file}...");
        if let Err(error) = download_file(&run, &format!("{base_url}/{file}"), dest, &headers, 120)
        {
            fail(format!("ERROR: Failed to download rclone assets: {error}"));
        }
    }
    println!("Verifying checksum...");
    if let Err(error) = verify_checksum_file(&sums_dest, &zip_dest, "sha256") {
        fail(format!("ERROR: Checksum verification failed: {error}"));
    }
    println!("Extracting archive...");
    if let Err(error) = extract_archive(&run, &zip_dest, work.path()) {
        fail(format!("ERROR: Extraction failed: {error}"));
    }
    let mut extracted = work.path().join(&basename).join("rclone");
    if !extracted.is_file() {
        extracted = work.path().join("rclone");
    }
    let target = PathBuf::from(RCLONE_BIN);
    if let Some(parent) = target.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    // Same-dir temp + fsync + atomic rename: copying directly over the live
    // binary truncates it in place — a concurrent exec runs partial bytes
    // and a power loss leaves a corrupt /usr/local/bin/rclone.
    let staging = target.with_extension("new");
    if let Err(error) = (|| -> Result<(), String> {
        std::fs::copy(&extracted, &staging)
            .map_err(|error| format!("copy to staging failed: {error}"))?;
        set_executable(&staging);
        {
            let file = std::fs::OpenOptions::new()
                .read(true)
                .open(&staging)
                .map_err(|error| format!("fsync staging failed: {error}"))?;
            file.sync_all()
                .map_err(|error| format!("fsync staging failed: {error}"))?;
        }
        std::fs::rename(&staging, &target)
            .map_err(|error| format!("atomic replace failed: {error}"))?;
        Ok(())
    })() {
        let _ = std::fs::remove_file(&staging);
        fail(format!(
            "ERROR: Failed to install rclone binary to {}: {error}",
            target.display()
        ));
    }
    // Verify the installed binary reports the target version — a short or
    // corrupt write must fail loudly, never print "installed".
    match run(&[RCLONE_BIN.to_string(), "--version".to_string()], 30) {
        Some((0, stdout)) => {
            let first = stdout.lines().next().unwrap_or("");
            println!("rclone installed: {first}");
            if !first.contains(rclone_ver.as_str()) {
                fail(format!(
                    "ERROR: installed rclone version mismatch (expected {rclone_ver}, got {first})"
                ));
            }
        }
        Some((code, _)) => {
            fail(format!(
                "ERROR: installed rclone failed its version check (exit {code})"
            ));
        }
        None => {
            fail("ERROR: installed rclone could not be executed".to_string());
        }
    }
    std::process::ExitCode::SUCCESS
}

#[cfg(test)]
mod tests {
    /// The installed binary must report the target version: first line of
    /// `rclone --version` contains the version string.
    fn version_line_matches(first_line: &str, target: &str) -> bool {
        first_line.contains(target)
    }

    #[test]
    fn version_gate_accepts_match_and_rejects_mismatch() {
        assert!(version_line_matches("rclone v1.66.0", "v1.66.0"));
        assert!(!version_line_matches("rclone v1.65.0", "v1.66.0"));
        assert!(!version_line_matches("", "v1.66.0"));
    }
}
