import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import imagesrc  # noqa: E402


class InstallerImageSourceCoverageTests(unittest.TestCase):
    def setUp(self):
        imagesrc._SOURCE_STATUS_CACHE.clear()

    def _oci_fixture(self, root: Path, *, tag="latest", target=None):
        manifest = b'{"schemaVersion":2}'
        digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
        blob = root / "blobs" / "sha256" / digest.split(":", 1)[1]
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(manifest)
        (root / "oci-layout").write_text(json.dumps({"imageLayoutVersion": "1.0.0"}))
        (root / "index.json").write_text(json.dumps({"manifests": [{
            "digest": digest,
            "annotations": {"org.opencontainers.image.ref.name": tag},
        }]}))
        metadata = root.parent / "source.json"
        metadata.write_text(json.dumps({
            "schema_version": 1,
            "digest": digest,
            "target_image": target if target is not None else imagesrc.TARGET_IMAGE,
        }))
        return digest, metadata

    def test_oci_reference_parses_tag_and_defaults_latest(self):
        self.assertEqual(imagesrc._oci_layout_ref("oci:/images/kyth:stable"), (Path("/images/kyth"), "stable"))
        self.assertEqual(imagesrc._oci_layout_ref("oci:/images/kyth"), (Path("/images/kyth"), "latest"))
        self.assertEqual(imagesrc._oci_layout_ref("oci:/images/kyth:"), (Path("/images/kyth"), "latest"))

    def test_metadata_rejects_missing_invalid_and_unsupported_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            with self.assertRaisesRegex(RuntimeError, "missing or unsafe"):
                imagesrc._read_source_metadata(path)
            path.write_text("not-json")
            with self.assertRaisesRegex(RuntimeError, "could not read"):
                imagesrc._read_source_metadata(path)
            path.write_text(json.dumps({"schema_version": 2}))
            with self.assertRaisesRegex(RuntimeError, "unsupported schema"):
                imagesrc._read_source_metadata(path)

    def test_oci_verification_rejects_layout_manifest_and_target_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            digest, metadata = self._oci_fixture(root)
            (root / "oci-layout").write_text(json.dumps({"imageLayoutVersion": "0.9.0"}))
            with self.assertRaisesRegex(RuntimeError, "layout version"):
                imagesrc._verify_oci_source(f"oci:{root}", expected_digest=digest, metadata_path=metadata)

            self._oci_fixture(root)
            (root / "index.json").write_text(json.dumps({"manifests": []}))
            with self.assertRaisesRegex(RuntimeError, "no valid manifest digest"):
                imagesrc._verify_oci_source(f"oci:{root}", expected_digest=digest, metadata_path=metadata)

            digest, metadata = self._oci_fixture(root, target="different/image")
            with self.assertRaisesRegex(RuntimeError, "update target"):
                imagesrc._verify_oci_source(f"oci:{root}", expected_digest=digest, metadata_path=metadata)

    def test_oci_verification_rejects_missing_and_modified_manifest_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            digest, metadata = self._oci_fixture(root)
            blob = root / "blobs" / "sha256" / digest.split(":", 1)[1]
            blob.unlink()
            with self.assertRaisesRegex(RuntimeError, "blob is missing"):
                imagesrc._verify_oci_source(f"oci:{root}", expected_digest=digest, metadata_path=metadata)
            blob.write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "integrity check"):
                imagesrc._verify_oci_source(f"oci:{root}", expected_digest=digest, metadata_path=metadata)

    def test_network_preflight_reports_route_dns_and_connection_failures(self):
        route = SimpleNamespace(returncode=1, stdout="")
        with mock.patch.object(imagesrc, "run_command", return_value=route):
            self.assertIn("default network route", imagesrc._network_preflight("docker://registry/image"))

        route = SimpleNamespace(returncode=0, stdout="default via 1.2.3.4")
        with mock.patch.object(imagesrc, "run_command", return_value=route), mock.patch.object(
            imagesrc.socket, "getaddrinfo", side_effect=imagesrc.socket.gaierror
        ):
            self.assertIn("not resolving", imagesrc._network_preflight("docker://registry/image"))

        with mock.patch.object(imagesrc, "run_command", return_value=route), mock.patch.object(
            imagesrc.socket, "getaddrinfo", return_value=[]
        ), mock.patch.object(imagesrc.socket, "create_connection", side_effect=OSError):
            self.assertIn("cannot reach", imagesrc._network_preflight("docker://registry/image"))

    def test_network_preflight_allows_reachable_registry_after_route_probe_error(self):
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        with mock.patch.object(imagesrc, "run_command", side_effect=OSError), mock.patch.object(
            imagesrc.socket, "getaddrinfo", return_value=[]
        ), mock.patch.object(imagesrc.socket, "create_connection", return_value=connection):
            self.assertIsNone(imagesrc._network_preflight("docker://registry/image"))

    def test_cachy_image_derivation_normalizes_existing_suffix_and_latest(self):
        with mock.patch.object(imagesrc, "TARGET_IMAGE", "registry/kyth:testing-cachy"):
            self.assertEqual(
                imagesrc._install_images("cachy"),
                ("docker://registry/kyth:testing-cachy", "registry/kyth:testing-cachy"),
            )
        with mock.patch.object(imagesrc, "TARGET_IMAGE", "registry/kyth"):
            self.assertEqual(imagesrc._install_images("cachy")[1], "registry/kyth:latest-cachy")

    def test_source_resolution_classifies_embedded_local_and_network(self):
        with mock.patch.object(imagesrc, "_verify_oci_source", return_value="sha256:verified"):
            embedded = imagesrc.resolve_source_refs("oci:/image", "target")
        with mock.patch.object(imagesrc, "SOURCE_DIGEST", "sha256:pinned"):
            local = imagesrc.resolve_source_refs("containers-storage:image", "target")
            network = imagesrc.resolve_source_refs("docker://registry/image", "target")
        self.assertEqual((embedded.kind, embedded.verified), ("embedded", True))
        self.assertEqual((local.kind, local.verified), ("local", True))
        self.assertEqual((network.kind, network.requires_network), ("network", True))

    def test_source_status_caches_success_but_not_failures(self):
        source = imagesrc.ImageSource("docker://registry/image", "target", "network")
        with mock.patch.object(imagesrc, "resolve_install_source", return_value=source) as resolve:
            first = imagesrc.source_status("fedora")
            second = imagesrc.source_status("fedora")
        self.assertIs(first, second)
        resolve.assert_called_once()
        self.assertEqual(first["message"], "Network image selected")

        imagesrc._SOURCE_STATUS_CACHE.clear()
        with mock.patch.object(imagesrc, "resolve_install_source", side_effect=RuntimeError("invalid image")):
            failed = imagesrc.source_status("fedora")
        self.assertFalse(failed["available"])
        self.assertIn("invalid image", failed["message"])


if __name__ == "__main__":
    unittest.main()
