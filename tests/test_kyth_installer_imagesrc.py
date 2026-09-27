import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import imagesrc  # noqa: E402


class InstallerImageSourceTests(unittest.TestCase):
    def _oci_fixture(self, root: Path, *, target: str = imagesrc.TARGET_IMAGE,
                       source_image: str = "ghcr.io/kyth-os/kyth:testing") -> tuple[str, Path, Path]:
        manifest = b'{"schemaVersion":2}'
        digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
        blob = root / "blobs" / "sha256" / digest.split(":", 1)[1]
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(manifest)
        (root / "oci-layout").write_text(json.dumps({"imageLayoutVersion": "1.0.0"}))
        (root / "index.json").write_text(json.dumps({"manifests": [{
            "digest": digest,
            "annotations": {"org.opencontainers.image.ref.name": "latest"},
        }]}))
        bundle = root.parent / "bundle.json"
        bundle.write_text(json.dumps({
            "schema_version": 1,
            "digest": digest,
            "release_digest": digest,
            "source_image": source_image,
            "identity": "test-identity",
            "issuer": "https://token.actions.githubusercontent.com",
            "signatures": ["c2lnbmF0dXJlLW9uZQ=="],
        }))
        bundle_digest = "sha256:" + hashlib.sha256(bundle.read_bytes()).hexdigest()
        metadata = root.parent / "source.json"
        metadata.write_text(json.dumps({
            "schema_version": 1,
            "digest": digest,
            "release_digest": digest,
            "target_image": target,
            "source_image": source_image,
            "signature": "verified",
            "signature_digest": bundle_digest,
        }))
        return digest, metadata, bundle

    def test_network_preflight_skips_local_images(self):
        with mock.patch.object(imagesrc, "run_command") as run_command, \
             mock.patch.object(imagesrc.socket, "create_connection") as create_connection:
            result = imagesrc._network_preflight("containers-storage:localhost/kyth")

        self.assertIsNone(result)
        run_command.assert_not_called()
        create_connection.assert_not_called()

    def test_oci_layout_is_preserved_as_an_offline_source(self):
        source = "oci:/usr/share/kyth/image:latest"

        self.assertEqual(imagesrc._source_imgref(source), source)
        self.assertIsNone(imagesrc._network_preflight(source))

    def test_network_preflight_reports_missing_default_route(self):
        with mock.patch.object(imagesrc.socket, "getaddrinfo", return_value=[]), \
             mock.patch.object(imagesrc.socket, "create_connection", side_effect=OSError("network unreachable")):

            result = imagesrc._network_preflight("docker://ghcr.io/kyth-os/kyth:latest")

        self.assertIsInstance(result, str)
        self.assertIn("Connect", result)

    def test_install_images_returns_source_and_target_refs(self):
        image = "ghcr.io/kyth-os/kyth:testing"
        with mock.patch.object(imagesrc, "run_command") as run_command, \
             mock.patch.object(imagesrc, "SOURCE_IMAGE", image), \
             mock.patch.object(imagesrc, "TARGET_IMAGE", image):
            src, tgt = imagesrc._install_images("fedora")

        self.assertTrue(src.startswith("docker://"))
        self.assertEqual(tgt, "ghcr.io/kyth-os/kyth:testing")
        self.assertEqual(src, f"docker://{tgt}")
        run_command.assert_not_called()

    def test_source_imgref_empty_input_uses_default_source_image(self):
        self.assertEqual(imagesrc._source_imgref(""), imagesrc.SOURCE_IMAGE)

    def test_embedded_oci_manifest_is_verified_against_release_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            digest, metadata, bundle = self._oci_fixture(root)

            actual = imagesrc._verify_oci_source(
                f"oci:{root}:latest",
                expected_digest=digest,
                metadata_path=metadata,
                bundle_path=bundle,
            )

        self.assertEqual(actual, digest)

    def test_embedded_oci_digest_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            _digest, metadata, bundle = self._oci_fixture(root)

            with self.assertRaisesRegex(RuntimeError, "does not match"):
                imagesrc._verify_oci_source(
                    f"oci:{root}:latest",
                    expected_digest="sha256:" + "0" * 64,
                    metadata_path=metadata,
                    bundle_path=bundle,
                )

    def test_embedded_oci_release_digest_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            digest, metadata, bundle = self._oci_fixture(root)
            payload = json.loads(metadata.read_text())
            payload["release_digest"] = "sha256:" + "0" * 64
            metadata.write_text(json.dumps(payload))

            with self.assertRaisesRegex(RuntimeError, "release digest"):
                imagesrc._verify_oci_source(
                    f"oci:{root}:latest",
                    expected_digest=digest,
                    metadata_path=metadata,
                    bundle_path=bundle,
                )

    def test_embedded_oci_tampered_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            digest, metadata, bundle = self._oci_fixture(root)
            bundle.write_text(json.dumps({"schema_version": 1}))

            with self.assertRaisesRegex(RuntimeError, "signature"):
                imagesrc._verify_oci_source(
                    f"oci:{root}:latest",
                    expected_digest=digest,
                    metadata_path=metadata,
                    bundle_path=bundle,
                )

    def test_embedded_oci_unsigned_local_claim_requires_local_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            digest, metadata, bundle = self._oci_fixture(
                root, source_image="docker://localhost:5000/kyth:dev"
            )
            payload = json.loads(metadata.read_text())
            payload["signature"] = "local"
            payload["signature_digest"] = ""
            metadata.write_text(json.dumps(payload))
            actual = imagesrc._verify_oci_source(
                f"oci:{root}:latest",
                expected_digest=digest,
                metadata_path=metadata,
                bundle_path=bundle,
            )
            self.assertEqual(actual, digest)

            _digest, registry_metadata, registry_bundle = self._oci_fixture(root)
            payload = json.loads(registry_metadata.read_text())
            payload["signature"] = "local"
            payload["signature_digest"] = ""
            registry_metadata.write_text(json.dumps(payload))
            with self.assertRaisesRegex(RuntimeError, "unsigned local"):
                imagesrc._verify_oci_source(
                    f"oci:{root}:latest",
                    expected_digest=digest,
                    metadata_path=registry_metadata,
                    bundle_path=registry_bundle,
                )


