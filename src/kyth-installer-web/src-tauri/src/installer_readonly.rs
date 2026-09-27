//! Read-only installer inventories and source-image status.
//!
//! These probes intentionally use fixed executable paths and bounded output.
//! They are part of the privileged daemon's API surface, but they never write
//! to the target disk or trust values supplied by the frontend.

use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const MAX_PROBE_OUTPUT: usize = 4 * 1024 * 1024;

fn command_output(program: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|error| format!("could not run {program}: {error}"))?;
    if output.stdout.len() > MAX_PROBE_OUTPUT || output.stderr.len() > MAX_PROBE_OUTPUT {
        return Err(format!("{program} returned too much output"));
    }
    if !output.status.success() {
        return Err(format!(
            "{program} failed with exit code {}: {}",
            output.status.code().unwrap_or(1),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    String::from_utf8(output.stdout).map_err(|_| format!("{program} returned non-UTF-8 output"))
}

fn command_lines(program: &str, args: &[&str]) -> Option<Vec<String>> {
    let output = command_output(program, args).ok()?;
    let values = output
        .lines()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    (!values.is_empty()).then_some(values)
}

fn fallback_lines(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_string()).collect()
}

pub(crate) fn timezones() -> Vec<String> {
    if let Some(values) = command_lines("/usr/bin/timedatectl", &["list-timezones"]) {
        return values;
    }
    let mut zones = BTreeSet::from(["UTC".to_string()]);
    for path in [
        "/usr/share/zoneinfo/zone1970.tab",
        "/usr/share/zoneinfo/zone.tab",
    ] {
        let Ok(contents) = fs::read_to_string(path) else {
            continue;
        };
        for line in contents.lines().map(str::trim) {
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some(zone) = line.split_whitespace().nth(2) {
                zones.insert(zone.to_string());
            }
        }
        if zones.len() > 1 {
            break;
        }
    }
    zones.into_iter().collect()
}

pub(crate) fn locales() -> Vec<String> {
    command_lines("/usr/bin/localectl", &["list-locales", "--no-pager"])
        .unwrap_or_else(|| fallback_lines(&["en_US.UTF-8"]))
}

pub(crate) fn keymaps() -> Vec<String> {
    command_lines("/usr/bin/localectl", &["list-keymaps", "--no-pager"])
        .unwrap_or_else(|| fallback_lines(&["us"]))
}

fn configured(name: &str, default: &str) -> String {
    std::env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| default.to_string())
}

fn normalize_source_reference(image: &str) -> String {
    if ["docker://", "containers-storage:", "oci:", "ostree:"]
        .iter()
        .any(|prefix| image.starts_with(prefix))
    {
        image.to_string()
    } else {
        format!("docker://{image}")
    }
}

fn source_reference() -> String {
    normalize_source_reference(&configured(
        "KYTH_SOURCE_IMAGE",
        "ghcr.io/kyth-os/kyth:latest",
    ))
}

fn target_reference() -> String {
    configured(
        "KYTH_TARGET_IMAGE",
        &configured("KYTH_SOURCE_IMAGE", "ghcr.io/kyth-os/kyth:latest"),
    )
}

fn oci_layout_parts(reference: &str) -> Option<(PathBuf, String)> {
    let value = reference.strip_prefix("oci:")?;
    let slash = value.rfind('/').unwrap_or(0);
    let colon = value.rfind(':');
    if colon.is_some_and(|colon| colon > slash) {
        let colon = colon?;
        Some((
            PathBuf::from(&value[..colon]),
            value[colon + 1..].to_string(),
        ))
    } else {
        Some((PathBuf::from(value), "latest".to_string()))
    }
}

fn metadata_path() -> PathBuf {
    PathBuf::from(configured(
        "KYTH_SOURCE_METADATA",
        "/usr/share/kyth/image-source.json",
    ))
}

fn signature_bundle_path() -> PathBuf {
    PathBuf::from(configured(
        "KYTH_SOURCE_SIGNATURE",
        "/usr/share/kyth/image.sig.bundle.json",
    ))
}

/// True when the ISO build-time source needed a registry cosign signature.
///
/// Loopback registries and non-registry transports are unsigned dev inputs;
/// everything else must carry a verified signature bundle.
fn registry_signed_source(source_image: &str) -> bool {
    let image = source_image
        .strip_prefix("docker://")
        .unwrap_or(source_image);
    if image.starts_with("oci:")
        || image.starts_with("containers-storage:")
        || image.starts_with("dir:")
        || image.starts_with("ostree:")
    {
        return false;
    }
    !(image.starts_with("localhost:")
        || image.starts_with("localhost/")
        || image.starts_with("127.0.0.1")
        || image.starts_with("[::1]"))
}

