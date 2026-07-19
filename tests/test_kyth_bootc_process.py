"""Pure process/bootc/registry helpers (no Qt)."""
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.bootc import (  # noqa: E402
    REGISTRY,
    image_digest_from_status,
    image_reference_from_status,
    _branch_from_ref,
    _branch_display_name,
)
from kyth_welcome.services.process import (  # noqa: E402
    _human_bytes,
    _human_bytes_pair,
    _parse_size_bytes,
)
from kyth_welcome.services.registry import (  # noqa: E402
    check_registry_update,
)


class ProcessHelpersTests(unittest.TestCase):
    def test_human_bytes(self):
        self.assertEqual(_human_bytes(500), "500 B")
        self.assertEqual(_human_bytes(2048), "2.0 KB")
        self.assertEqual(_human_bytes(5 * 1024**2), "5.0 MB")

    def test_human_bytes_pair_shares_unit(self):
        down, total = _human_bytes_pair(512 * 1024, 2 * 1024**2)
        self.assertTrue(total.endswith("MB"))
        self.assertIn(".", down)

    def test_parse_size_bytes(self):
        self.assertEqual(_parse_size_bytes("8.0 GB"), 8 * 1024**3)
        self.assertEqual(_parse_size_bytes("bad"), 0)


class BootcHelpersTests(unittest.TestCase):
    def test_image_reference_from_status_nested(self):
        status = {
            "status": {
                "booted": {
                    "image": {"reference": f"{REGISTRY}:testing"},
                }
            }
        }
        self.assertEqual(
            image_reference_from_status(status),
            f"{REGISTRY}:testing",
        )

    def test_image_reference_from_status_spec_fallback(self):
        status = {"spec": {"image": {"image": f"{REGISTRY}:latest"}}}
        self.assertEqual(
            image_reference_from_status(status),
            f"{REGISTRY}:latest",
        )

    def test_image_digest_from_status(self):
        digest = "sha256:" + "a" * 64
        status = {"status": {"booted": {"image": {"imageDigest": digest}}}}
        self.assertEqual(image_digest_from_status(status, "booted"), digest)
        self.assertIsNone(image_digest_from_status(status, "staged"))

    def test_branch_helpers(self):
        self.assertEqual(_branch_from_ref(f"{REGISTRY}:testing-cachy"), "testing-cachy")
        self.assertEqual(_branch_display_name("latest"), "Stable (latest)")
        self.assertEqual(_branch_display_name("testing"), "Testing")


class RegistrySharedTests(unittest.TestCase):
    def test_check_registry_update_available(self):
        local = "sha256:" + "1" * 64
        remote = "sha256:" + "2" * 64
        status = {"status": {"booted": {"image": {"imageDigest": local}}}}
        manifest = {
            "manifests": [
                {
                    "digest": remote,
                    "platform": {"architecture": "amd64", "os": "linux"},
                }
            ]
        }

        def runner(ref):
            self.assertEqual(ref, f"{REGISTRY}:latest")
            return subprocess.CompletedProcess([], 0, __import__("json").dumps(manifest).encode(), b"")

        result = check_registry_update(
            status_data=status,
            branch="latest",
            registry=REGISTRY,
            inspect_runner=runner,
        )
        self.assertEqual(result.state, "available")


if __name__ == "__main__":
    unittest.main()
