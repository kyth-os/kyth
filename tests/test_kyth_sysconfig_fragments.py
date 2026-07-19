"""Sysconfig domain fragments (demonolith build layout)."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "build_files" / "scripts"
FRAG_DIR = SCRIPTS / "sysconfig"
RUNNER = SCRIPTS / "sysconfig-static.sh"
SYSCTL_DATA = ROOT / "build_files" / "data" / "sysctl.d" / "99-kyth.conf"


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
        # The fragment copies the sysctl values from a data file (build_files/data/)
        # instead of embedding them in a heredoc — same pattern as every other
        # extracted config in this refactor. The values themselves are checked
        # against that data file, not the fragment script.
        path = FRAG_DIR / "01-kernel-sysctl-parameters.sh"
        self.assertTrue(path.is_file())
        body = path.read_text(encoding="utf-8")
        self.assertIn("99-kyth.conf", body)
        self.assertTrue(SYSCTL_DATA.is_file())
        self.assertIn("vm.swappiness", SYSCTL_DATA.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