fn valid_base64_signature(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128 * 1024
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'+' | b'/' | b'='))
}

/// Verify the cosign signature bundle embedded at ISO build time.
///
/// `metadata.signature` is `"verified"` for registry builds — the bundle
/// file's sha256 must equal `metadata.signature_digest` and the bundle's
/// subject digest must equal the release digest — or `"local"` for unsigned
/// loopback / non-registry dev sources. `"local"` is only accepted when the
/// build-time source image itself is loopback/local; a registry image
/// claiming to be local fails closed. Unknown states fail closed.
fn verify_embedded_signature(
    metadata: &Value,
    digest: &str,
    release_digest: &str,
    bundle_path: &Path,
) -> Result<(), String> {
    let state = metadata
        .get("signature")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if state == "local" {
        let source_image = metadata
            .get("source_image")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if registry_signed_source(source_image) {
            return Err(
                "embedded image claims an unsigned local source but was built from a registry image"
                    .to_string(),
            );
        }
        return Ok(());
    }
    if state != "verified" {
        return Err("embedded-image metadata has an unknown signature state".to_string());
    }
    regular_file(bundle_path)
        .map_err(|error| format!("embedded signature bundle is missing or unsafe: {error}"))?;
    let raw = fs::read(bundle_path)
        .map_err(|error| format!("could not read embedded signature bundle: {error}"))?;
    if raw.len() > MAX_PROBE_OUTPUT {
        return Err("embedded signature bundle is too large".to_string());
    }
    let Some(bundle_hex) = bundle_path.to_str().and_then(|path| {
        command_output("/usr/bin/sha256sum", &[path])
            .ok()?
            .split_whitespace()
            .next()
            .map(str::to_string)
    }) else {
        return Err("sha256sum returned no bundle digest".to_string());
    };
    let calculated = format!("sha256:{bundle_hex}");
    let expected = metadata
        .get("signature_digest")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if expected.is_empty() || expected != calculated {
        return Err(
            "embedded signature bundle does not match the digest pinned by this ISO release"
                .to_string(),
        );
    }
    let bundle: Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("embedded signature bundle is invalid: {error}"))?;
    if bundle.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err("embedded signature bundle has an unsupported schema".to_string());
    }
    if bundle.get("digest").and_then(Value::as_str) != Some(digest)
        || bundle.get("release_digest").and_then(Value::as_str) != Some(release_digest)
    {
        return Err("embedded signature bundle does not cover this ISO release digest".to_string());
    }
    let signed = bundle
        .get("signatures")
        .and_then(Value::as_array)
        .is_some_and(|signatures| {
            !signatures.is_empty()
                && signatures
                    .iter()
                    .all(|entry| entry.as_str().is_some_and(valid_base64_signature))
        });
    if !signed {
        return Err("embedded signature bundle carries no verifiable signature".to_string());
    }
    Ok(())
}

fn regular_file(path: &Path) -> Result<(), String> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("could not inspect source metadata: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!(
            "source metadata is missing or unsafe: {}",
            path.display()
        ));
    }
    Ok(())
}

fn embedded_digest(reference: &str, target: &str) -> Result<String, String> {
    embedded_digest_with_paths(
        reference,
        target,
        &metadata_path(),
        &signature_bundle_path(),
    )
}

