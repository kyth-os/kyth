import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import kyth_changelog as changelog  # noqa: E402


class NormalizeVersionTests(unittest.TestCase):
    def test_strips_epoch_prefix(self):
        self.assertEqual(changelog.normalize_version("2:1.2.3-4.fc44"), "1.2.3-4")

    def test_strips_fedora_release_suffix(self):
        self.assertEqual(changelog.normalize_version("1.2.3-4.fc44"), "1.2.3-4")

    def test_no_epoch_or_fedora_suffix_is_unchanged(self):
        self.assertEqual(changelog.normalize_version("1.2.3-4"), "1.2.3-4")

    def test_fedora_suffix_mid_string_is_stripped(self):
        self.assertEqual(changelog.normalize_version("1.2.3.fc44.x86_64"), "1.2.3.x86_64")


class RpmPackagesTests(unittest.TestCase):
    def test_none_sbom_returns_empty(self):
        self.assertEqual(changelog.rpm_packages(None), {})

    def test_filters_to_rpm_artifacts_and_normalizes_versions(self):
        sbom = {
            "artifacts": [
                {"type": "rpm", "name": "gamescope", "version": "2:3.14-1.fc44"},
                {"type": "npm", "name": "not-an-rpm", "version": "1.0.0"},
                {"type": "rpm", "name": "no-version"},
                {"type": "rpm", "version": "1.0.0"},
            ]
        }
        self.assertEqual(changelog.rpm_packages(sbom), {"gamescope": "3.14-1"})


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
        Path(path).write_text("not json", encoding="utf-8")
        try:
            self.assertEqual(changelog.grype_cve_set(path), set())
        finally:
            Path(path).unlink()


class SecuritySectionTests(unittest.TestCase):
    def _write_report(self, matches: list[dict]) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
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
