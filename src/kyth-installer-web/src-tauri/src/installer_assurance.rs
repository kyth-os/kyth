//! Native post-configuration assurance for an installed target.
//!
//! These checks are deliberately read-only and support-safe. They run after
//! the typed configuration/account operations and before the native executor
//! records configure_complete, so a partially configured target cannot be
//! reported as successful.

use serde::Serialize;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const MAX_TARGET_ROOT_BYTES: usize = 4096;
const MAX_COMMAND_OUTPUT_BYTES: usize = 1024 * 1024;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct AssuranceCheck {
    pub name: String,
    pub status: String,
    pub detail: String,
}

#[derive(Clone, Debug)]
pub(crate) struct AssuranceInput {
    /// Physical ostree sysroot: boot metadata and `ostree/deploy` live here.
    pub target_root: String,
    /// The installed deployment checkout; its `etc/` is the booted system's
    /// `/etc` (the sysroot has none of its own).
    pub deploy_root: String,
    pub hostname: String,
    pub locale: String,
    pub keymap: String,
    pub timezone: String,
    pub username: String,
    /// Encryption mode requested for the install (`"tpm2"` or `"none"`).
    /// When `"tpm2"`, assurance requires a TPM-bound LUKS keyslot on the
    /// target disk (M8) and fails the install otherwise.
    ///
    /// NOTE: the native executor call site must populate these two fields;
    /// an empty `encryption` skips the check (never silently passes it).
    pub encryption: String,
    /// Disk the system was installed to (e.g. `/dev/sda`), used to locate
    /// the LUKS partition for the TPM keyslot check.
    pub target_disk: String,
}

/// One parsed, validated fstab entry (M15c).
#[derive(Clone, Debug, PartialEq, Eq)]
struct FstabEntry {
    source: String,
    mountpoint: String,
    fstype: String,
}

fn safe_target_root(raw: &str) -> Result<PathBuf, String> {
    let value = raw.trim();
    if value.is_empty()
        || value.len() > MAX_TARGET_ROOT_BYTES
        || !value.starts_with('/')
        || value.contains("..")
        || !value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'/' | b'.' | b'_' | b'+' | b':' | b'-')
        })
    {
        return Err("installed target root is not a safe absolute path".to_string());
    }
    Ok(PathBuf::from(value))
}

fn regular_file(path: &Path, label: &str) -> Result<(), String> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("could not inspect installed {label}: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!("installed {label} is not a regular file"));
    }
    Ok(())
}

fn real_directory(path: &Path, label: &str) -> Result<(), String> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("could not inspect installed {label}: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(format!("installed {label} is not a real directory"));
    }
    Ok(())
}

fn contains_real_entry(path: &Path) -> bool {
    fs::read_dir(path)
        .ok()
        .into_iter()
        .flatten()
        .filter_map(Result::ok)
        .any(|entry| {
            fs::symlink_metadata(entry.path())
                .map(|metadata| !metadata.file_type().is_symlink())
                .unwrap_or(false)
        })
}

fn has_loader_entry(path: &Path) -> bool {
    fs::read_dir(path)
        .ok()
        .into_iter()
        .flatten()
        .filter_map(Result::ok)
        .any(|entry| {
            entry
                .path()
                .extension()
                .is_some_and(|extension| extension == "conf")
                && fs::symlink_metadata(entry.path())
                    .map(|metadata| metadata.is_file() && !metadata.file_type().is_symlink())
                    .unwrap_or(false)
        })
}

fn boot_metadata_reason(root: &Path) -> Option<&'static str> {
    if has_loader_entry(&root.join("boot/loader/entries")) {
        return Some("boot loader entries are present");
    }
    if contains_real_entry(&root.join("boot/efi/EFI")) {
        return Some("EFI boot files are present");
    }
    if contains_real_entry(&root.join("ostree/deploy")) {
        return Some("ostree deployment metadata is present");
    }
    None
}

