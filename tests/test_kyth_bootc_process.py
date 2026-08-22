"""Pure process/bootc/registry helpers (no Qt)."""
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import mock_open, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.system.bootc import (  # noqa: E402
    REGISTRY,
    image_digest_from_status,
    image_reference_from_status,
    bootc_cancel_block_reason,
    branch_from_ref,
    branch_display_name,
    branches_view,
    current_kernel_flavor,
    default_phase,
    image_tag_for_channel,
    image_tag_for_kernel,
    parse_update_phase,
    update_availability_view,
)
from kyth_shared.system.process import (  # noqa: E402
    format_dl_progress_line,
    format_elapsed,
    format_eta,
    human_bytes,
    human_bytes_pair,
    parse_size_bytes,
)
from kyth_shared.system.registry import (  # noqa: E402
    check_registry_update,
)
from kyth_shared.system import bootc_policy, bootc_query  # noqa: E402


class ProcessHelpersTests(unittest.TestCase):
    def test_human_bytes(self):
        self.assertEqual(human_bytes(500), "500 B")
        self.assertEqual(human_bytes(2048), "2.0 KB")
        self.assertEqual(human_bytes(5 * 1024**2), "5.0 MB")

    def test_human_bytes_pair_shares_unit(self):
        down, total = human_bytes_pair(512 * 1024, 2 * 1024**2)
        self.assertTrue(total.endswith("MB"))
        self.assertIn(".", down)

    def test_parse_size_bytes(self):
        self.assertEqual(parse_size_bytes("8.0 GB"), 8 * 1024**3)
        self.assertEqual(parse_size_bytes("bad"), 0)

    def test_format_elapsed(self):
        self.assertEqual(format_elapsed(45), "45s")
        self.assertEqual(format_elapsed(65), "1m 05s")

    def test_format_eta(self):
        self.assertEqual(format_eta(0), "")
        self.assertEqual(format_eta(45), "~45s remaining")
        self.assertEqual(format_eta(125), "~2m 05s remaining")

    def test_format_dl_progress_line(self):
        line = format_dl_progress_line(512 * 1024, 2 * 1024**2, 300_000, 30)
        self.assertIn("/", line)
        self.assertIn(f"{human_bytes(300_000)}/s", line)
        self.assertIn("~30s remaining", line)


class BootcHelpersTests(unittest.TestCase):
    def test_query_parser_is_independent_from_command_execution(self):
        status = {
            "status": {
                "booted": {"image": {"reference": f"{REGISTRY}:testing"}},
            },
        }
        self.assertEqual(
            bootc_query.image_reference_from_status(status),
            f"{REGISTRY}:testing",
        )

    def test_policy_layer_computes_kernel_target_without_probing(self):
        self.assertEqual(
            bootc_policy.image_tag_for_kernel("cachy", "testing"),
            "testing-cachy",
        )

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
        self.assertEqual(branch_from_ref(f"{REGISTRY}:testing-cachy"), "testing-cachy")
        self.assertEqual(branch_display_name("latest"), "Stable (latest)")
        self.assertEqual(branch_display_name("testing"), "Testing")


