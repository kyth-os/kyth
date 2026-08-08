import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.updates import (  # noqa: E402
    UpdateCheckCoordinator,
    UpdateProbeResult,
    booted_image_digest,
    check_registry_update,
    firmware_check_commands,
)
from kyth_welcome.services.registry import (  # noqa: E402
    amd64_manifest_entry,
    image_annotations,
    image_revision,
)


class UpdateServiceTests(unittest.TestCase):
    def test_coordinator_completes_after_both_probes_in_any_order(self):
        coordinator = UpdateCheckCoordinator()
        coordinator.begin()
        self.assertIsNone(
            coordinator.accept(UpdateProbeResult.success("flatpak", 2))
        )

        completed = coordinator.accept(
            UpdateProbeResult.success(
                "system", "available", detail="today", manifest_raw="manifest",
            )
        )

        self.assertIsNotNone(completed)
        self.assertEqual(completed.system_state, "available")
        self.assertEqual(completed.flatpak_count, 2)
        self.assertEqual(completed.manifest_raw, "manifest")

    def test_coordinator_turns_probe_failures_into_completed_error_state(self):
        coordinator = UpdateCheckCoordinator()
        coordinator.begin()
        coordinator.accept(UpdateProbeResult.error("flatpak", "flatpak timed out"))
        completed = coordinator.accept(UpdateProbeResult.error("system", "registry timed out"))

        self.assertEqual(completed.system_state, "error")
        self.assertEqual(completed.system_detail, "registry timed out")
        self.assertEqual(completed.flatpak_count, 0)
        self.assertEqual(completed.flatpak_detail, "flatpak timed out")

    def test_coordinator_rejects_unrelated_probe(self):
        coordinator = UpdateCheckCoordinator()
        with self.assertRaises(ValueError):
            coordinator.accept(UpdateProbeResult.success("firmware"))

    def test_booted_image_digest_reads_nested_status(self):
        status = {
            "status": {
                "booted": {
                    "image": {
                        "imageDigest": "sha256:" + "1" * 64,
                    }
                }
            }
        }

        self.assertEqual(booted_image_digest(status), "sha256:" + "1" * 64)

    def test_check_registry_update_reports_uptodate_digest(self):
        digest = "sha256:" + "2" * 64
        status = {"status": {"booted": {"imageDigest": digest}}}
        manifest = {
            "manifests": [
                {
                    "digest": digest,
                    "platform": {"architecture": "amd64", "os": "linux"},
                }
            ]
        }

        def runner(ref):
            self.assertEqual(ref, "ghcr.io/example/os:stable")
            return subprocess.CompletedProcess([], 0, json.dumps(manifest).encode(), b"")

        result = check_registry_update(
            status_data=status,
            branch="stable",
            registry="ghcr.io/example/os",
            inspect_runner=runner,
        )

        self.assertEqual(result.state, "uptodate")

    def test_check_registry_update_reports_inspect_failure(self):
        status = {"status": {"booted": {"digest": "sha256:" + "3" * 64}}}

        def runner(_ref):
            return subprocess.CompletedProcess([], 1, b"", b"denied")

        result = check_registry_update(
            status_data=status,
            branch="stable",
            registry="ghcr.io/example/os",
            inspect_runner=runner,
        )

        self.assertEqual(result.state, "error")
        self.assertEqual(result.detail, "denied")

    def test_firmware_check_commands_refreshes_before_checking(self):
        self.assertEqual(
            firmware_check_commands(refresh=True),
            [["fwupdmgr", "refresh"], ["fwupdmgr", "get-updates"]],
        )


class ManifestAnnotationHelperTests(unittest.TestCase):
    _REV = "org.opencontainers.image.revision"

    def test_amd64_manifest_entry_selects_matching_platform(self):
        index = {
            "manifests": [
                {"digest": "sha256:arm", "platform": {"architecture": "arm64", "os": "linux"}},
                {"digest": "sha256:amd", "platform": {"architecture": "amd64", "os": "linux"}},
            ]
        }
        entry = amd64_manifest_entry(index)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["digest"], "sha256:amd")

    def test_amd64_manifest_entry_returns_none_without_index(self):
        self.assertIsNone(amd64_manifest_entry({"config": {}, "layers": []}))
        self.assertIsNone(amd64_manifest_entry({"manifests": []}))

    def test_image_annotations_prefers_top_level_revision(self):
        manifest = {
            "annotations": {self._REV: "toplevel"},
            "manifests": [
                {"annotations": {self._REV: "entry"},
                 "platform": {"architecture": "amd64", "os": "linux"}},
            ],
        }
        self.assertEqual(image_annotations(manifest).get(self._REV), "toplevel")

    def test_image_annotations_falls_back_to_amd64_entry(self):
        manifest = {
            "manifests": [
                {"annotations": {self._REV: "entry"},
                 "platform": {"architecture": "amd64", "os": "linux"}},
            ],
        }
        self.assertEqual(image_annotations(manifest).get(self._REV), "entry")

    def test_image_annotations_returns_empty_when_nothing_matches(self):
        self.assertEqual(image_annotations({}), {})

    def test_image_revision_truncates_to_twelve_chars(self):
        self.assertEqual(image_revision({self._REV: "0123456789abcdef"}), "0123456789ab")
        self.assertEqual(image_revision({}), "")


if __name__ == "__main__":
    unittest.main()
