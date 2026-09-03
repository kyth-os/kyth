"""Shared Rust/Python parity cases for Secure Boot decision planning."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth_shared"))
sys.path.insert(0, str(ROOT / "src" / "kyth-installer"))

from kyth_installer.secure_boot import plan_mok  # noqa: E402
from kyth_installer import system  # noqa: E402


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

    def test_installed_helper_supplies_the_decision_without_password_data(self):
        response = {
            "state": "ready",
            "action": "import-certificate",
            "requires_password": True,
            "requires_reboot_confirmation": True,
            "message": "stage enrollment",
        }
        with (
            mock.patch.object(system.shutil, "which", return_value="/usr/bin/kyth-installer-exec"),
            mock.patch.object(
                system,
                "run_command",
                return_value=mock.Mock(stdout=json.dumps(response)),
            ) as run,
        ):
            plan = system._plan_mok(
                kernel="cachy",
                force_stage=False,
                certificate_present=True,
                mokutil_present=True,
                secure_boot="enabled",
                enrolled="no",
                pending="no",
            )
        self.assertEqual(plan.state, "ready")
        self.assertTrue(plan.requires_password)
        self.assertNotIn("password", run.call_args.kwargs["input"])


if __name__ == "__main__":
    unittest.main()
