//! Typed execution of the alongside-installation `@home` configuration.

use serde::Deserialize;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Deserialize, serde::Serialize)]
pub(crate) struct AlongsideHomeInput {
    pub config_root: String,
    pub target_device: String,
    pub fstab_path: String,
}

#[derive(Debug, serde::Serialize)]
pub(crate) struct AlongsideHomeResult {
    pub mounted: bool,
    pub fstab_written: bool,
}

fn safe_path(raw: &str, label: &str) -> Result<PathBuf, String> {
    let value = raw.trim();
    if value.is_empty()
        || !value.starts_with('/')
        || value.contains("..")
        || value.contains("//")
        || !value.bytes().all(|b| {
            b.is_ascii_alphanumeric() || matches!(b, b'/' | b'.' | b'_' | b'+' | b':' | b'-')
        })
    {
        return Err(format!("{label} must be an absolute safe path"));
    }
    Ok(PathBuf::from(value))
}

/// Device validation reuses the shared installer device gate
/// (`installer_plan::normalize_device_path`): the local check used to accept
/// arbitrarily nested `/dev/foo/bar` paths.
fn safe_device(raw: &str) -> Result<String, String> {
    crate::installer_plan::normalize_device_path(raw)
        .ok_or_else(|| "target device must be a safe /dev path".into())
}

pub(crate) fn validate(input: &AlongsideHomeInput) -> Result<(PathBuf, String, PathBuf), String> {
    let root = safe_path(&input.config_root, "config root")?;
    let device = safe_device(&input.target_device)?;
    let fstab = safe_path(&input.fstab_path, "fstab path")?;
    // `Path::ends_with` compares path components and treats a leading `/` in
    // the argument as an anchored path.  That makes a perfectly valid
    // `/mnt/target/etc/fstab` fail the check.  Validate the installed fstab
    // shape component-wise instead, without weakening the absolute-path
    // checks above.
    if fstab.file_name().and_then(|name| name.to_str()) != Some("fstab")
        || fstab
            .parent()
            .and_then(|parent| parent.file_name())
            .and_then(|name| name.to_str())
            != Some("etc")
    {
        return Err("fstab path must point to installed /etc/fstab".into());
    }
    Ok((root, device, fstab))
}

pub(crate) fn apply(input: AlongsideHomeInput) -> Result<AlongsideHomeResult, String> {
    let (root, device, fstab) = validate(&input)?;
    let home = root.join("ostree/deploy/default/var/home");
    if let Ok(metadata) = fs::symlink_metadata(&home) {
        if metadata.file_type().is_symlink() {
            return Err("alongside home path is a symlink".into());
        }
    }
    fs::create_dir_all(&home)
        .map_err(|e| format!("could not create alongside home mountpoint: {e}"))?;
    let _ = Command::new("/usr/bin/umount")
        .args(["-R", "-l"])
        .arg(&home)
        .status();
    let mounted = Command::new("/usr/bin/mount")
        .args(["-o", "subvol=@home"])
        .arg(&device)
        .arg(&home)
        .status()
        .map_err(|e| format!("could not mount alongside home: {e}"))?;
    if !mounted.success() {
        return Err("could not mount alongside home".into());
    }
    let uuid =
        match crate::installer_probe::lookup_uuid(crate::installer_probe::UuidInput { device }) {
            Ok(uuid) => uuid,
            Err(error) => {
                detach_home(&home);
                return Err(error);
            }
        };
    let line = format!("UUID={uuid} /var/home btrfs subvol=@home,compress=zstd:1 0 0\n");
    persist_home_fstab(&fstab, line, || detach_home(&home))
}

fn detach_home(home: &Path) {
    let _ = Command::new("/usr/bin/umount")
        .args(["-R", "-l"])
        .arg(home)
        .status();
}

/// Persist the `@home` fstab row. A failed write is an error, never a
/// `fstab_written:false` success: the caller only checks the helper's exit
/// status, so a swallowed failure shipped a system whose /var/home silently
/// lived inside `@`. The mount is detached so nothing is left behind.
fn persist_home_fstab(
    fstab: &Path,
    line: String,
    detach: impl FnOnce(),
) -> Result<AlongsideHomeResult, String> {
    match crate::installer_configuration::append_fstab(
        crate::installer_configuration::FstabAppendInput {
            path: fstab.to_string_lossy().into_owned(),
            line,
        },
    ) {
        Ok(()) => Ok(AlongsideHomeResult {
            mounted: true,
            fstab_written: true,
        }),
        Err(error) => {
            detach();
            Err(format!("could not write the @home fstab entry: {error}"))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn validates_fixed_alongside_paths() {
        let input = AlongsideHomeInput {
            config_root: "/mnt/target".into(),
            target_device: "/dev/sda3".into(),
            fstab_path: "/mnt/target/etc/fstab".into(),
        };
        let (root, device, fstab) = validate(&input).unwrap();
        assert_eq!(root, Path::new("/mnt/target"));
        assert_eq!(device, "/dev/sda3");
        assert_eq!(fstab, Path::new("/mnt/target/etc/fstab"));
    }
    #[test]
    fn failed_home_fstab_write_is_an_error_and_detaches_the_mount() {
        let dir = tempfile::tempdir().unwrap();
        // The parent directory does not exist, so the append cannot succeed.
        let fstab = dir.path().join("missing/etc/fstab");
        let mut detached = false;
        let result = persist_home_fstab(
            &fstab,
            "UUID=abcd /var/home btrfs subvol=@home 0 0\n".into(),
            || detached = true,
        );
        assert!(result.unwrap_err().contains("@home fstab entry"));
        assert!(detached);
    }

    #[test]
    fn successful_home_fstab_write_reports_written() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("etc")).unwrap();
        let fstab = dir.path().join("etc/fstab");
        let result = persist_home_fstab(
            &fstab,
            "UUID=abcd /var/home btrfs subvol=@home 0 0\n".into(),
            || panic!("must not detach on success"),
        )
        .unwrap();
        assert!(result.fstab_written);
    }

    #[test]
    fn rejects_unsafe_alongside_inputs() {
        for target_device in [
            "/dev/sda;id",
            // The old local gate accepted arbitrarily nested device paths.
            "/dev/foo/bar",
            "/dev/../etc",
            "/dev/",
        ] {
            let base = AlongsideHomeInput {
                config_root: "/mnt/target".into(),
                target_device: target_device.into(),
                fstab_path: "/mnt/target/etc/fstab".into(),
            };
            assert!(validate(&base).is_err(), "{target_device} must be rejected");
        }
    }
}
