"""Shared mount-registry cases for the Rust model and Python registry."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.mount_registry import MountRegistry  # noqa: E402


FIXTURE = ROOT / "src" / "kyth-installer-web" / "src-tauri" / "testdata" / "mount_cases.json"


class InstallerMountParityTests(unittest.TestCase):
    def test_python_registry_matches_shared_cases(self):
        for case in json.loads(FIXTURE.read_text(encoding="utf-8")):
            with self.subTest(case=case["name"]):
                registry = MountRegistry()
                for operation in case["operations"]:
                    if operation["action"] == "register":
                        registry.register(operation["path"])
                    elif operation["action"] == "release":
                        registry.release(operation["path"])
                    elif operation["action"] == "clear":
                        registry.clear()
                    else:
                        self.fail(f"unsupported action: {operation['action']}")
                self.assertEqual(registry.snapshot(), case["expected_snapshot"])
                expected_cleanup = list(reversed(registry.snapshot()))
                registry.clear()
                self.assertEqual(expected_cleanup, case["expected_cleanup"])
                self.assertEqual(registry.snapshot(), [])


if __name__ == "__main__":
    unittest.main()
