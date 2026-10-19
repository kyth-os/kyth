//! KythOS-signed update manifest verification for the runtime updaters.
//!
//! Implements the updater signature-verification decision (approved
//! 2026-10-19, docs/updater-signing.md). Today both runtime updaters
//! (rclone, GE-Proton) verify downloads against a checksum fetched from
//! the same release as the artifact itself, which proves transport
//! integrity but not authenticity: a compromised upstream release
//! replaces the file and its checksum together. The fix is a small
//! manifest, signed offline with the KythOS updater signing key, that
//! approves a specific (component, version, artifact, digest) tuple.
//! The updaters refuse — fail closed — unless the update they are about
//! to install is approved by a manifest whose OpenPGP signature verifies
//! against the KythOS signing primary key baked into the image.
//!
//! Trust model (mirrors the decision):
//!   * The image carries only PUBLIC key material: the trust anchor at
//!     [`DEFAULT_KEYRING_PATH`] is the primary key certificate(s).
//!   * The current certificate (primary + its current signing subkeys)
//!     is published next to the manifest as [`KEYS_FILENAME`]. A fetched
//!     certificate is trusted only when its primary key fingerprint
//!     matches a baked-in anchor — so a signing-subkey rotation needs
//!     no image update (publish the amended certificate), while a new
//!     primary must ride out in an image update. The anchor file may
//!     hold several certificates so an old and a new primary can
//!     overlap during a primary rotation.
//!   * Signing is offline and manual; nothing automated can sign. This
//!     module is verify-only.
//!   * Any failure — missing/unparseable key, missing manifest,
//!     missing or invalid signature, no manifest entry for the resolved
//!     version, digest mismatch — is an error, and the callers refuse
//!     the install and keep the current version.
//!
//! Until a real public key replaces the shipped placeholder anchor, the
//! anchor contains no key material and every gated update is refused
//! with an explicit "signing key not installed yet" error. That is the
//! intended placeholder behaviour, not a bypass.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use pgp::composed::{Deserializable, DetachedSignature, SignedPublicKey};
use pgp::types::KeyDetails;
use serde::Deserialize;

use super::release_fetch::{digest_file_hex, download_file, MAX_CHECKSUM_BYTES};

pub const COMPONENT_RCLONE: &str = "rclone";
pub const COMPONENT_GE_PROTON: &str = "ge-proton";

/// File names published on the KythOS public release channel (the same
/// R2 bucket `release_publish` serves ISO metadata from).
pub const MANIFEST_FILENAME: &str = "kyth-updater-manifest.json";
pub const KEYS_FILENAME: &str = "kyth-updater-keys.asc";

/// Image-baked trust anchor: OpenPGP public certificate(s) of the
/// KythOS updater signing primary key(s). Installed from
/// `build_files/config/updater-signing-keys.asc` by the branding
/// fragment `99-updater-signing-key.sh`.
pub const DEFAULT_KEYRING_PATH: &str = "/usr/share/kyth/updater-signing-keys.asc";

pub const KEYRING_PATH_ENV: &str = "KYTH_UPDATER_KEYRING_PATH";
pub const MANIFEST_URL_ENV: &str = "KYTH_UPDATER_MANIFEST_URL";
pub const SIGNATURE_URL_ENV: &str = "KYTH_UPDATER_MANIFEST_SIGNATURE_URL";
pub const KEYS_URL_ENV: &str = "KYTH_UPDATER_KEYS_URL";

/// Only manifest schema this build understands. Unknown schemas fail
/// closed: a future format must not be half-interpreted by old images.
pub const SUPPORTED_MANIFEST_SCHEMA: u32 = 1;

pub fn default_manifest_url() -> String {
    format!(
        "{}/{MANIFEST_FILENAME}",
        crate::release_publish::PUBLIC_ASSET_BASE_URL
    )
}

pub fn default_keys_url() -> String {
    format!(
        "{}/{KEYS_FILENAME}",
        crate::release_publish::PUBLIC_ASSET_BASE_URL
    )
}

fn env_or(name: &str, default: &str) -> String {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| default.to_string())
}

pub fn keyring_path() -> PathBuf {
    PathBuf::from(env_or(KEYRING_PATH_ENV, DEFAULT_KEYRING_PATH))
}

pub fn manifest_url() -> String {
    env_or(MANIFEST_URL_ENV, &default_manifest_url())
}

