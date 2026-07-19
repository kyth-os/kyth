"""Sysconfig domain fragments (demonolith build layout)."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "build_files" / "scripts"
FRAG_DIR = SCRIPTS / "sysconfig"
RUNNER = SCRIPTS / "sysconfig-static.sh"


class SysconfigFragmentTests(unittest.TestCase):
    def test_runner_exists_and_is_thin(self):
        self.assertTrue(RUNNER.is_file())
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("sysconfig", text)
        self.assertLess(len(text.splitlines()), 50)
        # Must not still embed the old monolith herdocs.
        self.assertNotIn("99-kyth.conf", text)

    def test_fragments_present_and_named(self):
        frags = sorted(FRAG_DIR.glob("*.sh"))
        self.assertGreaterEqual(len(frags), 20)
        for frag in frags:
            self.assertRegex(frag.name, r"^\d{2}-.+\.sh$")
            body = frag.read_text(encoding="utf-8")
            self.assertTrue(body.startswith("#!/bin/bash") or body.lstrip().startswith("#"))
            self.assertIn("set -euo pipefail", body)

    def test_kernel_sysctl_fragment(self):
        path = FRAG_DIR / "01-kernel-sysctl-parameters.sh"
        self.assertTrue(path.is_file())
        body = path.read_text(encoding="utf-8")
        self.assertIn("vm.swappiness", body)
        self.assertIn("99-kyth.conf", body)


if __name__ == "__main__":
    unittest.main()
