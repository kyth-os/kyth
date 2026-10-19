"""Contract tests for the KythOS-signed updater manifest gate.

The signature verification itself is covered by Rust unit tests in
src/kyth-shared-rs/src/system/update_manifest.rs (throwaway keys
generated in-run). These tests pin the wiring: both runtime updaters
gate on the signed manifest in addition to their upstream checksum
checks, the trust anchor ships as a key-free placeholder installed to
the path the verifier reads, and the release flow's manifest generator
never signs anything itself.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_RS = ROOT / "src/kyth-shared-rs/src/system/update_manifest.rs"
RCLONE_BIN = ROOT / "src/kyth-shared-rs/src/rclone_update_bin.rs"
PROTON_BIN = ROOT / "src/kyth-shared-rs/src/proton_cachyos_update_bin.rs"
ANCHOR = ROOT / "build_files/config/updater-signing-keys.asc"
FRAGMENT = ROOT / "build_files/scripts/branding/99-updater-signing-key.sh"
GENERATOR = ROOT / "build_files/scripts/generate-updater-manifest.py"
DOC = ROOT / "docs/updater-signing.md"


class UpdaterSigningContractTests(unittest.TestCase):
    def test_verifier_module_is_registered_and_fail_closed(self):
        module = (ROOT / "src/kyth-shared-rs/src/system/mod.rs").read_text(encoding="utf-8")
        self.assertIn("pub mod update_manifest;", module)
        source = MANIFEST_RS.read_text(encoding="utf-8")
        for expected in (
            "pub fn verify_signed_manifest(",
            "pub fn approve_update(",
            "pub fn verify_artifact_matches(",
            "verify_bindings()",
            "SUPPORTED_MANIFEST_SCHEMA: u32 = 1",
            'DEFAULT_KEYRING_PATH: &str = "/usr/share/kyth/updater-signing-keys.asc"',
            'COMPONENT_RCLONE: &str = "rclone"',
            'COMPONENT_GE_PROTON: &str = "ge-proton"',
        ):
            self.assertIn(expected, source)
        # The placeholder anchor must refuse, never fall through.
        self.assertIn("placeholder trust anchor", source)
        self.assertIn("no KythOS updater signing key is installed yet", source)

    def test_verifier_regression_tests_cover_the_refusal_matrix(self):
        source = MANIFEST_RS.read_text(encoding="utf-8")
        for test_name in (
            "valid_signature_unlocks_matching_entry",
            "tampered_manifest_is_refused",
            "signature_from_unrelated_key_is_refused",
            "missing_signature_is_refused",
            "placeholder_anchor_is_refused_with_named_reason",
            "unapproved_version_is_refused",
            "rotated_signing_subkey_verifies_against_same_primary_anchor",
            "overlapping_primaries_in_anchor_both_verify",
            "artifact_digest_must_match_manifest_pin",
            "unknown_manifest_schema_is_refused",
        ):
            self.assertIn(f"fn {test_name}(", source)

    def test_rclone_updater_gates_before_download_and_after_checksum(self):
        source = RCLONE_BIN.read_text(encoding="utf-8")
        gate = source.index("update_manifest::approve_update(")
        self.assertIn("update_manifest::COMPONENT_RCLONE", source[gate:gate + 400])
        # Gate runs before the artifact download...
        self.assertLess(gate, source.index("rclone: downloading"))
        # ...and the manifest digest check runs after the pre-existing
        # upstream SHA256SUMS verification.
        upstream = source.index("verify_checksum_file(")
        manifest_digest = source.index("update_manifest::verify_artifact_matches(&approved, \"sha256\"")
        self.assertLess(upstream, manifest_digest)
        self.assertIn("ERROR: Signed update manifest check failed", source)

    def test_proton_updater_gates_before_cleanup_and_after_checksum(self):
        source = PROTON_BIN.read_text(encoding="utf-8")
        gate = source.index("update_manifest::approve_update(")
        self.assertIn("update_manifest::COMPONENT_GE_PROTON", source[gate:gate + 400])
        # Gate runs before the incomplete-install cleanup, so a refused
        # update cannot disturb the currently installed version.
        self.assertLess(gate, source.index("found incomplete"))
        upstream = source.index("verify_checksum_file(")
        manifest_digest = source.index("update_manifest::verify_artifact_matches(&approved", upstream)
        self.assertLess(upstream, manifest_digest)
        self.assertIn('"sha512"', source[manifest_digest:manifest_digest + 200])
        self.assertIn("Signed update manifest check failed", source)

    def test_anchor_placeholder_carries_no_key_material(self):
        anchor = ANCHOR.read_text(encoding="utf-8")
        self.assertIn("PLACEHOLDER", anchor)
        self.assertNotIn("BEGIN PGP PUBLIC KEY BLOCK", anchor)
        self.assertNotIn("BEGIN PGP PRIVATE KEY BLOCK", anchor)

    def test_fragment_installs_anchor_to_the_verifier_path(self):
        self.assertTrue(FRAGMENT.stat().st_mode & 0o111)
        source = FRAGMENT.read_text(encoding="utf-8")
        self.assertIn("/ctx/config/updater-signing-keys.asc", source)
        self.assertIn("/usr/share/kyth/updater-signing-keys.asc", source)

    def test_generator_produces_unsigned_manifest_and_never_signs(self):
        self.assertTrue(GENERATOR.stat().st_mode & 0o111)
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn('"schema": 1', source)
        self.assertIn('MANIFEST_FILENAME = "kyth-updater-manifest.json"', source)
        self.assertIn('KEYS_FILENAME = "kyth-updater-keys.asc"', source)
        for component in ('"rclone"', '"ge-proton"'):
            self.assertIn(component, source)
        # Signing is a printed manual step for the key owner's hardware,
        # never something this script performs.
        self.assertIn("gpg --armor --detach-sign", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)

    def test_doc_covers_ceremony_rotation_and_failure_semantics(self):
        doc = DOC.read_text(encoding="utf-8")
        for expected in (
            "Key ceremony",
            "Release flow",
            "Rotation",
            "Failure semantics",
            "fail closed",
            "/usr/share/kyth/updater-signing-keys.asc",
        ):
            self.assertIn(expected, doc)


if __name__ == "__main__":
    unittest.main()