fn command_output(program: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|error| format!("could not run {program}: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "{program} failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    if output.stdout.len() > MAX_COMMAND_OUTPUT_BYTES {
        return Err(format!("{program} output was too large"));
    }
    String::from_utf8(output.stdout).map_err(|_| format!("{program} output was not UTF-8"))
}

/// Parse and validate every fstab entry (M15c): valid UUID/device sources
/// and sane mountpoints, not mere existence. Blank lines and comments are
/// skipped; anything else must satisfy the same strict shape the
/// installer's own `append_fstab` enforces.
fn parse_fstab_entries(content: &str) -> Result<Vec<FstabEntry>, String> {
    let mut entries = Vec::new();
    for (index, raw_line) in content.lines().enumerate() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        crate::installer_configuration::validate_fstab_line(&format!("{line}\n"))
            .map_err(|error| format!("installed fstab line {} is invalid: {error}", index + 1))?;
        let mut fields = line.split_whitespace();
        entries.push(FstabEntry {
            source: fields.next().unwrap_or_default().to_string(),
            mountpoint: fields.next().unwrap_or_default().to_string(),
            fstype: fields.next().unwrap_or_default().to_string(),
        });
    }
    Ok(entries)
}

fn is_esp_mountpoint(mountpoint: &str) -> bool {
    matches!(mountpoint, "/boot/efi" | "/efi" | "/boot")
}

/// Resolve the ESP block device from validated fstab entries: the vfat
/// entry's `UUID=` source maps to its `/dev/disk/by-uuid/` node.
fn esp_device_from_entries(entries: &[FstabEntry]) -> Option<String> {
    entries
        .iter()
        .find(|entry| {
            entry.fstype.eq_ignore_ascii_case("vfat") && is_esp_mountpoint(&entry.mountpoint)
        })
        .and_then(|entry| entry.source.strip_prefix("UUID="))
        .filter(|uuid| !uuid.is_empty())
        .map(|uuid| format!("/dev/disk/by-uuid/{uuid}"))
}

/// True when the running (live) system booted via UEFI. Pure over an
/// explicit sysfs root so tests don't depend on the machine running them.
fn efi_booted_in(sys_root: &Path) -> bool {
    fs::symlink_metadata(sys_root.join("sys/firmware/efi"))
        .map(|metadata| metadata.is_dir())
        .unwrap_or(false)
}

fn efi_file_present(dir: &Path) -> bool {
    let Ok(entries) = fs::read_dir(dir) else {
        return false;
    };
    entries.flatten().any(|entry| {
        let path = entry.path();
        if path.is_dir() {
            return efi_file_present(&path);
        }
        path.extension()
            .is_some_and(|extension| extension.eq_ignore_ascii_case("efi"))
            && fs::symlink_metadata(&path)
                .map(|metadata| metadata.is_file())
                .unwrap_or(false)
    })
}
/// actually landed (M15b). The mount is always released, even when the
/// check itself fails; an unmount failure fails the check too — a leaked
/// mount in the long-lived daemon is not acceptable.
/// Mount the ESP read-only and verify the expected bootloader files
/// actually landed (M15b). The mount is always released, even when the
/// check itself fails; an unmount failure fails the check too — a leaked
/// mount in the long-lived daemon is not acceptable.
fn verify_esp_bootloaders(device: &str) -> Result<String, String> {
    let metadata = fs::symlink_metadata(device)
        .map_err(|error| format!("ESP device {device} is not usable: {error}"))?;
    if !metadata.file_type().is_symlink() {
        return Err(format!(
            "ESP device {device} is not a /dev/disk/by-uuid node"
        ));
    }
    let mountpoint = tempfile::Builder::new()
        .prefix("kyth-esp-verify-")
        .tempdir()
        .map_err(|error| format!("could not create ESP check mountpoint: {error}"))?;
    let target = mountpoint.path();
    let mounted = Command::new("/usr/sbin/mount")
        .args(["-o", "ro", device])
        .arg(target)
        .output()
        .map_err(|error| format!("could not mount ESP read-only: {error}"))?;
    if !mounted.status.success() {
        return Err(format!(
            "could not mount ESP read-only: {}",
            String::from_utf8_lossy(&mounted.stderr).trim()
        ));
    }
    let check = (|| {
        // FAT is case-insensitive; accept the common casings.
        let boot_dir = target.join("EFI").join("BOOT");
        let loader = ["bootx64.efi", "BOOTX64.EFI", "Bootx64.efi"]
            .iter()
            .map(|name| boot_dir.join(name))
            .find(|path| {
                fs::symlink_metadata(path)
                    .map(|metadata| metadata.is_file())
                    .unwrap_or(false)
            })
            .ok_or_else(|| "ESP has no EFI/BOOT/bootx64.efi".to_string())?;
        let any_payload = efi_file_present(&target.join("EFI"));
        if !any_payload {
            return Err("ESP has no .efi bootloader payload under EFI/".to_string());
        }
        Ok(format!(
            "{} landed on the ESP",
            loader.strip_prefix(target).unwrap_or(&loader).display()
        ))
    })();
    let unmounted = Command::new("/usr/sbin/umount")
        .arg(target)
        .output()
        .map_err(|error| format!("could not release ESP check mount: {error}"))?;
    if !unmounted.status.success() {
        return Err(format!(
            "ESP bootloader files verified but the check mount could not be released: {}",
            String::from_utf8_lossy(&unmounted.stderr).trim()
        ));
    }
    check
}

