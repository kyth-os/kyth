import unittest
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QualityContractsTests(unittest.TestCase):
    def test_quality_dependencies_are_exactly_pinned(self):
        requirements = (ROOT / "requirements-quality.txt").read_text().splitlines()
        self.assertTrue(requirements)
        self.assertTrue(all(line.count("==") == 1 for line in requirements))
        justfile = (ROOT / "Justfile").read_text()
        self.assertIn("setup-quality:", justfile)
        self.assertIn(".venv-quality/bin/python", justfile)

    def test_validation_publishes_coverage_even_on_failure(self):
        workflow = (ROOT / ".github/workflows/validation.yml").read_text()
        self.assertIn("./build_files/scripts/run-quality.sh", workflow)
        quality_job = workflow.split("  quality:", 1)[1]
        self.assertNotIn("run: just ", quality_job)
        self.assertIn("if: always()", workflow)
        self.assertIn("coverage.xml", workflow)

    def test_pre_push_runs_the_same_quality_gate_as_ci(self):
        preflight = (ROOT / "build_files/scripts/ci-preflight.sh").read_text()
        self.assertIn("./build_files/scripts/run-quality.sh", preflight)

    def test_validation_tool_archives_do_not_require_archive_owners(self):
        installer = (
            ROOT / "build_files/scripts/install-validation-tools.sh"
        ).read_text()
        self.assertIn("--no-same-owner", installer)
        self.assertIn('SHELLCHECK_VERSION="${SHELLCHECK_VERSION:-', installer)
        self.assertIn('download_and_verify "shellcheck"', installer)

    def test_critical_modules_have_explicit_thresholds(self):
        gate = (ROOT / "build_files/scripts/check-critical-coverage.py").read_text()
        for module in ("recovery.py", "privileged.py", "updates.py", "user_polish.py"):
            self.assertIn(module, gate)

    def test_primary_ui_shells_do_not_bypass_command_gateway(self):
        ui_paths = (
            ROOT / "build_files/kyth-welcome/kyth_welcome/windows.py",
            ROOT / "build_files/kyth-welcome/kyth_welcome/wizard/window.py",
            ROOT / "build_files/kyth-welcome/kyth_welcome/wizard/steps_finish.py",
        )
        violations = []
        for path in ui_paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    violations.extend(
                        f"{path.relative_to(ROOT)} imports subprocess"
                        for alias in node.names
                        if alias.name == "subprocess"
                    )
                elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                    violations.append(
                        f"{path.relative_to(ROOT)} imports from subprocess"
                    )
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
