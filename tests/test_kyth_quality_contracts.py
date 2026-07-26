import unittest
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
        self.assertIn("just test-coverage", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("coverage.xml", workflow)

    def test_critical_modules_have_explicit_thresholds(self):
        gate = (ROOT / "build_files/scripts/check-critical-coverage.py").read_text()
        for module in ("recovery.py", "privileged.py", "updates.py", "user_polish.py"):
            self.assertIn(module, gate)


if __name__ == "__main__":
    unittest.main()