fn embedded_digest_with_paths(
    reference: &str,
    target: &str,
    metadata_path: &Path,
    bundle_path: &Path,
) -> Result<String, String> {
    let (root, tag) = oci_layout_parts(reference)
        .ok_or_else(|| "embedded OCI image reference is invalid".to_string())?;
    let root_metadata = fs::symlink_metadata(&root)
        .map_err(|error| format!("could not inspect embedded OCI image: {error}"))?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        return Err(format!(
            "embedded OCI layout is missing or unsafe: {}",
            root.display()
        ));
    }
    let layout_path = root.join("oci-layout");
    regular_file(&layout_path)?;
    let layout: Value = serde_json::from_slice(
        &fs::read(&layout_path).map_err(|error| format!("could not read OCI layout: {error}"))?,
    )
    .map_err(|error| format!("embedded OCI layout is invalid: {error}"))?;
    if layout.get("imageLayoutVersion").and_then(Value::as_str) != Some("1.0.0") {
        return Err("embedded OCI image has an unsupported layout version".to_string());
    }
    let index_path = root.join("index.json");
    regular_file(&index_path)?;
    let index: Value = serde_json::from_slice(
        &fs::read(&index_path).map_err(|error| format!("could not read OCI index: {error}"))?,
    )
    .map_err(|error| format!("embedded OCI index is invalid: {error}"))?;
    let manifests = index
        .get("manifests")
        .and_then(Value::as_array)
        .ok_or_else(|| "embedded OCI index has no manifests".to_string())?;
    let descriptor = manifests
        .iter()
        .find(|item| {
            item.get("annotations")
                .and_then(Value::as_object)
                .and_then(|annotations| annotations.get("org.opencontainers.image.ref.name"))
                .and_then(Value::as_str)
                == Some(tag.as_str())
        })
        .or_else(|| (manifests.len() == 1).then(|| &manifests[0]))
        .ok_or_else(|| "embedded OCI image tag was not found".to_string())?;
    let digest = descriptor
        .get("digest")
        .and_then(Value::as_str)
        .filter(|digest| digest.starts_with("sha256:") && digest.len() == 71)
        .ok_or_else(|| "embedded OCI image has no valid manifest digest".to_string())?;
    let blob = root.join("blobs").join("sha256").join(&digest[7..]);
    regular_file(&blob)?;
    let calculated = command_output(
        "/usr/bin/sha256sum",
        &[blob
            .to_str()
            .ok_or_else(|| "OCI manifest path is not UTF-8".to_string())?],
    )?
    .split_whitespace()
    .next()
    .map(|value| format!("sha256:{value}"))
    .ok_or_else(|| "sha256sum returned no digest".to_string())?;
    if calculated != digest {
        return Err("embedded OCI manifest failed its SHA-256 integrity check".to_string());
    }

    regular_file(metadata_path)?;
    let metadata: Value = serde_json::from_slice(
        &fs::read(metadata_path)
            .map_err(|error| format!("could not read embedded-image metadata: {error}"))?,
    )
    .map_err(|error| format!("embedded-image metadata is invalid: {error}"))?;
    if metadata.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err("embedded-image metadata has an unsupported schema".to_string());
    }
    let metadata_digest = metadata
        .get("digest")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let configured_digest = configured("KYTH_SOURCE_DIGEST", metadata_digest);
    if configured_digest != digest || metadata_digest != digest {
        return Err(
            "embedded OCI image does not match the digest pinned by this ISO release".to_string(),
        );
    }
    // The release digest is the ISO build's pinned expectation: manifest,
    // metadata, release, and configured digests must all agree, and the
    // build-time cosign bundle must still cover that digest.
    let release_digest = metadata
        .get("release_digest")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if release_digest != digest {
        return Err(
            "embedded OCI image does not match the release digest pinned by this ISO release"
                .to_string(),
        );
    }
    verify_embedded_signature(&metadata, digest, release_digest, bundle_path)?;
    if let Some(metadata_target) = metadata.get("target_image").and_then(Value::as_str) {
        if !metadata_target.is_empty() && metadata_target != target {
            return Err(
                "embedded-image metadata does not match the configured update target".to_string(),
            );
        }
    }
    Ok(digest.to_string())
}

pub(crate) fn source_status_for(source_value: &str, target: &str) -> Value {
    let source = normalize_source_reference(source_value);
    if source.starts_with("oci:") {
        return match embedded_digest(&source, &target) {
            Ok(digest) => serde_json::json!({
                "available": true,
                "kind": "embedded",
                "verified": true,
                "requires_network": false,
                "digest": digest,
                "target_ref": target,
                "message": "Verified image embedded in this ISO"
            }),
            Err(error) => serde_json::json!({
                "available": false,
                "kind": "invalid",
                "verified": false,
                "requires_network": false,
                "digest": "",
                "message": error
            }),
        };
    }
    if ["containers-storage:", "ostree:"]
        .iter()
        .any(|prefix| source.starts_with(prefix))
    {
        let digest = configured("KYTH_SOURCE_DIGEST", "");
        return serde_json::json!({
            "available": true,
            "kind": "local",
            "verified": !digest.is_empty(),
            "requires_network": false,
            "digest": digest,
            "target_ref": target,
            "message": "Local image selected"
        });
    }
    let digest = configured("KYTH_SOURCE_DIGEST", "");
    serde_json::json!({
        "available": true,
        "kind": "network",
        "verified": !digest.is_empty(),
        "requires_network": true,
        "digest": digest,
        "target_ref": target,
        "message": "Network image selected"
    })
}