pub fn signature_url() -> String {
    let manifest = manifest_url();
    env_or(SIGNATURE_URL_ENV, &format!("{manifest}.asc"))
}

pub fn keys_url() -> String {
    env_or(KEYS_URL_ENV, &default_keys_url())
}

/// One approved update tuple from the signed manifest.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ApprovedUpdate {
    pub component: String,
    pub version: String,
    pub artifact: String,
    #[serde(default)]
    pub sha256: Option<String>,
    #[serde(default)]
    pub sha512: Option<String>,
}

impl ApprovedUpdate {
    /// The manifest-pinned digest for `algorithm` ("sha256"/"sha512"),
    /// normalized to lowercase hex. A manifest entry that lacks the
    /// digest an updater needs is a refusal, not a skip: the signature
    /// only vouches for values actually present.
    pub fn expected_digest(&self, algorithm: &str) -> Result<String, String> {
        let raw = match algorithm {
            "sha256" => self.sha256.as_deref(),
            "sha512" => self.sha512.as_deref(),
            other => {
                return Err(format!(
                    "unsupported digest algorithm for manifest check: {other}"
                ))
            }
        };
        let digest = raw
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                format!(
                    "signed updater manifest entry for {} {} ({}) has no {algorithm} digest",
                    self.component, self.version, self.artifact
                )
            })?;
        let expected_len = if algorithm == "sha256" { 64 } else { 128 };
        if digest.len() != expected_len || !digest.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(format!(
                "signed updater manifest entry for {} {} ({}) has a malformed {algorithm} digest",
                self.component, self.version, self.artifact
            ));
        }
        Ok(digest.to_ascii_lowercase())
    }
}

/// The signed manifest document. The signature covers the exact bytes
/// of the JSON file as published; parsing happens only after the
/// signature verifies, so field handling never has to be defensive
/// about unsigned input beyond ordinary shape errors.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct UpdateManifest {
    pub schema: u32,
    #[serde(default)]
    pub issued: String,
    pub updates: Vec<ApprovedUpdate>,
}

impl UpdateManifest {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        let manifest: UpdateManifest = serde_json::from_slice(bytes)
            .map_err(|error| format!("signed updater manifest is not valid JSON: {error}"))?;
        if manifest.schema != SUPPORTED_MANIFEST_SCHEMA {
            return Err(format!(
                "signed updater manifest schema {} is not supported by this build (expected {SUPPORTED_MANIFEST_SCHEMA})",
                manifest.schema
            ));
        }
        Ok(manifest)
    }

    /// Exactly one entry must approve the (component, version, artifact)
    /// being installed. Zero matches means the update was never approved;
    /// duplicates mean the manifest itself is ambiguous. Both refuse.
    pub fn find(
        &self,
        component: &str,
        version: &str,
        artifact: &str,
    ) -> Result<ApprovedUpdate, String> {
        let mut matches = self
            .updates
            .iter()
            .filter(|entry| {
                entry.component == component
                    && entry.version == version
                    && entry.artifact == artifact
            })
            .cloned();
        match (matches.next(), matches.next()) {
            (Some(entry), None) => Ok(entry),
            (None, _) => Err(format!(
                "signed updater manifest does not approve {component} {version} ({artifact})"
            )),
            (Some(_), Some(_)) => Err(format!(
                "signed updater manifest approves {component} {version} ({artifact}) more than once"
            )),
        }
    }
}

/// Parse every OpenPGP public certificate in a keyring blob (armored
/// or binary, one or several certificates). Unparseable entries are
/// skipped: callers fail closed when the usable set is empty, and one
/// corrupt entry must not hide a good one during a key overlap window.
/// Secret keys are never accepted as trust material and are dropped.
///
/// Parse armored certificates. A keyring file may carry several
/// certificates in one armor block (a single multi-key export) or as
/// several concatenated armor blocks (keyring-style append, which is
/// how an overlap anchor is written) — rPGP's armor iterator covers a
/// single block, so split blocks and parse each.
fn parse_armored_certs(text: &str) -> Vec<SignedPublicKey> {
    const BEGIN: &str = "-----BEGIN PGP PUBLIC KEY BLOCK-----";
    let mut certs = Vec::new();
    for piece in text.split(BEGIN).skip(1) {
        let block = format!("{BEGIN}{piece}");
        if let Ok((iter, _headers)) =
            SignedPublicKey::from_armor_many(std::io::Cursor::new(block.into_bytes()))
        {
            certs.extend(iter.flatten());
        }
    }
    certs
}