class SignatureBundleUnitTests(unittest.TestCase):
    """Direct unit coverage for the cosign-bundle verification helpers."""

    def _write_bundle(self, directory: str, name: str, payload: object) -> Path:
        path = Path(directory) / name
        if isinstance(payload, bytes):
            path.write_bytes(payload)
        else:
            path.write_text(json.dumps(payload))
        return path

    def _verified_metadata(self, raw: bytes, source_image: str) -> dict:
        return {
            "signature": "verified",
            "signature_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "source_image": source_image,
        }

    def _bundle_bytes(self, digest: str, **overrides: object) -> bytes:
        payload = {
            "schema_version": 1,
            "digest": digest,
            "release_digest": digest,
            "signatures": ["c2lnbmF0dXJlLW9uZQ=="],
        }
        payload.update(overrides)
        return json.dumps(payload).encode("utf-8")

    def test_registry_source_detection(self):
        signed = imagesrc._registry_signed_source
        self.assertFalse(signed("oci:/usr/share/kyth/image"))
        self.assertFalse(signed("containers-storage:localhost/kyth"))
        self.assertFalse(signed("dir:/tmp/layout"))
        self.assertFalse(signed("ostree:default"))
        self.assertFalse(signed("docker://localhost:5000/kyth:dev"))
        self.assertFalse(signed("localhost/kyth:testing"))
        self.assertFalse(signed("127.0.0.1:5000/kyth:testing"))
        self.assertFalse(signed("[::1]:5000/kyth:testing"))
        self.assertTrue(signed("docker://ghcr.io/kyth-os/kyth:testing"))
        self.assertTrue(signed("ghcr.io/kyth-os/kyth:testing"))

    def test_base64_signature_shapes(self):
        valid = imagesrc._valid_base64_signature
        self.assertTrue(valid("c2lnbmF0dXJlLW9uZQ=="))
        self.assertFalse(valid(""))
        self.assertFalse(valid(None))
        self.assertFalse(valid(42))
        self.assertFalse(valid("x" * (128 * 1024 + 1)))
        self.assertFalse(valid("has spaces"))
        self.assertFalse(valid("unicode-\u00e9"))

    def test_local_state_accepts_loopback_source(self):
        metadata = {"signature": "local", "source_image": "docker://localhost:5000/kyth:dev"}
        imagesrc._verify_signature_bundle("sha256:abc", "sha256:abc", metadata)

    def test_unknown_signature_state_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "unknown signature state"):
            imagesrc._verify_signature_bundle("sha256:abc", "sha256:abc", {})
        with self.assertRaisesRegex(RuntimeError, "unknown signature state"):
            imagesrc._verify_signature_bundle(
                "sha256:abc", "sha256:abc", {"signature": "pending"}
            )

    def test_missing_bundle_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.json"
            metadata = self._verified_metadata(b"{}", "ghcr.io/x")
            with self.assertRaisesRegex(RuntimeError, "missing or unsafe"):
                imagesrc._verify_signature_bundle(
                    "sha256:abc", "sha256:abc", metadata, bundle_path=missing
                )

    def test_unreadable_bundle_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = self._write_bundle(directory, "bundle.json", {"schema_version": 1})
            raw = bundle.read_bytes()
            metadata = self._verified_metadata(raw, "ghcr.io/x")
            with (
                mock.patch.object(Path, "read_bytes", side_effect=OSError("denied")),
                self.assertRaisesRegex(RuntimeError, "could not read"),
            ):
                imagesrc._verify_signature_bundle(
                    "sha256:abc", "sha256:abc", metadata, bundle_path=bundle
                )

    def test_oversize_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = b"0" * (4 * 1024 * 1024 + 1)
            bundle = self._write_bundle(directory, "big.json", raw)
            metadata = self._verified_metadata(raw, "ghcr.io/x")
            with self.assertRaisesRegex(RuntimeError, "too large"):
                imagesrc._verify_signature_bundle(
                    "sha256:abc", "sha256:abc", metadata, bundle_path=bundle
                )

    def test_malformed_and_wrong_schema_bundles_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = self._write_bundle(directory, "bad.json", b"{nope")
            metadata = self._verified_metadata(b"{nope", "ghcr.io/x")
            with self.assertRaisesRegex(RuntimeError, "invalid"):
                imagesrc._verify_signature_bundle(
                    "sha256:abc", "sha256:abc", metadata, bundle_path=bad
                )
            raw = self._bundle_bytes("sha256:abc", schema_version=2)
            wrong = self._write_bundle(directory, "wrong.json", json.loads(raw))
            metadata = self._verified_metadata(raw, "ghcr.io/x")
            with self.assertRaisesRegex(RuntimeError, "unsupported schema"):
                imagesrc._verify_signature_bundle(
                    "sha256:abc", "sha256:abc", metadata, bundle_path=wrong
                )

    def test_digest_mismatch_and_missing_signatures_rejected(self):
        digest = "sha256:" + "a" * 64
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "schema_version": 1,
                "digest": "sha256:" + "b" * 64,
                "release_digest": digest,
                "signatures": ["c2lnbmF0dXJlLW9uZQ=="],
            }
            raw = json.dumps(payload).encode("utf-8")
            bundle = self._write_bundle(directory, "bundle.json", payload)
            metadata = self._verified_metadata(raw, "ghcr.io/x")
            with self.assertRaisesRegex(RuntimeError, "does not cover"):
                imagesrc._verify_signature_bundle(
                    digest, digest, metadata, bundle_path=bundle
                )
            raw = self._bundle_bytes(digest, signatures=[])
            unsigned = self._write_bundle(directory, "unsigned.json", json.loads(raw))
            metadata = self._verified_metadata(raw, "ghcr.io/x")
            with self.assertRaisesRegex(RuntimeError, "no verifiable signature"):
                imagesrc._verify_signature_bundle(
                    digest, digest, metadata, bundle_path=unsigned
                )


if __name__ == "__main__":
    unittest.main()
