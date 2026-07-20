"""Node/npm defaults for rootless global developer tools in KythOS container environment."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_SCRIPT = (
    ROOT
    / "build_files"
    / "scripts"
    / "packages"
    / "18-desktop-helper-and-creator-tooling.sh"
)
AI_DEV_SCRIPT = ROOT / "build_files" / "kyth-ai-dev"


class NodeToolingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package_script = PACKAGE_SCRIPT.read_text(encoding="utf-8")
        cls.ai_dev_script = AI_DEV_SCRIPT.read_text(encoding="utf-8")

    def test_global_npm_prefix_is_user_writable(self):
        self.assertIn("cat >/etc/npmrc", self.package_script)
        self.assertIn("prefix=${HOME}/.local", self.package_script)

    def test_ai_dev_installs_node_and_exports_wrappers(self):
        self.assertIn("nodejs npm", self.ai_dev_script)
        self.assertIn("distrobox-export --bin /usr/bin/node", self.ai_dev_script)
        self.assertIn("distrobox-export --bin /usr/bin/npm", self.ai_dev_script)
        self.assertIn("distrobox-export --bin /usr/bin/npx", self.ai_dev_script)


if __name__ == "__main__":
    unittest.main()
