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
    _bootc_cancel_block_reason,
    _branch_from_ref,
    _branch_display_name,
    _default_phase,
    _parse_update_phase,
)
from kyth_welcome.services.process import (  # noqa: E402
    _format_dl_progress_line,
    _format_elapsed,
    _format_eta,
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

    def test_format_elapsed(self):
        self.assertEqual(_format_elapsed(45), "45s")
        self.assertEqual(_format_elapsed(65), "1m 05s")

    def test_format_eta(self):
        self.assertEqual(_format_eta(0), "")
        self.assertEqual(_format_eta(45), "~45s remaining")
        self.assertEqual(_format_eta(125), "~2m 05s remaining")

    def test_format_dl_progress_line(self):
        line = _format_dl_progress_line(512 * 1024, 2 * 1024**2, 300_000, 30)
        self.assertIn("/", line)
        self.assertIn(f"{_human_bytes(300_000)}/s", line)
        self.assertIn("~30s remaining", line)


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


class UpdatePhaseParsingTests(unittest.TestCase):
    """page_update_ops.py's status label and cancel-safety gating both come
    from these pure functions — drives the Update page's progress display and,
    more importantly, decides when it's no longer safe to let a user cancel
    (once bootc has started writing/staging the new image)."""

    def test_default_phase_per_mode(self):
        self.assertEqual(_default_phase("update"), "Pulling OS image from container registry…")
        self.assertEqual(_default_phase("full-update"), "Running full system update…")
        self.assertEqual(_default_phase("rollback"), "Staging rollback deployment…")
        self.assertEqual(_default_phase("unknown-mode"), "Operation in progress…")

    def test_parse_update_phase_recognizes_known_lines(self):
        cases = [
            ("Pulling sha256:abcdef from ghcr.io", "Downloading image layers…"),
            ("Unpacking layer 3/5", "Unpacking image layers…"),
            ("Checking out tree onto filesystem", "Importing image into system storage…"),
            ("Writing manifest to image destination", "Storing image manifest…"),
            ("Composing final image", "Writing new OS image to disk…"),
            ("rpmdb: verifying package database", "Updating package database in the new image…"),
            ("Generating initramfs for kernel 6.x", "Preparing boot files for the new image…"),
            ("Deploying commit abc123", "Deploying new OS image…"),
            ("Transaction complete", "Staging new image for next reboot…"),
            ("No update available.", "Already on the latest image — nothing to download."),
        ]
        for line, expected in cases:
            self.assertEqual(_parse_update_phase(line, "update"), expected, msg=line)

    def test_parse_update_phase_returns_none_for_unrecognized_line(self):
        self.assertIsNone(_parse_update_phase("some unrelated log noise", "update"))

    def test_parse_update_phase_full_update_section_header(self):
        line = "―― 12:34:01 - Flatpaks ――"
        self.assertEqual(
            _parse_update_phase(line, "full-update"),
            "Updating Flatpaks…",
        )
        # The same section-header format is only meaningful in full-update mode.
        self.assertIsNone(_parse_update_phase(line, "update"))

    def test_cancel_blocked_once_writing_or_staging(self):
        for phase in (
            "Unpacking image layers…",
            "Writing new OS image to disk…",
            "Staging new image for next reboot…",
        ):
            self.assertNotEqual(_bootc_cancel_block_reason("update", phase), "")

    def test_cancel_allowed_while_still_downloading(self):
        self.assertEqual(_bootc_cancel_block_reason("update", "Downloading image layers…"), "")
        self.assertEqual(_bootc_cancel_block_reason("update", "Resolving OS image version…"), "")

    def test_rollback_never_cancellable(self):
        # Rollback has no safe early phase to cancel from at all.
        self.assertNotEqual(_bootc_cancel_block_reason("rollback", "Staging rollback deployment…"), "")
        self.assertNotEqual(_bootc_cancel_block_reason("rollback", ""), "")


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
