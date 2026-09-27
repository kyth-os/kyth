"""Shared Rescue guidance cases for the Rust and Python implementations."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.recovery import rescue_guidance  # noqa: E402


FIXTURE = ROOT / "src" / "kyth-installer-web" / "src-tauri" / "testdata" / "recovery_cases.json"


class InstallerRecoveryParityTests(unittest.TestCase):
    def test_python_guidance_matches_shared_status_cases(self):
        for case in json.loads(FIXTURE.read_text(encoding="utf-8")):
            with self.subTest(status=case["status"]):
                guidance = rescue_guidance({"status": case["status"]})
                self.assertEqual(guidance["severity"], case["severity"])
                self.assertEqual(guidance["bootable"], case["bootable"])
                self.assertEqual(guidance["message"], case["message"])


if __name__ == "__main__":
    unittest.main()