fn parse_certs(bytes: &[u8]) -> Vec<SignedPublicKey> {
    if bytes.is_empty() {
        return Vec::new();
    }
    let text = String::from_utf8_lossy(bytes);
    if text.contains("-----BEGIN PGP") {
        return parse_armored_certs(&text);
    }
    let Ok(iter) = SignedPublicKey::from_bytes_many(std::io::Cursor::new(bytes.to_vec())) else {
        return Vec::new();
    };
    iter.flatten().collect()
}

/// Certificates from the published key file whose primary key is one of
/// the baked-in anchors. The anchor pins the primary's fingerprint; the
/// fetched certificate supplies the primary's current signing subkeys,
/// which is what makes subkey rotation possible without an image
/// update. Anything else in the fetched file is ignored.
fn trusted_certs<'a>(
    anchors: &[SignedPublicKey],
    fetched: &'a [SignedPublicKey],
) -> Vec<&'a SignedPublicKey> {
    fetched
        .iter()
        .filter(|cert| {
            anchors
                .iter()
                .any(|anchor| anchor.fingerprint() == cert.fingerprint())
        })
        .collect()
}

/// Parse a detached signature (armored `.asc` as published, or raw
/// binary). Anything unparseable is an error: a missing or mangled
/// signature is a refusal, never a skip.
fn parse_signature(bytes: &[u8]) -> Result<DetachedSignature, String> {
    let text = String::from_utf8_lossy(bytes);
    if text.contains("-----BEGIN PGP") {
        let (signature, _) =
            DetachedSignature::from_armor_single(std::io::Cursor::new(bytes.to_vec()))
                .map_err(|error| format!("updater manifest signature is unparseable: {error}"))?;
        return Ok(signature);
    }
    DetachedSignature::from_bytes(std::io::Cursor::new(bytes.to_vec()))
        .map_err(|error| format!("updater manifest signature is unparseable: {error}"))
}

/// True when `signature` validates over `data` under `cert`'s primary
/// key or any of its public subkeys. The caller must already have
/// checked the certificate's self-signatures (`verify_bindings`): a
/// subkey only counts when the trusted primary actually bound it.
fn verifies_under(cert: &SignedPublicKey, signature: &DetachedSignature, data: &[u8]) -> bool {
    if signature.verify(cert, data).is_ok() {
        return true;
    }
    cert.public_subkeys
        .iter()
        .any(|subkey| signature.verify(subkey, data).is_ok())
}

/// Pure verification core: given the baked anchor keyring bytes, the
/// published key file bytes, and the manifest + detached signature
/// bytes, return the parsed manifest only if the signature verifies
/// under a certificate whose primary matches an anchor. Every other
/// outcome is an error (fail closed).
pub fn verify_signed_manifest(
    anchor_keyring: &[u8],
    published_keys: &[u8],
    manifest_bytes: &[u8],
    signature_bytes: &[u8],
) -> Result<UpdateManifest, String> {
    let anchors = parse_certs(anchor_keyring);
    if anchors.is_empty() {
        return Err(
            "no KythOS updater signing key is installed yet (the image still carries the \
             placeholder trust anchor), so no update can be verified"
                .to_string(),
        );
    }
    let fetched = parse_certs(published_keys);
    let trusted = trusted_certs(&anchors, &fetched);
    if trusted.is_empty() {
        return Err(
            "the published updater key file contains no certificate for the KythOS updater \
             signing key trusted by this image"
                .to_string(),
        );
    }
    let signature = parse_signature(signature_bytes)?;
    // A certificate counts only with intact self-signatures: the
    // subkey binding signatures are what stop a substituted subkey
    // riding on the (public) primary key. Then the detached signature
    // itself must validate under the primary or a bound subkey —
    // rPGP's signature check also enforces issuer identity and hash
    // strength.
    let verified = trusted.iter().any(|cert| {
        cert.verify_bindings().is_ok() && verifies_under(cert, &signature, manifest_bytes)
    });
    if !verified {
        return Err(
            "manifest signature did not validate against the trusted KythOS updater signing key"
                .to_string(),
        );
    }
    UpdateManifest::parse(manifest_bytes)
}