class KernelFlavorTests(unittest.TestCase):
    """page_kernel.py's current-kernel label and switch-target image tag both
    come from these functions. probe_cached is bypassed (call fetch directly)
    so tests exercise the fetch logic itself rather than a shared, ordering-
    sensitive in-memory cache."""

    def _fetch_flavor(self, file_content=None, file_error=False, uname="6.1.0-300.fc44.x86_64"):
        open_patch = (
            patch("builtins.open", side_effect=OSError("no such file"))
            if file_error
            else patch("builtins.open", mock_open(read_data=file_content))
        )
        with patch("kyth_shared.system.bootc.probe_cached", side_effect=lambda key, ttl, fetch: fetch()), \
             open_patch, \
             patch("kyth_shared.system.bootc.command_stdout", return_value=uname):
            return current_kernel_flavor()

    def test_flavor_from_marker_file(self):
        self.assertEqual(self._fetch_flavor(file_content="cachy\n"), "cachy")
        self.assertEqual(self._fetch_flavor(file_content="fedora\n"), "fedora")

    def test_flavor_falls_back_to_uname_when_marker_missing(self):
        self.assertEqual(
            self._fetch_flavor(file_error=True, uname="6.1.0-300.cachy.fc44.x86_64"), "cachy",
        )
        self.assertEqual(
            self._fetch_flavor(file_error=True, uname="6.1.0-300.fc44.x86_64"), "fedora",
        )

    def test_flavor_falls_back_to_uname_when_marker_content_invalid(self):
        self.assertEqual(
            self._fetch_flavor(file_content="bogus\n", uname="6.1.0-300.cachy.fc44.x86_64"), "cachy",
        )

    def test_image_tag_for_channel(self):
        self.assertEqual(image_tag_for_channel("latest", flavor="fedora"), "latest")
        self.assertEqual(image_tag_for_channel("latest", flavor="cachy"), "latest-cachy")
        self.assertEqual(image_tag_for_channel("testing", flavor="fedora"), "testing")
        self.assertEqual(image_tag_for_channel("testing", flavor="cachy"), "testing-cachy")
        # Anything other than the literal "testing" channel name is treated as stable.
        self.assertEqual(image_tag_for_channel("unknown", flavor="fedora"), "latest")

    def test_image_tag_for_kernel(self):
        with patch("kyth_shared.system.bootc.current_branch", return_value="latest"):
            self.assertEqual(image_tag_for_kernel("fedora"), "latest")
            self.assertEqual(image_tag_for_kernel("cachy"), "latest-cachy")
        with patch("kyth_shared.system.bootc.current_branch", return_value="testing-cachy"):
            self.assertEqual(image_tag_for_kernel("fedora"), "testing")
            self.assertEqual(image_tag_for_kernel("cachy"), "testing-cachy")
        with patch("kyth_shared.system.bootc.current_branch", return_value=None):
            self.assertEqual(image_tag_for_kernel("fedora"), "latest")


class UpdatePhaseParsingTests(unittest.TestCase):
    """page_update_ops.py's status label and cancel-safety gating both come
    from these pure functions — drives the Update page's progress display and,
    more importantly, decides when it's no longer safe to let a user cancel
    (once bootc has started writing/staging the new image)."""

    def test_default_phase_per_mode(self):
        self.assertEqual(default_phase("update"), "Pulling OS image from container registry…")
        self.assertEqual(default_phase("full-update"), "Running full system update…")
        self.assertEqual(default_phase("rollback"), "Staging rollback deployment…")
        self.assertEqual(default_phase("unknown-mode"), "Operation in progress…")

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
            self.assertEqual(parse_update_phase(line, "update"), expected, msg=line)

    def test_parse_update_phase_returns_none_for_unrecognized_line(self):
        self.assertIsNone(parse_update_phase("some unrelated log noise", "update"))

    def test_parse_update_phase_full_update_section_header(self):
        line = "―― 12:34:01 - Flatpaks ――"
        self.assertEqual(
            parse_update_phase(line, "full-update"),
            "Updating Flatpaks…",
        )
        # The same section-header format is only meaningful in full-update mode.
        self.assertIsNone(parse_update_phase(line, "update"))

    def test_cancel_blocked_once_writing_or_staging(self):
        for phase in (
            "Unpacking image layers…",
            "Writing new OS image to disk…",
            "Staging new image for next reboot…",
        ):
            self.assertNotEqual(bootc_cancel_block_reason("update", phase), "")

    def test_cancel_allowed_while_still_downloading(self):
        self.assertEqual(bootc_cancel_block_reason("update", "Downloading image layers…"), "")
        self.assertEqual(bootc_cancel_block_reason("update", "Resolving OS image version…"), "")

    def test_rollback_never_cancellable(self):
        # Rollback has no safe early phase to cancel from at all.
        self.assertNotEqual(bootc_cancel_block_reason("rollback", "Staging rollback deployment…"), "")
        self.assertNotEqual(bootc_cancel_block_reason("rollback", ""), "")


