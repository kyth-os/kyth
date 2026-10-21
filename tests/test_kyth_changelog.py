import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import kyth_changelog as changelog  # noqa: E402


class RpmPackagesTests(unittest.TestCase):
    def test_none_sbom_returns_empty(self):
        self.assertEqual(changelog.rpm_packages(None), {})

    def test_filters_to_rpm_artifacts_and_preserves_full_nevra_version(self):
        sbom = {
            "artifacts": [
                {
                    "type": "rpm",
                    "name": "gamescope",
                    "version": "2:3.14-1.fc44",
                    "metadata": {"architecture": "x86_64"},
                },
                {"type": "npm", "name": "not-an-rpm", "version": "1.0.0"},
                {"type": "rpm", "name": "no-version"},
                {"type": "rpm", "version": "1.0.0"},
            ]
        }
        self.assertEqual(
            changelog.rpm_packages(sbom),
            {"gamescope.x86_64": "2:3.14-1.fc44"},
        )

    def test_release_only_change_is_not_normalized_away(self):
        previous = changelog.rpm_packages({"artifacts": [{
            "type": "rpm", "name": "example", "version": "1.0-1.fc44",
            "metadata": {"architecture": "x86_64"},
        }]})
        current = changelog.rpm_packages({"artifacts": [{
            "type": "rpm", "name": "example", "version": "1.0-1.fc45",
            "metadata": {"architecture": "x86_64"},
        }]})

        added, changed, removed = changelog.package_changes(previous, current)

        self.assertEqual((added, changed, removed), ([], ["example.x86_64"], []))

    def test_multilib_packages_keep_architectures_separate(self):
        sbom = {"artifacts": [
            {
                "type": "rpm", "name": "example", "version": "1.0-1.fc45",
                "metadata": {"architecture": arch},
            }
            for arch in ("i686", "x86_64")
        ]}

        self.assertEqual(
            changelog.rpm_packages(sbom),
            {
                "example.i686": "1.0-1.fc45",
                "example.x86_64": "1.0-1.fc45",
            },
        )

    def test_reconstructs_full_evr_from_syft_rpm_metadata(self):
        sbom = {"artifacts": [{
            "type": "rpm",
            "name": "example",
            "metadata": {
                "version": "1.2.3",
                "release": "4.fc45",
                "epoch": 2,
                "architecture": "aarch64",
            },
        }]}

        self.assertEqual(
            changelog.rpm_packages(sbom),
            {"example.aarch64": "2:1.2.3-4.fc45"},
        )

    def test_reads_architecture_from_purl_when_rpm_metadata_lacks_it(self):
        sbom = {"artifacts": [{
            "type": "rpm",
            "name": "example",
            "version": "1.2.3-4.fc45",
            "purl": "pkg:rpm/fedora/example@1.2.3-4.fc45?arch=x86_64&distro=fedora-45",
        }]}

        self.assertEqual(
            changelog.rpm_packages(sbom),
            {"example.x86_64": "1.2.3-4.fc45"},
        )


class FindSbomDigestTests(unittest.TestCase):
    def test_prefers_syft_when_multiple_sbom_formats_are_attached(self):
        discovered = {"referrers": [
            {"artifactType": "application/spdx+json", "digest": "sha256:spdx"},
            {"artifactType": "application/vnd.syft+json", "digest": "sha256:syft"},
        ]}
        with patch.object(changelog, "run", return_value=json.dumps(discovered)):
            digest = changelog.find_sbom_digest("ghcr.io/kyth-os/kyth", "sha256:image")

        self.assertEqual(digest, "sha256:syft")

    def test_does_not_select_spdx_for_syft_rpm_comparison(self):
        discovered = {"referrers": [
            {"artifactType": "application/spdx+json", "digest": "sha256:spdx"},
        ]}
        with patch.object(changelog, "run", return_value=json.dumps(discovered)):
            digest = changelog.find_sbom_digest("ghcr.io/kyth-os/kyth", "sha256:image")

        self.assertIsNone(digest)


