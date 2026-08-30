//! Pure Plymouth policy and initramfs inspection helpers.
//!
//! The Python Plymouth module still owns filesystem mutation and `dracut`
//! execution. This module keeps deterministic inputs and inspection rules
//! reusable by Rust callers without starting privileged processes.

use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

pub const THEME: &str = "kyth";
pub const FALLBACK_THEMES: &[&str] = &["bgrt-fedora", "bgrt", "spinner"];
pub const REQUIRED_ENTRIES: &[&str] = &[
    "usr/share/plymouth/themes/kyth/kyth.plymouth",
    "usr/share/plymouth/themes/kyth/kyth.script",
    "usr/share/plymouth/themes/kyth/kyth-logo.png",
    "usr/share/plymouth/themes/default.plymouth",
];
pub const PLYMOUTH_CONFIG: &str =
    "[Daemon]\nTheme=kyth\nShowDelay=0\nDeviceTimeout=8\nUseFirmwareBackground=false\n";

/// Return the stable Plymouth fingerprint used to decide whether a refresh is
/// needed. Missing files are represented explicitly.
pub fn fingerprint(paths: &[&Path]) -> String {
    let mut digest = Sha256::new();
    for path in paths {
        match std::fs::read(path) {
            Ok(content) => {
                let item = Sha256::digest(content);
                digest.update(format!("{:x}  {}\n", item, path.display()).as_bytes());
            }
            Err(_) => digest.update(format!("MISSING  {}\n", path.display()).as_bytes()),
        }
    }
    format!("{:x}", digest.finalize())
}

fn kernel_name(path: &Path) -> Option<&str> {
    path.file_name()?.to_str()?.strip_prefix("initramfs-")?.strip_suffix(".img")
}

/// Find initramfs images that have a matching kernel module directory.
pub fn collect_images(boot: &Path, modules: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(entries) = std::fs::read_dir(boot) {
        candidates.extend(entries.filter_map(Result::ok).map(|entry| entry.path()));
    }
    let ostree = boot.join("ostree");
    if let Ok(revisions) = std::fs::read_dir(ostree) {
        for revision in revisions.filter_map(Result::ok) {
            if let Ok(entries) = std::fs::read_dir(revision.path()) {
                candidates.extend(entries.filter_map(Result::ok).map(|entry| entry.path()));
            }
        }
    }
    candidates.sort();
    candidates.dedup();
    candidates
        .into_iter()
        .filter(|path| path.is_file() && kernel_name(path).is_some_and(|kernel| modules.join(kernel).is_dir()))
        .collect()
}

/// Inspect already-collected `lsinitrd` output. Process execution is kept
/// outside the shared crate; callers provide command output and optional file
/// contents from their bounded runner.
pub fn inspect_listing(
    image: &Path,
    listing: &str,
    defaults: Option<&str>,
    logo: Option<&[u8]>,
    watermark: Option<&[u8]>,
) -> Vec<String> {
    let mut errors = Vec::new();
    for entry in REQUIRED_ENTRIES {
        if !listing.contains(entry) {
            errors.push(format!("refreshed initramfs is missing {entry}: {}", image.display()));
        }
    }
    if FALLBACK_THEMES
        .iter()
        .any(|theme| listing.contains(&format!("usr/share/plymouth/themes/{theme}/")))
    {
        errors.push(format!(
            "Plymouth fallback theme leaked into refreshed initramfs: {}",
            image.display()
        ));
    }
    match defaults {
        Some(defaults) => {
            for setting in ["Theme=kyth", "ShowDelay=0", "DeviceTimeout=8"] {
                if !defaults.lines().any(|line| line == setting) {
                    errors.push(format!(
                        "refreshed initramfs Plymouth defaults are missing {setting}: {}",
                        image.display()
                    ));
                }
            }
        }
        None => errors.push(format!(
            "refreshed initramfs is missing Plymouth defaults: {}",
            image.display()
        )),
    }
    if let Some(logo) = logo {
        match watermark {
            Some(watermark) if logo != watermark => errors.push(format!(
                "refreshed initramfs contains the wrong Plymouth system logo: {}",
                image.display()
            )),
            None => errors.push("transparent Plymouth watermark is unavailable".into()),
            _ => {}
        }
    } else {
        errors.push(format!(
            "refreshed initramfs is missing transparent Plymouth system logo: {}",
            image.display()
        ));
    }
    errors
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn fingerprint_changes_for_content_and_missing_files() {
        let directory = tempdir().unwrap();
        let present = directory.path().join("present");
        let missing = directory.path().join("missing");
        std::fs::write(&present, b"one").unwrap();
        let first = fingerprint(&[present.as_path(), missing.as_path()]);
        std::fs::write(&present, b"two").unwrap();
        let second = fingerprint(&[present.as_path(), missing.as_path()]);
        assert_ne!(first, second);
    }

    #[test]
    fn image_collection_is_filtered_and_sorted() {
        let directory = tempdir().unwrap();
        let boot = directory.path().join("boot");
        let modules = directory.path().join("modules");
        std::fs::create_dir_all(boot.join("ostree/rev")).unwrap();
        std::fs::create_dir_all(modules.join("6.1")).unwrap();
        std::fs::write(boot.join("initramfs-6.1.img"), b"").unwrap();
        std::fs::write(boot.join("initramfs-no-module.img"), b"").unwrap();
        std::fs::write(boot.join("ostree/rev/initramfs-6.1.img"), b"").unwrap();
        assert_eq!(collect_images(&boot, &modules).len(), 2);
    }

    #[test]
    fn listing_inspection_reports_missing_entries_and_fallbacks() {
        let image = Path::new("/boot/initramfs-6.1.img");
        let errors = inspect_listing(image, "usr/share/plymouth/themes/spinner/", None, None, None);
        assert!(errors.iter().any(|error| error.contains("fallback theme")));
        assert!(errors.iter().any(|error| error.contains("Plymouth defaults")));
        assert!(errors.iter().any(|error| error.contains("system logo")));
    }
}