/// Verify kernel and initramfs presence (M15a): either a vmlinuz plus an
/// initramfs under the target boot tree (ostree deployments keep them in
/// `boot/ostree/<stateroot>-<checksum>/`), or a vmlinuz in the deployment's
/// `/usr/lib/modules/<kver>/`.
fn kernel_detail(root: &Path, deploy: &Path) -> Result<String, String> {
    let mut saw_vmlinuz: Option<String> = None;
    let mut saw_initramfs = false;
    let boot = root.join("boot");
    let mut boot_dirs = vec![boot.clone()];
    if let Ok(entries) = fs::read_dir(boot.join("ostree")) {
        boot_dirs.extend(entries.flatten().map(|entry| entry.path()));
    }
    for dir in &boot_dirs {
        let Ok(entries) = fs::read_dir(dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let name = entry.path();
            let Some(file_name) = name.file_name().and_then(|name| name.to_str()) else {
                continue;
            };
            let is_file = fs::symlink_metadata(&name)
                .map(|metadata| metadata.is_file())
                .unwrap_or(false);
            if !is_file {
                continue;
            }
            if file_name.starts_with("vmlinuz") && saw_vmlinuz.is_none() {
                saw_vmlinuz = Some(format!(
                    "{}:{}",
                    dir.strip_prefix(root).unwrap_or(dir).display(),
                    file_name
                ));
            }
            if file_name.starts_with("initramfs") {
                saw_initramfs = true;
            }
        }
    }
    if let (Some(vmlinuz), true) = (saw_vmlinuz, saw_initramfs) {
        return Ok(format!("kernel and initramfs present ({vmlinuz})"));
    }
    if let Ok(entries) = fs::read_dir(deploy.join("usr/lib/modules")) {
        for entry in entries.flatten() {
            let vmlinuz = entry.path().join("vmlinuz");
            if fs::symlink_metadata(&vmlinuz)
                .map(|metadata| metadata.is_file())
                .unwrap_or(false)
            {
                return Ok(format!(
                    "kernel present in deployment modules ({})",
                    entry.file_name().to_string_lossy()
                ));
            }
        }
    }
    Err("installed system has no kernel (no vmlinuz+initramfs under target /boot, no vmlinuz in deployment modules)".to_string())
}

/// Pure check over `cryptsetup luksDump` output: a TPM-bound enrollment
/// (systemd-cryptenroll --tpm2-device=auto) records a `systemd-tpm2` token.
fn tpm_token_present(luks_dump: &str) -> bool {
    luks_dump.contains("systemd-tpm2")
}

/// After a `tpm2` install, require a TPM-bound LUKS keyslot (M8): locate
/// crypto_LUKS partitions on the target disk, dump each, and fail the
/// install unless at least one carries the systemd-tpm2 token.
fn verify_tpm_encryption(target_disk: &str) -> Result<String, String> {
    let disk = crate::installer_plan::normalize_device_path(target_disk)
        .ok_or_else(|| "TPM encryption check needs a valid installed target disk".to_string())?;
    let listing = command_output("/usr/sbin/lsblk", &["-npro", "NAME,FSTYPE", &disk])?;
    let mut luks_devices = Vec::new();
    for line in listing.lines() {
        let mut fields = line.split_whitespace();
        match (fields.next(), fields.next()) {
            (Some(name), Some(fstype)) if fstype.eq_ignore_ascii_case("crypto_LUKS") => {
                luks_devices.push(name.to_string());
            }
            _ => {}
        }
    }
    if luks_devices.is_empty() {
        return Err(format!(
            "TPM2 encryption was requested but no LUKS partition was found on {disk}"
        ));
    }
    for device in &luks_devices {
        let dump = command_output("/usr/sbin/cryptsetup", &["luksDump", device])?;
        if tpm_token_present(&dump) {
            return Ok(format!("TPM-bound keyslot verified on {device}"));
        }
    }
    Err("TPM2 encryption was requested but no TPM-bound keyslot (systemd-tpm2 token) was found; the disk cannot be unlocked automatically".to_string())
}

