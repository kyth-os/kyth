//! Fixed read-only probes used by the privileged installer executor.

use serde::Deserialize;
use std::process::Command;

#[derive(Debug, Deserialize)]
pub(crate) struct UuidInput {
    pub device: String,
}

fn device_path(raw: &str) -> Result<String, String> {
    let value = raw.trim();
    if !value.starts_with("/dev/")
        || value.len() <= 5
        || value.contains("..")
        || value.contains("//")
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'/' | b'_' | b'-' | b'.'))
    {
        return Err("UUID probe device must be a safe /dev path".into());
    }
    Ok(value.to_string())
}

pub(crate) fn uuid_argv(input: &UuidInput) -> Result<Vec<String>, String> {
    Ok(vec![
        "/usr/bin/blkid".into(),
        "-s".into(),
        "UUID".into(),
        "-o".into(),
        "value".into(),
        device_path(&input.device)?,
    ])
}

/// lsblk columns shared with the Python compatibility path.
///
/// `kyth_installer.disk._query.list_partitions` reads this same projection;
/// both consumers derive ESP / Windows-indicator / BitLocker state from
/// identical snapshot fields, so the typed Rust preflight and the Python
/// path share one detection source.
pub(crate) const STORAGE_PROBE_COLUMNS: &str =
    "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,PARTN,LABEL,MOUNTPOINT,MOUNTPOINTS,START,RO";

pub(crate) fn storage_probe_argv(disk: Option<&str>) -> Result<Vec<String>, String> {
    let mut argv = vec![
        "/usr/bin/lsblk".into(),
        "--json".into(),
        "--bytes".into(),
        "--paths".into(),
        "--output".into(),
        STORAGE_PROBE_COLUMNS.into(),
    ];
    if let Some(disk) = disk {
        argv.push(device_path(disk)?);
    }
    Ok(argv)
}

/// Fixed blkid probe for BitLocker `TYPE` detection.
///
/// This is the same `blkid -o value -s TYPE <partition>` invocation the
/// Python `_encryption_check` compat path uses: both read the same
/// kernel-visible filesystem type as the single detection source.
pub(crate) fn bitlocker_probe_argv(device: &str) -> Result<Vec<String>, String> {
    Ok(vec![
        "/usr/bin/blkid".into(),
        "-o".into(),
        "value".into(),
        "-s".into(),
        "TYPE".into(),
        device_path(device)?,
    ])
}

pub(crate) fn lookup_uuid(input: UuidInput) -> Result<String, String> {
    let argv = uuid_argv(&input)?;
    let output = Command::new(&argv[0])
        .args(&argv[1..])
        .output()
        .map_err(|error| format!("could not probe filesystem UUID: {error}"))?;
    if !output.status.success() {
        return Err("filesystem UUID probe failed".into());
    }
    let uuid = String::from_utf8(output.stdout)
        .map_err(|_| "filesystem UUID was not UTF-8".to_string())?;
    let uuid = uuid.trim();
    if uuid.is_empty()
        || uuid.len() > 128
        || !uuid.bytes().all(|b| b.is_ascii_hexdigit() || b == b'-')
    {
        return Err("filesystem UUID probe returned an invalid value".into());
    }
    Ok(uuid.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn builds_fixed_uuid_probe() {
        assert_eq!(
            uuid_argv(&UuidInput {
                device: "/dev/sda3".into()
            })
            .unwrap(),
            vec!["/usr/bin/blkid", "-s", "UUID", "-o", "value", "/dev/sda3"]
        );
    }
    #[test]
    fn rejects_unsafe_devices() {
        for device in ["sda3", "/dev/../etc/passwd", "/dev/sda;id", "/dev//sda3"] {
            assert!(uuid_argv(&UuidInput {
                device: device.into()
            })
            .is_err());
        }
    }

    #[test]
    fn storage_probe_argv_pins_shared_lsblk_projection() {
        // Must stay identical to kyth_installer.disk._query.list_partitions'
        // columns: the typed preflight and the Python path share one
        // detection source.
        assert!(STORAGE_PROBE_COLUMNS.contains("FSTYPE"));
        assert!(STORAGE_PROBE_COLUMNS.contains("PARTTYPE"));
        assert!(STORAGE_PROBE_COLUMNS.contains("LABEL"));
        assert!(STORAGE_PROBE_COLUMNS.contains("MOUNTPOINTS"));
        let argv = storage_probe_argv(Some("/dev/sda")).unwrap();
        assert_eq!(
            argv,
            vec![
                "/usr/bin/lsblk",
                "--json",
                "--bytes",
                "--paths",
                "--output",
                STORAGE_PROBE_COLUMNS,
                "/dev/sda"
            ]
        );
        assert_eq!(storage_probe_argv(None).unwrap().len(), 6);
        assert!(storage_probe_argv(Some("/dev/../etc/passwd")).is_err());
    }

    #[test]
    fn bitlocker_probe_argv_matches_python_compat_invocation() {
        assert_eq!(
            bitlocker_probe_argv("/dev/sda2").unwrap(),
            vec!["/usr/bin/blkid", "-o", "value", "-s", "TYPE", "/dev/sda2"]
        );
        assert!(bitlocker_probe_argv("sda2").is_err());
    }
}
