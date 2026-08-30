//! Safe Windows-installer inspection and Bottles planning.
//!
//! This is the read-only half of `desktop.windows_installer`: it validates PE
//! and MSI headers, captures a file identity/hash, assesses compatibility, and
//! projects a deterministic bottle plan. Staging, Flatpak installation, and
//! launching a Windows program remain explicit caller-owned actions.

use regex::RegexBuilder;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt::{Display, Formatter};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

pub const BOTTLES_ID: &str = "com.usebottles.bottles";
pub const FLATHUB_URL: &str = "https://dl.flathub.org/repo/flathub.flatpakrepo";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum InstallerKind { Exe, Msi }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Compatibility { Likely, Unknown, Unsupported }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum WorkflowFailureKind { InvalidFile, FileChanged }

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InstallerInspectionError {
    pub kind: WorkflowFailureKind,
    pub message: String,
}

impl Display for InstallerInspectionError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result { self.message.fmt(formatter) }
}

impl std::error::Error for InstallerInspectionError {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileIdentity {
    pub device: u64,
    pub inode: u64,
    pub size: u64,
    pub modified_ns: i128,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InstallerRequest {
    pub source: PathBuf,
    pub kind: InstallerKind,
    pub architecture: String,
    pub identity: FileIdentity,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CompatibilityAssessment {
    pub level: Compatibility,
    pub summary: String,
    pub detail: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BottlePlan {
    pub name: String,
    pub environment: String,
    pub architecture: String,
}

fn invalid(message: impl Into<String>) -> InstallerInspectionError {
    InstallerInspectionError { kind: WorkflowFailureKind::InvalidFile, message: message.into() }
}

fn inspect_pe(source: &mut File) -> Result<String, InstallerInspectionError> {
    let mut dos_header = [0_u8; 64];
    source.read_exact(&mut dos_header).map_err(|_| invalid("The file does not contain a valid Windows executable header."))?;
    if &dos_header[..2] != b"MZ" {
        return Err(invalid("The file does not contain a valid Windows executable header."));
    }
    let pe_offset = u32::from_le_bytes(dos_header[0x3c..0x40].try_into().unwrap()) as u64;
    if pe_offset < 64 || pe_offset > 64 * 1024 * 1024 {
        return Err(invalid("The Windows executable header points outside a safe inspection range."));
    }
    source.seek(SeekFrom::Start(pe_offset)).map_err(|_| invalid("The Windows executable header could not be inspected."))?;
    let mut header = [0_u8; 6];
    source.read_exact(&mut header).map_err(|_| invalid("The Windows executable header points outside a safe inspection range."))?;
    if &header[..4] != b"PE\0\0" {
        return Err(invalid("The file has a DOS header but no valid PE executable header."));
    }
    Ok(match u16::from_le_bytes([header[4], header[5]]) {
        0x014c => "win32",
        0x8664 => "win64",
        0xaa64 => "arm64",
        _ => "unknown",
    }.into())
}

fn identity(path: &Path) -> Result<FileIdentity, InstallerInspectionError> {
    let metadata = std::fs::metadata(path).map_err(|error| invalid(format!("The installer could not be read: {error}")))?;
    Ok(FileIdentity { device: metadata.dev(), inode: metadata.ino(), size: metadata.len(), modified_ns: i128::from(metadata.mtime()) * 1_000_000_000 + i128::from(metadata.mtime_nsec()) })
}

fn sha256(path: &Path) -> Result<String, InstallerInspectionError> {
    let mut source = File::open(path).map_err(|error| invalid(format!("The installer could not be read: {error}")))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = source.read(&mut buffer).map_err(|error| invalid(format!("The installer could not be read: {error}")))?;
        if count == 0 { break; }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

pub fn inspect_installer(path: impl AsRef<Path>) -> Result<InstallerRequest, InstallerInspectionError> {
    let path = path.as_ref();
    if path.is_symlink() || !path.is_file() {
        return Err(invalid("Choose a regular, non-symbolic-link installer file."));
    }
    let resolved = path.canonicalize().map_err(|error| invalid(format!("The installer could not be read: {error}")))?;
    let kind = match resolved.extension().and_then(|extension| extension.to_str()).map(str::to_ascii_lowercase).as_deref() {
        Some("exe") => InstallerKind::Exe,
        Some("msi") => InstallerKind::Msi,
        _ => return Err(invalid("Kyth currently supports Windows .exe and .msi installers only.")),
    };
    let mut source = File::open(&resolved).map_err(|error| invalid(format!("The installer could not be read: {error}")))?;
    let architecture = match kind {
        InstallerKind::Exe => inspect_pe(&mut source)?,
        InstallerKind::Msi => {
            let mut header = [0_u8; 8];
            source.read_exact(&mut header).map_err(|_| invalid("The file does not contain a valid MSI compound-document header."))?;
            if header == *b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" { "win64".into() } else { return Err(invalid("The file does not contain a valid MSI compound-document header.")); }
        }
    };
    Ok(InstallerRequest { source: resolved.clone(), kind, architecture, identity: identity(&resolved)?, sha256: sha256(&resolved)? })
}

pub fn assess_compatibility(request: &InstallerRequest) -> CompatibilityAssessment {
    let unsupported = RegexBuilder::new(r"(?:^|[-_. ])(?:anti[-_. ]?cheat|battleye|easyanti(?:cheat)?|driver|firmware|bios|chipset|microsoft[-_. ]?store|windows[-_. ]?update)(?:$|[-_. ])").case_insensitive(true).build().expect("static compatibility pattern");
    if request.architecture == "arm64" {
        return CompatibilityAssessment { level: Compatibility::Unsupported, summary: "ARM Windows installer".into(), detail: "This installer targets Windows on ARM, which this Kyth compatibility path does not support.".into() };
    }
    let stem = request.source.file_stem().and_then(|stem| stem.to_str()).unwrap_or_default();
    if unsupported.is_match(stem) {
        return CompatibilityAssessment { level: Compatibility::Unsupported, summary: "System-level Windows component".into(), detail: "Drivers, firmware tools, kernel anti-cheat, and Windows system components generally cannot run through Wine.".into() };
    }
    if matches!(request.architecture.as_str(), "win32" | "win64") {
        return CompatibilityAssessment { level: Compatibility::Likely, summary: "Standard Windows installer".into(), detail: "Many conventional desktop installers work, but compatibility is not guaranteed.".into() };
    }
    CompatibilityAssessment { level: Compatibility::Unknown, summary: "Unknown Windows architecture".into(), detail: "Kyth can try this installer, but its architecture could not be identified reliably.".into() }
}

pub fn plan_bottle(request: &InstallerRequest) -> BottlePlan {
    let source_stem = request.source.file_stem().and_then(|stem| stem.to_str()).unwrap_or("windows-app").to_ascii_lowercase();
    let separators = regex::Regex::new(r"[^a-z0-9]+").expect("static bottle name pattern");
    let mut stem = separators.replace_all(&source_stem, "-").trim_matches('-').to_string();
    for token in ["setup", "installer", "install", "update", "updater"] {
        let pattern = regex::Regex::new(&format!(r"(?:^|-){token}(?:-|$)")).expect("static bottle wrapper pattern");
        stem = pattern.replace_all(&stem, "-").trim_matches('-').to_string();
    }
    stem.truncate(36);
    let architecture = matches!(request.architecture.as_str(), "win32" | "win64").then_some(request.architecture.as_str()).unwrap_or("win64");
    let gaming = RegexBuilder::new(r"(?:game|gaming|steam|battle[-_. ]?net|blizzard|gog|epic|launcher|ubisoft|uplay)").case_insensitive(true).build().expect("static gaming pattern").is_match(&source_stem);
    BottlePlan { name: format!("Kyth-{}-{}", if stem.is_empty() { "windows-app" } else { &stem }, &request.sha256[..request.sha256.len().min(8)]), environment: if gaming { "gaming" } else { "application" }.into(), architecture: architecture.into() }
}

pub fn flatpak_install_commands() -> [Vec<String>; 2] {
    [vec!["flatpak", "remote-add", "--if-not-exists", "--user", "flathub", FLATHUB_URL].into_iter().map(String::from).collect(), vec!["flatpak", "install", "-y", "--noninteractive", "--user", "flathub", BOTTLES_ID].into_iter().map(String::from).collect()]
}

pub fn bottles_cli(args: &[&str]) -> Vec<String> {
    [vec!["flatpak", "run", "--command=bottles-cli", BOTTLES_ID].into_iter().map(String::from).collect::<Vec<_>>(), args.iter().map(|arg| (*arg).into()).collect()].concat()
}

pub fn bottle_names(payload: &str) -> BTreeSet<String> {
    let Ok(mut value) = serde_json::from_str::<Value>(payload) else {
        return payload.lines().map(str::trim).filter(|line| !line.is_empty()).map(String::from).collect();
    };
    if let Some(bottles) = value.get("bottles") { value = bottles.clone(); }
    if let Some(object) = value.as_object() { return object.keys().cloned().collect(); }
    value.as_array().into_iter().flatten().filter_map(|item| item.as_str().map(String::from).or_else(|| item.get("Name").or_else(|| item.get("name")).and_then(Value::as_str).map(String::from))).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    fn pe(machine: u16) -> Vec<u8> {
        let mut bytes = vec![0_u8; 128];
        bytes[..2].copy_from_slice(b"MZ");
        bytes[0x3c..0x40].copy_from_slice(&(64_u32).to_le_bytes());
        bytes[64..68].copy_from_slice(b"PE\0\0");
        bytes[68..70].copy_from_slice(&machine.to_le_bytes());
        bytes
    }

    #[test]
    fn inspects_pe_and_msi_headers() {
        let directory = tempdir().unwrap();
        let exe = directory.path().join("Setup Game.exe");
        fs::write(&exe, pe(0x8664)).unwrap();
        let request = inspect_installer(&exe).unwrap();
        assert_eq!(request.architecture, "win64");
        assert_eq!(assess_compatibility(&request).level, Compatibility::Likely);
        assert_eq!(plan_bottle(&request).environment, "gaming");
        let msi = directory.path().join("office.msi");
        fs::write(&msi, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload").unwrap();
        assert_eq!(inspect_installer(&msi).unwrap().kind, InstallerKind::Msi);
    }

    #[test]
    fn rejects_bad_headers_and_system_components() {
        let directory = tempdir().unwrap();
        let exe = directory.path().join("driver.exe");
        fs::write(&exe, b"MZbad").unwrap();
        assert!(inspect_installer(&exe).is_err());
        let request = InstallerRequest { source: PathBuf::from("Battleye Setup.exe"), kind: InstallerKind::Exe, architecture: "win64".into(), identity: FileIdentity { device: 0, inode: 0, size: 0, modified_ns: 0 }, sha256: "0123456789abcdef".into() };
        assert_eq!(assess_compatibility(&request).level, Compatibility::Unsupported);
    }

    #[test]
    fn parses_bottles_shapes_and_projects_commands() {
        assert_eq!(bottle_names(r#"{"bottles":{"Demo":{}}}"#), BTreeSet::from(["Demo".into()]));
        assert_eq!(bottle_names(r#"[{"Name":"Demo"},"Other"]"#), BTreeSet::from(["Demo".into(), "Other".into()]));
        assert_eq!(bottle_names("Demo\nOther\n"), BTreeSet::from(["Demo".into(), "Other".into()]));
        assert_eq!(bottles_cli(&["list"]) [0], "flatpak");
        assert_eq!(flatpak_install_commands()[1].last().unwrap(), BOTTLES_ID);
    }
}