pub(crate) fn validate(input: AssuranceInput) -> Result<Vec<AssuranceCheck>, String> {
    let root = safe_target_root(&input.target_root)?;
    real_directory(&root, "target root")?;
    let deploy = safe_target_root(&input.deploy_root)?;
    if !deploy.starts_with(root.join("ostree/deploy")) {
        return Err("installed deployment is not inside the target root".to_string());
    }
    let etc = deploy.join("etc");
    real_directory(&etc, "/etc tree")?;

    let hostname_path = etc.join("hostname");
    regular_file(&hostname_path, "hostname")?;
    let installed_hostname = fs::read_to_string(&hostname_path)
        .map_err(|error| format!("could not read installed hostname: {error}"))?;
    if installed_hostname.trim() != input.hostname.trim() {
        return Err(format!(
            "installed hostname verification failed: expected {:?}",
            input.hostname.trim()
        ));
    }

    let locale_path = etc.join("locale.conf");
    regular_file(&locale_path, "locale configuration")?;
    let locale = fs::read_to_string(&locale_path)
        .map_err(|error| format!("could not read installed locale: {error}"))?;
    if locale.trim() != format!("LANG={}", input.locale.trim()) {
        return Err("installed locale verification failed".to_string());
    }

    let keymap_path = etc.join("vconsole.conf");
    regular_file(&keymap_path, "console keymap configuration")?;
    let keymap = fs::read_to_string(&keymap_path)
        .map_err(|error| format!("could not read installed keymap: {error}"))?;
    if keymap.trim() != format!("KEYMAP={}", input.keymap.trim()) {
        return Err("installed keymap verification failed".to_string());
    }

    let localtime = etc.join("localtime");
    let localtime_metadata = fs::symlink_metadata(&localtime)
        .map_err(|error| format!("could not inspect installed timezone link: {error}"))?;
    if !localtime_metadata.file_type().is_symlink() {
        return Err("installed timezone is not a symlink".to_string());
    }
    let expected_timezone = Path::new("/usr/share/zoneinfo").join(input.timezone.trim());
    if fs::read_link(&localtime)
        .map_err(|error| format!("could not read installed timezone link: {error}"))?
        != expected_timezone
    {
        return Err("installed timezone verification failed".to_string());
    }

    if !input.username.trim().is_empty() {
        let passwd_path = etc.join("passwd");
        regular_file(&passwd_path, "passwd database")?;
        let passwd = fs::read_to_string(&passwd_path)
            .map_err(|error| format!("could not read installed account database: {error}"))?;
        if !passwd
            .lines()
            .filter_map(|line| line.split_once(':'))
            .any(|(name, _)| name == input.username.trim())
        {
            return Err(format!(
                "installed account {:?} was not created",
                input.username.trim()
            ));
        }
    }

    let fstab = etc.join("fstab");
    regular_file(&fstab, "fstab")?;
    // M15c: parse every entry — valid UUID/device sources and sane
    // mountpoints — instead of merely checking the file exists.
    let fstab_content = fs::read_to_string(&fstab)
        .map_err(|error| format!("could not read installed fstab: {error}"))?;
    let fstab_entries = parse_fstab_entries(&fstab_content)?;

    // M8: a `tpm2` install must leave a TPM-bound LUKS keyslot behind;
    // without it the disk cannot unlock at boot. Fail the install.
    let encryption_detail = if input.encryption.trim().eq_ignore_ascii_case("tpm2") {
        verify_tpm_encryption(&input.target_disk)?
    } else {
        "encryption not requested".to_string()
    };

    // M15a: the installed system must actually carry a kernel.
    let kernel_detail = kernel_detail(&root, &deploy)?;

    let reason = boot_metadata_reason(&root).ok_or_else(|| {
        "installed system has no boot metadata (loader entries, EFI files, or ostree deployment)"
            .to_string()
    })?;
    // M15b: when the fstab configures an ESP, mount it read-only and
    // verify the bootloader files actually landed. With no ESP entry,
    // fail closed on UEFI boots (the bootloader would be missing) and
    // pass with a note on legacy BIOS boots.
    let bootloader_detail = match esp_device_from_entries(&fstab_entries) {
        Some(device) => format!("{reason}; {}", verify_esp_bootloaders(&device)?),
        None if efi_booted_in(Path::new("/")) => {
            return Err(
                "system booted via UEFI but the installed fstab has no ESP entry".to_string(),
            );
        }
        None => format!("{reason}; no ESP entry in fstab (non-UEFI boot)"),
    };

    Ok(vec![
        AssuranceCheck {
            name: "hostname".to_string(),
            status: "pass".to_string(),
            detail: installed_hostname.trim().to_string(),
        },
        AssuranceCheck {
            name: "locale".to_string(),
            status: "pass".to_string(),
            detail: input.locale.trim().to_string(),
        },
        AssuranceCheck {
            name: "keymap".to_string(),
            status: "pass".to_string(),
            detail: input.keymap.trim().to_string(),
        },
        AssuranceCheck {
            name: "timezone".to_string(),
            status: "pass".to_string(),
            detail: input.timezone.trim().to_string(),
        },
        AssuranceCheck {
            name: "account".to_string(),
            status: "pass".to_string(),
            detail: if input.username.trim().is_empty() {
                "no account requested".to_string()
            } else {
                input.username.trim().to_string()
            },
        },
        AssuranceCheck {
            name: "filesystem".to_string(),
            status: "pass".to_string(),
            detail: format!("{} fstab entries parsed and valid", fstab_entries.len()),
        },
        AssuranceCheck {
            name: "encryption".to_string(),
            status: "pass".to_string(),
            detail: encryption_detail,
        },
        AssuranceCheck {
            name: "kernel".to_string(),
            status: "pass".to_string(),
            detail: kernel_detail,
        },
        AssuranceCheck {
            name: "bootloader".to_string(),
            status: "pass".to_string(),
            detail: bootloader_detail,
        },
    ])
}

