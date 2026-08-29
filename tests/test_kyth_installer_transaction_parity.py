"""Shared transaction-state decoder cases for Rust and Python."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.recovery import read_transaction_state  # noqa: E402
from kyth_installer.recovery import rescue_guidance  # noqa: E402


FIXTURE = ROOT / "src" / "kyth-installer-web" / "src-tauri" / "testdata" / "transaction_cases.json"


class InstallerTransactionParityTests(unittest.TestCase):
    def test_python_reader_and_guidance_match_shared_states(self):
        for case in json.loads(FIXTURE.read_text(encoding="utf-8")):
            if "expected" not in case:
                continue
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "transaction.json"
                path.write_text(json.dumps(case["json"]), encoding="utf-8")
                state = read_transaction_state(path)
                expected = case["expected"]
                self.assertEqual(state.get("status", ""), expected["status"])
                self.assertEqual(state.get("phase", ""), expected["phase"])
                self.assertEqual(state.get("disk", ""), expected["disk"])
                self.assertEqual(state.get("source", {}).get("digest", ""), expected["source_digest"])
                guidance = rescue_guidance(state)
                self.assertEqual(guidance["severity"], expected["severity"])
                self.assertEqual(guidance["bootable"], expected["bootable"])


if __name__ == "__main__":
    unittest.main()
