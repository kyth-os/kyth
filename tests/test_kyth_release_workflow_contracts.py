from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "build_files/scripts/release_identity.py"
SPEC = importlib.util.spec_from_file_location("release_identity", SCRIPT)
assert SPEC and SPEC.loader
release_identity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_identity
SPEC.loader.exec_module(release_identity)


class ReleaseIdentityTests(unittest.TestCase):
    def test_testing_release_names_are_deterministic(self):
        identity = release_identity.build_identity(
            "testing",
            "abcdef0123456789",
            "42",
            "3",
            build_date="20260726",
        )

        self.assertEqual(identity.release_id, "20260726-abcdef01-42-3")
        self.assertEqual(
            identity.artifact_name,
            "kyth-live-iso-testing-20260726-abcdef01-42-3",
        )
        self.assertEqual(identity.channel_basename, "kyth-live-testing.iso")

    def test_unknown_release_channel_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported release channel"):
            release_identity.build_identity(
                "nightly", "abcdef0123456789", "1", "1"
            )


class WorkflowArtifactContracts(unittest.TestCase):
    def test_iso_artifact_has_one_producer_and_matching_consumer(self):
        workflow = (
            ROOT / ".github/workflows/build-live-iso.yml"
        ).read_text(encoding="utf-8")
        producer = "\n          name: ${{ steps.release.outputs.artifact_name }}"
        consumer = "\n          name: ${{ needs.build.outputs.artifact_name }}"

        self.assertEqual(workflow.count(producer), 1)
        self.assertEqual(workflow.count(consumer), 1)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertIn("retention-days: 7", workflow)

    def test_release_identity_is_generated_by_shared_script(self):
        workflow = (
            ROOT / ".github/workflows/build-live-iso.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "python3 build_files/scripts/release_identity.py",
            workflow,
        )
        self.assertNotIn('RELEASE_ID="${DATE}-${SHORT_SHA}', workflow)


if __name__ == "__main__":
    unittest.main()