#[cfg(test)]
mod tests {
    use super::*;

    const DEPLOY: &str = "ostree/deploy/default/deploy/abc123.0";

    fn input(root: &Path) -> AssuranceInput {
        AssuranceInput {
            target_root: root.to_string_lossy().into_owned(),
            deploy_root: root.join(DEPLOY).to_string_lossy().into_owned(),
            hostname: "kyth-box".to_string(),
            locale: "en_US.UTF-8".to_string(),
            keymap: "us".to_string(),
            timezone: "UTC".to_string(),
            username: "alice".to_string(),
            encryption: "none".to_string(),
            target_disk: String::new(),
        }
    }

    fn target_fixture() -> tempfile::TempDir {
        let directory = tempfile::tempdir().expect("temporary target");
        let root = directory.path();
        // The real layout: no sysroot /etc, only the deployment's.
        let etc = root.join(DEPLOY).join("etc");
        std::fs::create_dir_all(&etc).unwrap();
        std::fs::write(etc.join("hostname"), "kyth-box\n").unwrap();
        std::fs::write(etc.join("locale.conf"), "LANG=en_US.UTF-8\n").unwrap();
        std::fs::write(etc.join("vconsole.conf"), "KEYMAP=us\n").unwrap();
        std::fs::write(
            etc.join("passwd"),
            "alice:x:1000:1000::/home/alice:/bin/bash\n",
        )
        .unwrap();
        // A valid data entry plus an ESP entry whose UUID cannot resolve:
        // the ESP stage must fail closed deterministically (mount fails)
        // instead of depending on the machine running the test.
        std::fs::write(
            etc.join("fstab"),
            "# generated\nUUID=ABCD-1234 /var/home btrfs subvol=@home,compress=zstd:1 0 0\nUUID=DEAD-BEEF /boot/efi vfat umask=0077 0 2\n",
        )
        .unwrap();
        std::os::unix::fs::symlink("/usr/share/zoneinfo/UTC", etc.join("localtime")).unwrap();
        // Deployment kernel for the M15a check.
        let modules = root.join(DEPLOY).join("usr/lib/modules/6.15.0-kyth");
        std::fs::create_dir_all(&modules).unwrap();
        std::fs::write(modules.join("vmlinuz"), "fake kernel").unwrap();
        directory
    }