fn source_status() -> Value {
    source_status_for(&source_reference(), &target_reference())
}

pub(crate) fn config() -> Value {
    serde_json::json!({
        "source_image": configured("KYTH_SOURCE_IMAGE", "ghcr.io/kyth-os/kyth:latest"),
        "is_live": Path::new("/etc/kyth-installer.env").is_file(),
        "source": source_status()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fallback_inventories_are_nonempty() {
        assert_eq!(fallback_lines(&["UTC"]), vec!["UTC"]);
        assert_eq!(fallback_lines(&["en_US.UTF-8"]), vec!["en_US.UTF-8"]);
        assert_eq!(fallback_lines(&["us"]), vec!["us"]);
    }

    #[test]
    fn source_reference_normalizes_registry_images() {
        assert_eq!(
            source_reference().starts_with("docker://") || source_reference().starts_with("oci:"),
            true
        );
    }

    #[test]
    fn source_status_is_support_safe_without_embedded_metadata() {
        let value = source_status();
        assert!(value.get("kind").and_then(Value::as_str).is_some());
        assert!(value.get("message").and_then(Value::as_str).is_some());
        assert!(value.get("digest").and_then(Value::as_str).is_some());
    }

    struct EmbeddedFixture {
        _directory: tempfile::TempDir,
        reference: String,
        digest: String,
        metadata_path: PathBuf,
        bundle_path: PathBuf,
    }

    fn sha256_hex(path: &Path) -> String {
        command_output(
            "/usr/bin/sha256sum",
            &[path.to_str().expect("fixture path is UTF-8")],
        )
        .expect("sha256sum fixture probe")
        .split_whitespace()
        .next()
        .expect("sha256sum fixture digest")
        .to_string()
    }

    fn embedded_fixture(source_image: &str) -> EmbeddedFixture {
        let directory = tempfile::tempdir().expect("fixture directory");
        let root = directory.path().join("image");
        let manifest = br#"{"schemaVersion":2,"mediaType":"application/vnd.oci.image.manifest.v1+json","config":{}}"#;
        let blob_dir = root.join("blobs").join("sha256");
        fs::create_dir_all(&blob_dir).expect("fixture blob directory");
        fs::write(root.join("oci-layout"), r#"{"imageLayoutVersion":"1.0.0"}"#)
            .expect("fixture layout");
        // Write the blob first so its content-addressed name is real.
        let probe = blob_dir.join("probe");
        fs::write(&probe, manifest).expect("fixture probe blob");
        let hex = sha256_hex(&probe);
        let digest = format!("sha256:{hex}");
        fs::rename(&probe, blob_dir.join(&hex)).expect("fixture manifest blob");
        fs::write(
            root.join("index.json"),
            serde_json::json!({"manifests": [{
                "digest": digest,
                "annotations": {"org.opencontainers.image.ref.name": "latest"},
            }]})
            .to_string(),
        )
        .expect("fixture index");
        let reference = format!("oci:{}:latest", root.display());
        let bundle_path = directory.path().join("image.sig.bundle.json");
        let bundle = serde_json::json!({
            "schema_version": 1,
            "digest": digest,
            "release_digest": digest,
            "source_image": source_image,
            "identity": "test-identity",
            "issuer": "https://token.actions.githubusercontent.com",
            "signatures": ["c2lnbmF0dXJlLW9uZQ=="],
        });
        fs::write(&bundle_path, bundle.to_string()).expect("fixture bundle");
        let bundle_digest = format!("sha256:{}", sha256_hex(&bundle_path));
        let metadata_path = directory.path().join("image-source.json");
        fs::write(
            &metadata_path,
            serde_json::json!({
                "schema_version": 1,
                "digest": digest,
                "release_digest": digest,
                "target_image": "ghcr.io/kyth-os/kyth:testing",
                "source_image": source_image,
                "signature": "verified",
                "signature_digest": bundle_digest,
            })
            .to_string(),
        )
        .expect("fixture metadata");
        EmbeddedFixture {
            _directory: directory,
            reference,
            digest,
            metadata_path,
            bundle_path,
        }
    }

    #[test]
    fn embedded_digest_requires_release_and_signature_agreement() {
        let fixture = embedded_fixture("ghcr.io/kyth-os/kyth:testing");
        let digest = embedded_digest_with_paths(
            &fixture.reference,
            "ghcr.io/kyth-os/kyth:testing",
            &fixture.metadata_path,
            &fixture.bundle_path,
        )
        .expect("verified embedded source should validate");
        assert_eq!(digest, fixture.digest);
    }

    #[test]
    fn embedded_digest_rejects_release_digest_mismatch() {
        let fixture = embedded_fixture("ghcr.io/kyth-os/kyth:testing");
        let mut metadata: Value =
            serde_json::from_slice(&fs::read(&fixture.metadata_path).expect("fixture metadata"))
                .expect("fixture metadata JSON");
        metadata["release_digest"] = serde_json::json!(
            "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        );
        fs::write(&fixture.metadata_path, metadata.to_string()).expect("fixture metadata");
        let error = embedded_digest_with_paths(
            &fixture.reference,
            "ghcr.io/kyth-os/kyth:testing",
            &fixture.metadata_path,
            &fixture.bundle_path,
        )
        .expect_err("release digest mismatch must fail closed");
        assert!(error.contains("release digest"), "{error}");
    }

    #[test]
    fn embedded_digest_rejects_tampered_signature_bundle() {
        let fixture = embedded_fixture("ghcr.io/kyth-os/kyth:testing");
        fs::write(&fixture.bundle_path, r#"{"schema_version":1}"#).expect("fixture bundle");
        let error = embedded_digest_with_paths(
            &fixture.reference,
            "ghcr.io/kyth-os/kyth:testing",
            &fixture.metadata_path,
            &fixture.bundle_path,
        )
        .expect_err("tampered bundle must fail closed");
        assert!(error.contains("signature"), "{error}");
    }

    #[test]
    fn embedded_digest_rejects_bundle_covering_another_digest() {
        let fixture = embedded_fixture("ghcr.io/kyth-os/kyth:testing");
        let bundle: Value =
            serde_json::from_slice(&fs::read(&fixture.bundle_path).expect("fixture bundle"))
                .expect("fixture bundle JSON");
        let mut metadata: Value =
            serde_json::from_slice(&fs::read(&fixture.metadata_path).expect("fixture metadata"))
                .expect("fixture metadata JSON");
        // Re-point the bundle at another digest and re-pin it, so only the
        // subject check can catch the mismatch.
        let mut other = bundle.clone();
        other["digest"] = serde_json::json!(
            "sha256:1111111111111111111111111111111111111111111111111111111111111111"
        );
        fs::write(&fixture.bundle_path, other.to_string()).expect("fixture bundle");
        metadata["signature_digest"] =
            serde_json::json!(format!("sha256:{}", sha256_hex(&fixture.bundle_path)));
        fs::write(&fixture.metadata_path, metadata.to_string()).expect("fixture metadata");
        let error = embedded_digest_with_paths(
            &fixture.reference,
            "ghcr.io/kyth-os/kyth:testing",
            &fixture.metadata_path,
            &fixture.bundle_path,
        )
        .expect_err("bundle subject mismatch must fail closed");
        assert!(error.contains("signature bundle"), "{error}");
    }

    #[test]
    fn embedded_digest_accepts_unsigned_local_dev_source_only() {
        let fixture = embedded_fixture("docker://localhost:5000/kyth:dev");
        let mut metadata: Value =
            serde_json::from_slice(&fs::read(&fixture.metadata_path).expect("fixture metadata"))
                .expect("fixture metadata JSON");
        metadata["signature"] = serde_json::json!("local");
        metadata["signature_digest"] = serde_json::json!("");
        fs::write(&fixture.metadata_path, metadata.to_string()).expect("fixture metadata");
        embedded_digest_with_paths(
            &fixture.reference,
            "ghcr.io/kyth-os/kyth:testing",
            &fixture.metadata_path,
            &fixture.bundle_path,
        )
        .expect("loopback dev source stays installable");

        let registry = embedded_fixture("ghcr.io/kyth-os/kyth:testing");
        let mut metadata: Value =
            serde_json::from_slice(&fs::read(&registry.metadata_path).expect("fixture metadata"))
                .expect("fixture metadata JSON");
        metadata["signature"] = serde_json::json!("local");
        metadata["signature_digest"] = serde_json::json!("");
        fs::write(&registry.metadata_path, metadata.to_string()).expect("fixture metadata");
        let error = embedded_digest_with_paths(
            &registry.reference,
            "ghcr.io/kyth-os/kyth:testing",
            &registry.metadata_path,
            &registry.bundle_path,
        )
        .expect_err("registry image claiming local must fail closed");
        assert!(error.contains("unsigned local"), "{error}");
    }
}