/// Full updater gate: fetch the signed manifest, its detached
/// signature, and the published key file; verify the signature against
/// the image-baked trust anchor; return the single manifest entry
/// approving (component, version, artifact). Any failure is an error
/// and the caller must refuse the install.
pub fn approve_update(
    run: &dyn for<'x> Fn(&'x [String], u64) -> Option<(i32, String)>,
    work: &Path,
    component: &str,
    version: &str,
    artifact: &str,
) -> Result<ApprovedUpdate, String> {
    let anchor_path = keyring_path();
    let anchor_bytes = std::fs::read(&anchor_path).map_err(|error| {
        format!(
            "cannot read the KythOS updater signing trust anchor at {}: {error}",
            anchor_path.display()
        )
    })?;
    if parse_certs(&anchor_bytes).is_empty() {
        return Err(
            "no KythOS updater signing key is installed yet (the image still carries the \
             placeholder trust anchor), so no update can be verified"
                .to_string(),
        );
    }
    let manifest_name = MANIFEST_FILENAME;
    let signature_name = format!("{MANIFEST_FILENAME}.asc");
    let keys_name = KEYS_FILENAME;
    let manifest_dest = work.join(&manifest_name);
    let signature_dest = work.join(&signature_name);
    let keys_dest = work.join(&keys_name);
    let headers = BTreeMap::new();
    for (url, dest) in [
        (manifest_url(), &manifest_dest),
        (signature_url(), &signature_dest),
        (keys_url(), &keys_dest),
    ] {
        download_file(run, &url, dest, &headers, 60, MAX_CHECKSUM_BYTES)
            .map_err(|error| format!("cannot fetch the signed updater manifest set: {error}"))?;
    }
    let manifest_bytes = std::fs::read(&manifest_dest)
        .map_err(|error| format!("cannot read the downloaded updater manifest: {error}"))?;
    let signature_bytes = std::fs::read(&signature_dest)
        .map_err(|error| format!("cannot read the downloaded manifest signature: {error}"))?;
    let published_keys = std::fs::read(&keys_dest)
        .map_err(|error| format!("cannot read the published updater key file: {error}"))?;
    let manifest = verify_signed_manifest(
        &anchor_bytes,
        &published_keys,
        &manifest_bytes,
        &signature_bytes,
    )?;
    manifest.find(component, version, artifact)
}

