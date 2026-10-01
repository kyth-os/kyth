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
    def test_testing_base_stage_refuses_a_non_f45_base(self):
        """A workflow_run build uses main's build.yml and passes an F44 base arg."""
        dockerfile = (ROOT / "build_base/Dockerfile").read_text(encoding="utf-8")
        guard = dockerfile.split("FROM ${BASE_IMAGE}", 1)[1]
        self.assertIn(". /etc/os-release", guard)
        self.assertIn('[ "${VERSION_ID}" = "45" ]', guard)
        self.assertIn("exit 1", guard)
        build = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        # push builds use their own concurrency group so a doomed main-copy
        # workflow_run build can never cancel the real F45 one.
        self.assertIn("github.event_name == 'push' && 'push-'", build)

    def test_every_testing_push_builds_with_testings_own_workflow(self):
        """workflow_run runs main's copy of build.yml, so testing pushes built F44.

        A push trigger runs the pushed branch's own build.yml (which pins F45).
        The gate must wait for that exact commit's Validation, the plan must pin
        the pushed SHA, and the build must refuse any non-F45 base on testing.
        """
        build = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        on_block = build.split("\npermissions:", 1)[0]
        self.assertRegex(on_block, r"(?m)^  push:\n    branches: \[testing\]$")
        # main must not gain a push build: it is promoted by a human, not pushed.
        self.assertNotRegex(on_block, r"push:\n    branches: \[[^\]]*main")
        gate = build.split("  plan:", 1)[0]
        self.assertIn("eventName === 'push'", gate)
        self.assertIn("head_sha: sha", gate)
        self.assertIn("r.name === 'Validation'", gate)
        self.assertIn("validation.conclusion === 'success'", gate)
        plan = build.split("  plan:", 1)[1].split("  build_push:", 1)[0]
        self.assertIn('elif [[ "${EVENT_NAME}" == push ]]', plan)
        self.assertIn('echo "head_sha=${HEAD_SHA}" >&3', plan.split("== push ]]", 1)[1])
        step = build.split("- name: Resolve upstream base image digest", 1)[1].split(
            "- name: Build base image", 1
        )[0]
        self.assertIn('"${MATRIX_BRANCH}" == testing', step)
        self.assertIn("!= quay.io/fedora/fedora-kinoite:45", step)

    def test_upstream_base_comes_from_the_dockerfile_pin(self):
        """build.yml must not hardcode the base: --build-arg overrides the pin.

        A hardcoded ublue F44 image here kept :testing on F44 even after
        build_base/Dockerfile moved to Fedora Kinoite 45. The supply-chain
        gate must also accept whichever base the branch pins.
        """
        build = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        step = build.split("- name: Resolve upstream base image digest", 1)[1].split(
            "- name: Build base image", 1
        )[0]
        self.assertIn("build_base/Dockerfile", step)
        self.assertNotIn('IMAGE="ghcr.io/ublue-os/kinoite-main:44"', step)
        dockerfile = (ROOT / "build_base/Dockerfile").read_text(encoding="utf-8")
        pinned = next(
            line.split("=", 1)[1].split("@", 1)[0]
            for line in dockerfile.splitlines()
            if line.startswith("ARG BASE_IMAGE=")
        )
        # Every base the Dockerfile may pin is allowed by both workflows.
        self.assertIn(pinned.replace(".", "\\."), step)
        supply = (ROOT / ".github/workflows/supply-chain.yml").read_text(encoding="utf-8")
        self.assertIn(pinned.replace(".", "\\."), supply)
        for label in ('image.version="45"', 'osbuild.version="45"', 'KythOS 45"'):
            self.assertIn(label, (ROOT / "Dockerfile").read_text(encoding="utf-8"))

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

    def test_iso_dispatch_waits_for_verified_container_signature(self):
        """The live ISO must not race the serialized supply-chain signer."""
        workflow = (
            ROOT / ".github/workflows/supply-chain.yml"
        ).read_text(encoding="utf-8")
        build = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        publish = workflow.split("  publish:", 1)[1]
        verify_at = publish.index(
            "- name: Verify published signatures and build provenance"
        )
        dispatch_at = publish.index(
            "- name: Dispatch Live ISO after image verification"
        )
        self.assertLess(verify_at, dispatch_at)
        dispatch_inputs = workflow.split("  workflow_dispatch:", 1)[1].split(
            "permissions:", 1
        )[0]
        self.assertIn("dispatch_iso", dispatch_inputs)
        self.assertIn('"dispatch_iso": "true"', build)
        self.assertIn("inputs.dispatch_iso", publish)


if __name__ == "__main__":
    unittest.main()
