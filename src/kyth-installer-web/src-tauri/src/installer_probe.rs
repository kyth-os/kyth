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
}