/// Second half of the gate: the downloaded artifact must hash to the
/// digest the signed manifest pinned for it. This runs IN ADDITION TO
/// the updaters' existing upstream checksum verification — the upstream
/// checksum proves the download matches the release page; this proves
/// the artifact is the one the KythOS signing key approved.
pub fn verify_artifact_matches(
    entry: &ApprovedUpdate,
    algorithm: &str,
    artifact_path: &Path,
) -> Result<(), String> {
    let expected = entry.expected_digest(algorithm)?;
    let actual = digest_file_hex(algorithm, artifact_path)?;
    if actual != expected {
        return Err(format!(
            "{algorithm} digest of {} does not match the signed updater manifest: expected {expected}, got {actual}",
            artifact_path.display()
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use pgp::composed::{
        ArmorOptions, KeyType, SecretKeyParamsBuilder, SignedSecretKey, SubkeyParamsBuilder,
    };
    use pgp::crypto::hash::HashAlgorithm;
    use pgp::types::{KeyVersion, Password};
    use rand::SeedableRng;

    const MANIFEST_JSON: &[u8] = br#"{
        "schema": 1,
        "issued": "2026-10-19T00:00:00Z",
        "updates": [
            {"component": "rclone", "version": "v1.68.2",
             "artifact": "rclone-v1.68.2-linux-amd64.zip",
             "sha256": "abababababababababababababababababababababababababababababababab"},
            {"component": "ge-proton", "version": "GE-Proton10-15",
             "artifact": "GE-Proton10-15-x86_64.tar.gz",
             "sha512": "cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd"}
        ]
    }"#;

    /// Throwaway secret key in the approved layout — a primary plus
    /// `signing_subkeys` signing subkeys — generated inside the test
    /// run and discarded with it. Never production key material.
    fn generate_secret(signing_subkeys: usize, seed: u64) -> SignedSecretKey {
        // Distinct seeds per test key: Ed25519 generation is
        // deterministic in the RNG stream, so reusing one seed would
        // produce byte-identical "different" keys.
        let mut rng = rand::rngs::StdRng::seed_from_u64(seed);
        let mut params = SecretKeyParamsBuilder::default();
        params
            .version(KeyVersion::V4)
            .key_type(KeyType::Ed25519)
            .can_certify(true)
            .can_sign(true)
            .primary_user_id("KythOS Updater Signing (throwaway test key)".to_string());
        for _ in 0..signing_subkeys {
            let subkey = SubkeyParamsBuilder::default()
                .version(KeyVersion::V4)
                .key_type(KeyType::Ed25519)
                .can_sign(true)
                .build()
                .expect("build throwaway subkey params");
            params.subkey(subkey);
        }
        params
            .build()
            .expect("build throwaway key params")
            .generate(&mut rng)
            .expect("generate throwaway test key")
    }

    fn armored(secret: &SignedSecretKey) -> Vec<u8> {
        secret
            .to_public_key()
            .to_armored_bytes(ArmorOptions::default())
            .expect("export throwaway test cert")
    }

    /// Detached armored signature over `data`, made by the `nth`
    /// secret signing subkey (0-based) of `secret`.
    fn sign_with_subkey(secret: &SignedSecretKey, nth: usize, data: &[u8]) -> Vec<u8> {
        let mut rng = rand::rngs::StdRng::seed_from_u64(0x5349_4755_4B59);
        let subkey = secret
            .secret_subkeys
            .get(nth)
            .expect("test key has the requested signing subkey");
        DetachedSignature::sign_binary_data(
            &mut rng,
            &subkey.key,
            &Password::empty(),
            HashAlgorithm::Sha256,
            std::io::Cursor::new(data.to_vec()),
        )
        .expect("sign test data")
        .to_armored_bytes(ArmorOptions::default())
        .expect("armor test signature")
    }

    #[test]
    fn valid_signature_unlocks_matching_entry() {
        let cert = generate_secret(1, 0xA11CE);
        let keyring = armored(&cert);
        let signature = sign_with_subkey(&cert, 0, MANIFEST_JSON);
        let manifest = verify_signed_manifest(&keyring, &keyring, MANIFEST_JSON, &signature)
            .expect("valid signature must verify");
        let entry = manifest
            .find("rclone", "v1.68.2", "rclone-v1.68.2-linux-amd64.zip")
            .expect("approved rclone entry must be found");
        assert_eq!(entry.component, COMPONENT_RCLONE);
        let proton = manifest
            .find(
                "ge-proton",
                "GE-Proton10-15",
                "GE-Proton10-15-x86_64.tar.gz",
            )
            .expect("approved GE-Proton entry must be found");
        assert_eq!(proton.component, COMPONENT_GE_PROTON);
    }

    #[test]
    fn tampered_manifest_is_refused() {
        let cert = generate_secret(1, 0xA11CE);
        let keyring = armored(&cert);
        let signature = sign_with_subkey(&cert, 0, MANIFEST_JSON);
        let mut tampered = MANIFEST_JSON.to_vec();
        tampered[20] ^= 0x01;
        let error = verify_signed_manifest(&keyring, &keyring, &tampered, &signature)
            .expect_err("a tampered manifest must not verify");
        assert!(error.contains("signature"), "unexpected error: {error}");
    }

    #[test]
    fn signature_from_unrelated_key_is_refused() {
        let trusted = generate_secret(1, 0xA11CE);
        let attacker = generate_secret(1, 0xBAD5EED);
        let keyring = armored(&trusted);
        // The attacker publishes their own certificate and signs with
        // it: cryptographically self-consistent, but the primary is
        // not the baked-in anchor, so it must be refused.
        let attacker_keyring = armored(&attacker);
        let signature = sign_with_subkey(&attacker, 0, MANIFEST_JSON);
        let error = verify_signed_manifest(&keyring, &attacker_keyring, MANIFEST_JSON, &signature)
            .expect_err("an unanchored primary must not verify");
        assert!(
            error.contains("no certificate"),
            "unexpected error: {error}"
        );
    }

    #[test]
    fn missing_signature_is_refused() {
        let cert = generate_secret(1, 0xA11CE);
        let keyring = armored(&cert);
        let error = verify_signed_manifest(&keyring, &keyring, MANIFEST_JSON, b"not a signature")
            .expect_err("garbage instead of a signature must not verify");
        assert!(!error.is_empty());
        let error = verify_signed_manifest(&keyring, &keyring, MANIFEST_JSON, b"")
            .expect_err("an absent signature must not verify");
        assert!(!error.is_empty());
    }

    #[test]
    fn placeholder_anchor_is_refused_with_named_reason() {
        let cert = generate_secret(1, 0xA11CE);
        let keyring = armored(&cert);
        let signature = sign_with_subkey(&cert, 0, MANIFEST_JSON);
        let placeholder: &[u8] = b"# KythOS updater signing keys\n\
            # PLACEHOLDER: no production key has been installed yet.\n";
        let error = verify_signed_manifest(placeholder, &keyring, MANIFEST_JSON, &signature)
            .expect_err("a placeholder anchor must refuse every update");
        assert!(
            error.contains("placeholder"),
            "error must name the placeholder state: {error}"
        );
        let error = verify_signed_manifest(b"", &keyring, MANIFEST_JSON, &signature)
            .expect_err("an empty anchor must refuse every update");
        assert!(error.contains("placeholder"), "unexpected error: {error}");
    }

    #[test]
    fn unapproved_version_is_refused() {
        let cert = generate_secret(1, 0xA11CE);
        let keyring = armored(&cert);
        let signature = sign_with_subkey(&cert, 0, MANIFEST_JSON);
        let manifest = verify_signed_manifest(&keyring, &keyring, MANIFEST_JSON, &signature)
            .expect("valid signature must verify");
        // Signature valid; approval absent. This is the fail-closed
        // path for a brand-new upstream release that no signed
        // manifest has approved yet.
        let error = manifest
            .find("rclone", "v9.99.9", "rclone-v9.99.9-linux-amd64.zip")
            .expect_err("an unapproved version must be refused");
        assert!(
            error.contains("does not approve"),
            "unexpected error: {error}"
        );
        let error = manifest
            .find(
                "ge-proton",
                "GE-Proton10-15",
                "GE-Proton10-15-aarch64.tar.gz",
            )
            .expect_err("an unapproved artifact name must be refused");
        assert!(error.contains("does not approve"));
    }

    #[test]
    fn rotated_signing_subkey_verifies_against_same_primary_anchor() {
        // Rotation semantics from the decision: the image anchors the
        // primary; any signing subkey bound to that primary is
        // accepted, so a fresh subkey verifies with no image change.
        let cert = generate_secret(2, 0xA11CE);
        let keyring = armored(&cert);
        let signature = sign_with_subkey(&cert, 1, MANIFEST_JSON);
        verify_signed_manifest(&keyring, &keyring, MANIFEST_JSON, &signature)
            .expect("a signature from the rotated-in subkey must verify");
    }

    #[test]
    fn overlapping_primaries_in_anchor_both_verify() {
        // Primary-rotation overlap: the anchor may carry the old and
        // the new primary at once; a manifest signed by either counts.
        let old = generate_secret(1, 0xA11CE);
        let new = generate_secret(1, 0xB0B);
        let mut anchor = armored(&old);
        anchor.extend_from_slice(&armored(&new));
        let published = armored(&new);
        let signature = sign_with_subkey(&new, 0, MANIFEST_JSON);
        verify_signed_manifest(&anchor, &published, MANIFEST_JSON, &signature)
            .expect("the incoming primary in an overlap anchor must verify");
    }

    #[test]
    fn artifact_digest_must_match_manifest_pin() {
        let dir = tempfile::tempdir().expect("tempdir");
        let artifact = dir.path().join("payload.bin");
        std::fs::write(&artifact, b"kyth test payload").expect("write artifact");
        let base = ApprovedUpdate {
            component: "rclone".to_string(),
            version: "v1.68.2".to_string(),
            artifact: "payload.bin".to_string(),
            sha256: None,
            sha512: None,
        };
        let real = digest_file_hex("sha256", &artifact).expect("hash artifact");
        let matching = ApprovedUpdate {
            sha256: Some(real),
            ..base.clone()
        };
        verify_artifact_matches(&matching, "sha256", &artifact).expect("matching digest must pass");
        let wrong = ApprovedUpdate {
            sha256: Some("00".repeat(32)),
            ..base.clone()
        };
        let error = verify_artifact_matches(&wrong, "sha256", &artifact)
            .expect_err("a mismatched digest must be refused");
        assert!(
            error.contains("does not match"),
            "unexpected error: {error}"
        );
        let error = verify_artifact_matches(&base, "sha256", &artifact)
            .expect_err("an entry without the needed digest must be refused");
        assert!(
            error.contains("no sha256 digest"),
            "unexpected error: {error}"
        );
    }

    #[test]
    fn unknown_manifest_schema_is_refused() {
        let error = UpdateManifest::parse(br#"{"schema": 99, "updates": []}"#)
            .expect_err("an unknown schema must fail closed");
        assert!(error.contains("not supported"), "unexpected error: {error}");
    }
}