class PackageChangesTests(unittest.TestCase):
    def test_added_changed_and_removed(self):
        previous = {"a": "1.0", "b": "2.0", "c": "3.0"}
        current = {"a": "1.0", "b": "2.1", "d": "4.0"}
        added, changed, removed = changelog.package_changes(previous, current)
        self.assertEqual(added, ["d"])
        self.assertEqual(changed, ["b"])
        self.assertEqual(removed, ["c"])

    def test_identical_maps_produce_no_changes(self):
        pkgs = {"a": "1.0"}
        added, changed, removed = changelog.package_changes(pkgs, dict(pkgs))
        self.assertEqual((added, changed, removed), ([], [], []))

    def test_results_are_sorted(self):
        previous = {}
        current = {"zeta": "1.0", "alpha": "1.0"}
        added, _, _ = changelog.package_changes(previous, current)
        self.assertEqual(added, ["alpha", "zeta"])

    def test_changelog_omits_repeated_inventory_without_a_baseline(self):
        current = {"kernel": "7.2", "mesa": "26.2"}
        section = changelog.package_changes_section(current, None)
        self.assertIn("RPM comparison unavailable", section)
        self.assertIn("previous SBOM baseline could not be loaded", section)

    def test_changelog_renders_only_changed_package_rows(self):
        previous = {"kernel": "7.1", "mesa": "26.2", "old": "1"}
        current = {"kernel": "7.2", "mesa": "26.2", "new": "2"}
        section = changelog.package_changes_section(current, previous)
        self.assertIn("| ~ | `kernel` | 7.1 | 7.2 |", section)
        self.assertIn("| + | `new` |  | 2 |", section)
        self.assertIn("| - | `old` | 1 |  |", section)
        self.assertNotIn("`mesa`", section)
        self.assertNotIn("No previous SBOM", section)

    def test_arch_qualified_kernel_still_gets_major_package_summary(self):
        previous = {"kernel-cachyos.x86_64": "6.12.0-1.fc45"}
        current = {"kernel-cachyos.x86_64": "6.13.0-1.fc45"}

        section = changelog.package_changes_section(current, previous)

        major = section.split("### All RPM Changes", 1)[0]
        self.assertIn("### Major Package Changes", major)
        self.assertIn(
            "| ~ | `kernel-cachyos.x86_64` | 6.12.0-1.fc45 | 6.13.0-1.fc45 |",
            major,
        )


