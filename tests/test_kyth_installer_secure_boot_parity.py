"""Shared Rust/Python parity cases for Secure Boot decision planning."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth_shared"))
sys.path.insert(0, str(ROOT / "src" / "kyth-installer"))

from kyth_installer.secure_boot import plan_mok  # noqa: E402


FIXTURE = (
    ROOT
    / "src"
    / "kyth-installer-web"
    / "src-tauri"
    / "testdata"
    / "secure_boot_cases.json"
)


class InstallerSecureBootParityTests(unittest.TestCase):
    def test_python_matches_shared_decision_fixture(self):
        for case in json.loads(FIXTURE.read_text(encoding="utf-8")):
            with self.subTest(case=case["name"]):
                plan = plan_mok(**case["input"])
                self.assertEqual(plan.state, case["expected"]["state"])
                self.assertEqual(plan.action, case["expected"]["action"])


if __name__ == "__main__":
    unittest.main()
