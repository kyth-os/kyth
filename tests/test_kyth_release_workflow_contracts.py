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
    def test_iso_artifact_has_one_producer_and_matching_consumers(self):
        """One upload in build; every download resolves it from build's output.

        Two consumers by design: the acceptance job boots the ISO, and publish
        signs and ships it. Both must name the artifact through
        needs.build.outputs so neither can drift onto a hardcoded name and
        publish or accept a different ISO than the one that was built.
        """
        workflow = (
            ROOT / ".github/workflows/build-live-iso.yml"
        ).read_text(encoding="utf-8")
        producer = "\n          name: ${{ steps.release.outputs.artifact_name }}"
        consumer = "\n          name: ${{ needs.build.outputs.artifact_name }}"

        self.assertEqual(workflow.count(producer), 1)
        self.assertEqual(workflow.count(consumer), 2)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertIn("retention-days: 7", workflow)

    def test_publication_is_gated_on_acceptance(self):
        """A failed VM acceptance must never reach the publish job."""
        workflow = (
            ROOT / ".github/workflows/build-live-iso.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("needs: [build, acceptance]", workflow)
        self.assertIn("needs.acceptance.result == 'success'", workflow)
        # Skipped is tolerated (emergency dispatch); failure never is.
        self.assertIn("needs.acceptance.result == 'skipped'", workflow)
        self.assertNotIn("needs.acceptance.result != 'failure'", workflow)

    def test_release_identity_is_generated_by_shared_script(self):
        workflow = (
            ROOT / ".github/workflows/build-live-iso.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "python3 build_files/scripts/release_identity.py",
            workflow,
        )
        self.assertNotIn('RELEASE_ID="${DATE}-${SHORT_SHA}', workflow)


class ReleaseChainingContracts(unittest.TestCase):
    def test_r2_public_base_url_is_single_sourced(self):
        """The R2 download host lives in release_identity.py exactly once.

        publish-release.py and generate-release-metadata.py import it;
        README download links must resolve to the same base.
        """
        scripts = ROOT / "build_files/scripts"
        identity_src = (scripts / "release_identity.py").read_text(encoding="utf-8")
        host = "pub-9a3cc72972ea44c4ae7504ee7cda1fa6.r2.dev"
        self.assertIn(f'R2_PUBLIC_BASE_URL = "https://{host}"', identity_src)

        for name in ("publish-release.py", "generate-release-metadata.py"):
            src = (scripts / name).read_text(encoding="utf-8")
            self.assertNotIn(host, src, f"{name} hardcodes the R2 host")
            self.assertIn("from release_identity import", src)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"https://{host}/kyth-live-latest.iso", readme)
        self.assertIn(f"https://{host}/kyth-live-testing.iso", readme)

    def test_downstream_dispatches_are_verified(self):
        """Every gh workflow run dispatch must fail loudly when dropped.

        dispatch-workflow polls for the downstream run; no workflow may
        fire-and-forget a raw `gh workflow run` anymore.
        """
        action = (
            ROOT / ".github/actions/dispatch-workflow/action.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("gh run list", action)
        self.assertIn("::error::", action)

        for name in ("build.yml", "supply-chain.yml", "build-live-iso.yml"):
            workflow = (ROOT / ".github/workflows" / name).read_text(
                encoding="utf-8"
            )
            self.assertNotIn(
                "gh workflow run", workflow, f"{name} has an unverified dispatch"
            )

    def test_iso_publish_fails_loudly_without_sbom(self):
        """A missing source-image SBOM blocks ISO publish; never warn-skip."""
        workflow = (ROOT / ".github/workflows/build-live-iso.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("::warning::No SBOM", workflow)
        self.assertIn("Wait for source image SBOM", workflow)
        self.assertIn("Fail if source image has no SBOM", workflow)


if __name__ == "__main__":
    unittest.main()