class ChangelogCliTests(unittest.TestCase):
    @staticmethod
    def _write_sbom(path: Path, packages: dict[str, str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "artifacts": [
                    {"type": "rpm", "name": name, "version": version}
                    for name, version in packages.items()
                ]
            }),
            encoding="utf-8",
        )

    def _run_changelog(self, output: Path, current_sbom: Path, *extra: str):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / ".github/scripts/kyth_changelog.py"),
                "--image", "ghcr.io/kyth-os/kyth",
                "--branch", "testing",
                "--current-tag", "testing.20261017.1.1.01234567",
                "--current-digest", "",
                "--previous-digest", "",
                "--current-sha", "a" * 40,
                "--current-sbom-file", str(current_sbom),
                *extra,
                "--output", str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_nested_previous_sbom_produces_the_complete_rpm_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_sbom = root / "current.syft.json"
            previous_sbom = root / "output/supply-chain/previous.syft.json"
            output = root / "changelog.md"
            self._write_sbom(current_sbom, {
                "kernel-cachyos": "6.13.0-1.fc44",
                "upgrade-pkg": "2.0-1.fc44",
                "added-pkg": "1.0-1.fc44",
                "unchanged-pkg": "4.0-1.fc44",
            })
            self._write_sbom(previous_sbom, {
                "kernel-cachyos": "6.12.0-1.fc44",
                "upgrade-pkg": "1.0-1.fc44",
                "removed-pkg": "3.0-1.fc44",
                "unchanged-pkg": "4.0-1.fc44",
            })

            result = self._run_changelog(
                output, current_sbom,
                "--previous-sbom-file", str(previous_sbom),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            notes = output.read_text(encoding="utf-8")
            all_changes = notes.split("### All RPM Changes", 1)[1]
            rows = [
                line
                for line in all_changes.splitlines()
                if line.startswith(("| + |", "| ~ |", "| - |"))
            ]
            self.assertEqual(len(rows), 4, notes)
            self.assertIn("| ~ | `kernel-cachyos` | 6.12.0-1.fc44 | 6.13.0-1.fc44 |", all_changes)
            self.assertIn("| ~ | `upgrade-pkg` | 1.0-1.fc44 | 2.0-1.fc44 |", all_changes)
            self.assertIn("| + | `added-pkg` |  | 1.0-1.fc44 |", all_changes)
            self.assertIn("| - | `removed-pkg` | 3.0-1.fc44 |  |", all_changes)

    def test_missing_previous_sbom_is_reported_as_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_sbom = root / "current.syft.json"
            output = root / "changelog.md"
            self._write_sbom(current_sbom, {"kernel-cachyos": "6.13.0-1.fc44"})

            result = self._run_changelog(output, current_sbom)

            self.assertEqual(result.returncode, 0, result.stderr)
            notes = output.read_text(encoding="utf-8")
            self.assertIn("RPM comparison unavailable", notes)
            self.assertIn("previous SBOM baseline could not be loaded", notes)

    def test_invalid_previous_sbom_is_not_reported_as_package_additions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_sbom = root / "current.syft.json"
            previous_sbom = root / "previous.json"
            output = root / "changelog.md"
            self._write_sbom(current_sbom, {"kernel-cachyos": "6.13.0-1.fc45"})
            previous_sbom.write_text(json.dumps({"not": "a Syft SBOM"}), encoding="utf-8")

            result = self._run_changelog(
                output, current_sbom,
                "--previous-sbom-file", str(previous_sbom),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            notes = output.read_text(encoding="utf-8")
            self.assertIn("RPM comparison unavailable", notes)
            self.assertNotIn("| + | `kernel-cachyos`", notes)

    def test_explicit_empty_previous_file_does_not_fallback_to_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_sbom = root / "current.syft.json"
            output = root / "changelog.md"
            self._write_sbom(current_sbom, {"kernel-cachyos": "6.13.0-1.fc45"})
            argv = [
                "kyth_changelog.py",
                "--image", "ghcr.io/kyth-os/kyth",
                "--branch", "testing",
                "--current-tag", "testing.20261017.1.1.01234567",
                "--current-digest", "sha256:current",
                "--previous-digest", "sha256:previous",
                "--current-sha", "a" * 40,
                "--current-sbom-file", str(current_sbom),
                "--previous-sbom-file", "",
                "--output", str(output),
            ]

            with patch.object(sys, "argv", argv), \
                 patch.object(changelog, "load_sbom", side_effect=AssertionError("unexpected registry fallback")), \
                 patch.object(changelog, "image_labels", return_value={}):
                result = changelog.main()

            self.assertEqual(result, 0)
            notes = output.read_text(encoding="utf-8")
            self.assertIn("RPM comparison unavailable", notes)
            self.assertNotIn("| + | `kernel-cachyos`", notes)

    def test_oras_sbom_fallback_finds_json_in_nested_directories(self):
        sbom = {"artifacts": [{"type": "rpm", "name": "nested-rpm", "version": "1.2-3"}]}

        def pull_into_nested_path(_cmd, *, cwd=None, **_kwargs):
            path = Path(cwd) / "output/supply-chain/previous.syft.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(sbom), encoding="utf-8")
            return ""

        with patch.object(changelog, "find_sbom_digest", return_value="sha256:sbom"), \
             patch.object(changelog, "run", side_effect=pull_into_nested_path):
            loaded = changelog.load_sbom("ghcr.io/kyth-os/kyth", "sha256:image")

        self.assertEqual(loaded, sbom)


class PreviousImageReleaseTests(unittest.TestCase):
    def test_selects_latest_published_older_release_of_same_flavor(self):
        older = "sha256:" + "a" * 64
        newer = "sha256:" + "b" * 64
        cachy = "sha256:" + "c" * 64
        releases = [
            {"tag_name": "image-testing-20261013-2755-1-9681d007", "draft": False, "prerelease": True,
             "body": f"Image: `ghcr.io/kyth-os/kyth@{newer}`"},
            {"tag_name": "image-testing-cachy-20261013-2754-1-9681d007", "draft": False, "prerelease": True,
             "body": f"Image: `ghcr.io/kyth-os/kyth@{cachy}`"},
            {"tag_name": "image-testing-20261013-2754-1-9681d007", "draft": False, "prerelease": True,
             "body": f"Image: `ghcr.io/kyth-os/kyth@{older}`"},
        ]
        digest = changelog.previous_image_release_digest(
            releases, "testing", "testing.20261013.2754.2.9681d007"
        )
        self.assertEqual(digest, older)

    def test_selects_cachy_baseline_from_shared_image_version(self):
        fedora = "sha256:" + "a" * 64
        cachy = "sha256:" + "b" * 64
        releases = [
            {"tag_name": "image-testing-20261013-2755-1-9681d007", "draft": False, "prerelease": True,
             "body": f"Image: `ghcr.io/kyth-os/kyth@{fedora}`"},
            {"tag_name": "image-testing-cachy-20261013-2754-1-9681d007", "draft": False, "prerelease": True,
             "body": f"Image: `ghcr.io/kyth-os/kyth@{cachy}`"},
        ]
        digest = changelog.previous_image_release_digest(
            releases, "testing-cachy", "testing.20261014.10.1.bbbbbbbb"
        )
        self.assertEqual(digest, cachy)

    def test_ignores_drafts_wrong_channels_and_invalid_digests(self):
        releases = [
            {"tag_name": "image-testing-20261012-2736-1-27a537a0", "draft": True, "prerelease": True,
             "body": "Image: `ghcr.io/kyth-os/kyth@sha256:" + "a" * 64 + "`"},
            {"tag_name": "image-testing-20261012-2735-1-27a537a0", "draft": False, "prerelease": False,
             "body": "Image: `ghcr.io/kyth-os/kyth@sha256:" + "b" * 64 + "`"},
            {"tag_name": "image-testing-20261012-2734-1-27a537a0", "draft": False, "prerelease": True,
             "body": "Image: `ghcr.io/kyth-os/kyth@not-a-digest`"},
        ]
        self.assertEqual(
            changelog.previous_image_release_digest(
                releases, "testing", "testing.20261013.2754.2.9681d007"
            ),
            "",
        )


class TableForTests(unittest.TestCase):
    def test_renders_one_row_per_name(self):
        previous = {"pkg": "1.0"}
        current = {"pkg": "2.0"}
        table = changelog.table_for(["pkg"], previous, current, "~")
        self.assertEqual(table, "| ~ | `pkg` | 1.0 | 2.0 |")

    def test_missing_version_renders_blank(self):
        table = changelog.table_for(["new-pkg"], {}, {"new-pkg": "1.0"}, "+")
        self.assertEqual(table, "| + | `new-pkg` |  | 1.0 |")

    def test_empty_names_renders_empty_string(self):
        self.assertEqual(changelog.table_for([], {}, {}, "+"), "")


class GrypeCveSetTests(unittest.TestCase):
    def _write_report(self, matches: list[dict]) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(path).write_text(json.dumps({"matches": matches}), encoding="utf-8")
        return path

    def test_none_path_returns_empty_set(self):
        self.assertEqual(changelog.grype_cve_set(None), set())

    def test_extracts_cve_and_package_pairs(self):
        path = self._write_report([
            {"vulnerability": {"id": "CVE-2024-1111"}, "artifact": {"name": "openssl"}},
            {"vulnerability": {"id": "CVE-2024-2222"}, "artifact": {"name": "curl"}},
        ])
        try:
            result = changelog.grype_cve_set(path)
        finally:
            Path(path).unlink()
        self.assertEqual(result, {("CVE-2024-1111", "openssl"), ("CVE-2024-2222", "curl")})

    def test_matches_missing_id_or_package_are_skipped(self):
        path = self._write_report([
            {"vulnerability": {"id": ""}, "artifact": {"name": "openssl"}},
            {"vulnerability": {"id": "CVE-2024-3333"}, "artifact": {}},
        ])
        try:
            result = changelog.grype_cve_set(path)
        finally:
            Path(path).unlink()
        self.assertEqual(result, set())

    def test_missing_file_returns_empty_set(self):
        self.assertEqual(changelog.grype_cve_set("/nonexistent/path.json"), set())

    def test_malformed_json_returns_empty_set(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(path).write_text("not json", encoding="utf-8")
        try:
            self.assertEqual(changelog.grype_cve_set(path), set())
        finally:
            Path(path).unlink()


class SecuritySectionTests(unittest.TestCase):
    def _write_report(self, matches: list[dict]) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(path).write_text(json.dumps({"matches": matches}), encoding="utf-8")
        return path

    def test_no_findings_at_all_returns_empty_string(self):
        self.assertEqual(changelog.security_section(None, None), "")

    def test_no_previous_scan_notes_current_finding_count(self):
        current = self._write_report([
            {"vulnerability": {"id": "CVE-2024-1111"}, "artifact": {"name": "openssl"}},
        ])
        try:
            section = changelog.security_section(current, None)
        finally:
            Path(current).unlink()
        self.assertIn("### Security fixes", section)
        self.assertIn("No previous scan to compare against", section)
        self.assertIn("1 finding(s)", section)

    def test_fixed_cve_appears_in_table(self):
        previous = self._write_report([
            {"vulnerability": {"id": "CVE-2024-1111"}, "artifact": {"name": "openssl"}},
        ])
        current = self._write_report([])
        try:
            section = changelog.security_section(current, previous)
        finally:
            Path(previous).unlink()
            Path(current).unlink()
        self.assertIn("CVE-2024-1111", section)
        self.assertIn("`openssl`", section)
        self.assertIn("nvd.nist.gov/vuln/detail/CVE-2024-1111", section)

    def test_no_cves_resolved_when_same_findings_persist(self):
        previous = self._write_report([
            {"vulnerability": {"id": "CVE-2024-1111"}, "artifact": {"name": "openssl"}},
        ])
        current = self._write_report([
            {"vulnerability": {"id": "CVE-2024-1111"}, "artifact": {"name": "openssl"}},
        ])
        try:
            section = changelog.security_section(current, previous)
        finally:
            Path(previous).unlink()
            Path(current).unlink()
        self.assertIn("No CVEs resolved compared to the previous build.", section)


class CommitSectionTests(unittest.TestCase):
    def test_missing_previous_sha_returns_empty(self):
        self.assertEqual(changelog.commit_section({}, "abc123"), "")

    def test_missing_current_sha_returns_empty(self):
        labels = {"org.opencontainers.image.revision": "abc123"}
        self.assertEqual(changelog.commit_section(labels, ""), "")

    def test_identical_shas_return_empty_without_shelling_out(self):
        # Same previous/current commit: no range to diff. If this reached
        # `run()` with a bogus git range it would raise, so a clean empty
        # result also proves the early-return guard works.
        labels = {"org.opencontainers.image.revision": "abc123"}
        self.assertEqual(changelog.commit_section(labels, "abc123"), "")


if __name__ == "__main__":
    unittest.main()