class BranchesViewTests(unittest.TestCase):
    """page_branches.py's Stable/Testing selector cards are driven entirely
    by this decision tree — no Qt, so it's testable directly."""

    def test_on_stable_marks_stable_active(self):
        view = branches_view("latest", "2026-07-20")
        self.assertEqual(view.stable.object_name, "branch-active")
        self.assertEqual(view.stable.button_text, "On Stable  (current)")
        self.assertIn("built 2026-07-20", view.stable.build_label_text)
        self.assertTrue(view.stable.build_label_visible)
        self.assertEqual(view.testing.object_name, "branch-inactive")
        self.assertEqual(view.testing.button_text, "Switch to Testing")
        self.assertFalse(view.testing.build_label_visible)

    def test_on_stable_cachy_flavor_also_marks_stable_active(self):
        view = branches_view("latest-cachy", "2026-07-20")
        self.assertEqual(view.stable.object_name, "branch-active")

    def test_on_testing_marks_testing_active(self):
        view = branches_view("testing", "2026-07-21")
        self.assertEqual(view.testing.object_name, "branch-active")
        self.assertEqual(view.testing.button_text, "On Testing  (current)")
        self.assertIn("built 2026-07-21", view.testing.build_label_text)
        self.assertTrue(view.testing.build_label_visible)
        self.assertEqual(view.stable.object_name, "branch-inactive")
        self.assertFalse(view.stable.build_label_visible)

    def test_on_testing_cachy_flavor_also_marks_testing_active(self):
        view = branches_view("testing-cachy", "2026-07-21")
        self.assertEqual(view.testing.object_name, "branch-active")

    def test_unrecognized_branch_marks_neither_active(self):
        view = branches_view("some-other-branch", "2026-07-21")
        self.assertEqual(view.stable.object_name, "branch-inactive")
        self.assertEqual(view.testing.object_name, "branch-inactive")
        self.assertFalse(view.stable.build_label_visible)
        self.assertFalse(view.testing.build_label_visible)

    def test_missing_booted_timestamp_hides_build_label(self):
        view = branches_view("latest", None)
        self.assertFalse(view.stable.build_label_visible)
        self.assertEqual(view.stable.build_label_text, "")


class UpdateAvailabilityViewTests(unittest.TestCase):
    """page_update_availability.py's hero card (icon/title/body/buttons) is
    driven entirely by this decision tree — no Qt, so it's testable directly."""

    def _view(self, **overrides):
        base = dict(
            staged=False, check_state="uptodate", flatpak_count=0,
            check_ts="14:00", check_ts_details="", staged_ts=None,
        )
        base.update(overrides)
        return update_availability_view(**base)

    def test_staged_takes_priority_and_offers_restart(self):
        view = self._view(staged=True, staged_ts="2026-07-20", check_state="uptodate", flatpak_count=2)
        self.assertEqual(view.card_style, "card-accent-ok")
        self.assertEqual(view.title, "Restart required")
        self.assertTrue(view.restart_btn_visible)
        self.assertFalse(view.update_btn_visible)
        self.assertIn("built 2026-07-20", view.body)
        self.assertIn("2 Flatpak updates can be installed", view.body)

    def test_system_update_available(self):
        view = self._view(check_state="available", check_ts_details="2026-07-21")
        self.assertEqual(view.title, "Update available")
        self.assertTrue(view.update_btn_visible)
        self.assertFalse(view.restart_btn_visible)
        self.assertIn("built 2026-07-21", view.body)

    def test_only_flatpaks_pending(self):
        view = self._view(check_state="uptodate", flatpak_count=1)
        self.assertEqual(view.title, "App updates available")
        self.assertIn("1 Flatpak app update is available", view.body)
        self.assertTrue(view.update_btn_visible)

    def test_up_to_date(self):
        view = self._view(check_state="uptodate", flatpak_count=0)
        self.assertEqual(view.title, "Up to date")
        self.assertFalse(view.update_btn_visible)
        self.assertFalse(view.restart_btn_visible)

    def test_check_unavailable(self):
        view = self._view(check_state="", flatpak_count=0)
        self.assertEqual(view.title, "Check unavailable")
        self.assertFalse(view.update_btn_visible)
        self.assertFalse(view.restart_btn_visible)

    def test_singular_flatpak_wording_on_staged_branch(self):
        view = self._view(staged=True, flatpak_count=1)
        self.assertIn("1 Flatpak update can be installed", view.body)


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


class BootcQueryLockTests(unittest.TestCase):
    def test_status_probes_are_skipped_during_upgrade(self):
        with patch.object(bootc_query, "active_operation", return_value="/usr/bin/bootc upgrade"):
            with patch.object(bootc_query, "run_command") as run:
                self.assertEqual(bootc_query.fetch_status_text(), "")
                self.assertIsNone(bootc_query.fetch_status_data())
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