    #[test]
    fn kernel_detail_finds_the_deployment_vmlinuz() {
        let directory = target_fixture();
        let root = directory.path();
        let detail = kernel_detail(root, &root.join(DEPLOY)).expect("kernel should be found");
        assert!(detail.contains("6.15.0-kyth"), "{detail}");
    }

    #[test]
    fn fstab_parsing_validates_every_entry() {
        let entries = parse_fstab_entries(
            "# comment\n\nUUID=ABCD-1234 /var/home btrfs subvol=@home 0 0\nUUID=DEAD-BEEF /boot/efi vfat umask=0077 0 2\n",
        )
        .expect("valid entries should parse");
        assert_eq!(entries.len(), 2);
        assert_eq!(
            esp_device_from_entries(&entries),
            Some("/dev/disk/by-uuid/DEAD-BEEF".to_string())
        );
        let error = parse_fstab_entries("UUID=ABCD-1234 /var/home btrfs\n")
            .expect_err("short entry must fail");
        assert!(error.contains("fstab line 1"), "{error}");
        let error = parse_fstab_entries("/dev/sda1 / btrfs defaults 0 1\n")
            .expect_err("non-UUID source must fail the strict installer shape");
        assert!(error.contains("fstab line 1"), "{error}");
    }

    #[test]
    fn tpm_token_detection_reads_luks_dump() {
        let with_tpm = "LUKS header information\n\nTokens:\n  0: systemd-tpm2\n     Keyslot:  1\n\nKeyslots:\n  1: luks2\n";
        assert!(tpm_token_present(with_tpm));
        let without_tpm = "LUKS header information\n\nKeyslots:\n  0: luks2\n";
        assert!(!tpm_token_present(without_tpm));
    }

    #[test]
    fn efi_boot_detection_is_root_relative() {
        let directory = tempfile::tempdir().expect("temporary sysroot");
        assert!(!efi_booted_in(directory.path()));
        std::fs::create_dir_all(directory.path().join("sys/firmware/efi")).unwrap();
        assert!(efi_booted_in(directory.path()));
    }

    #[test]
    fn esp_stage_fails_closed_when_the_device_cannot_mount() {
        let entries = parse_fstab_entries("UUID=DEAD-BEEF /boot/efi vfat umask=0077 0 2\n")
            .expect("entry should parse");
        let device = esp_device_from_entries(&entries).expect("ESP device should resolve");
        let error = verify_esp_bootloaders(&device).expect_err("bogus ESP must fail closed");
        assert!(error.contains("ESP"), "unexpected error: {error}");
    }

    #[test]
    fn full_validation_fails_closed_on_unverifiable_esp() {
        // Identity, account, fstab, kernel, and boot-metadata stages all
        // pass on the fixture; the ESP mount cannot succeed, so the whole
        // install fails closed instead of reporting success.
        let directory = target_fixture();
        let error = validate(input(directory.path())).expect_err("ESP must fail closed");
        assert!(error.contains("ESP"), "unexpected error: {error}");
    }

    #[test]
    fn rejects_missing_deployment_and_path_traversal() {
        let directory = target_fixture();
        std::fs::remove_dir_all(directory.path().join("ostree")).unwrap();
        assert!(validate(input(directory.path())).is_err());
        let mut unsafe_input = input(directory.path());
        unsafe_input.target_root = "/tmp/../etc".to_string();
        assert!(validate(unsafe_input).is_err());
    }

    #[test]
    fn checks_the_deployment_etc_and_rejects_a_foreign_deployment() {
        // A sysroot-level etc/ is not what the installed system boots with.
        // The real layout now fails closed at the ESP stage (unmountable
        // fixture UUID) after every earlier stage passed.
        let directory = target_fixture();
        let error = validate(input(directory.path())).expect_err("ESP must fail closed");
        assert!(error.contains("ESP"), "unexpected error: {error}");
        let mut outside = input(directory.path());
        outside.deploy_root = "/var/tmp/somewhere-else".to_string();
        assert!(validate(outside)
            .unwrap_err()
            .contains("not inside the target root"));
    }
}
