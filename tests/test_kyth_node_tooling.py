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
AI_DEV_MODULE = (
    ROOT / "build_files" / "kyth_shared" / "kyth_shared" / "ai_dev.py"
)


class NodeToolingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package_script = PACKAGE_SCRIPT.read_text(encoding="utf-8")
        cls.ai_dev_script = AI_DEV_SCRIPT.read_text(encoding="utf-8")
        cls.ai_dev_module = AI_DEV_MODULE.read_text(encoding="utf-8")

    def test_global_npm_prefix_is_user_writable(self):
        self.assertIn("cat >/etc/npmrc", self.package_script)
        self.assertIn("prefix=${HOME}/.local", self.package_script)

    def test_ai_dev_installs_node_and_exports_wrappers(self):
        self.assertIn("nodejs npm", self.ai_dev_module)
        for command in ("node", "npm", "npx"):
            self.assertIn(command, self.ai_dev_module)
        self.assertIn("distrobox-export --bin", self.ai_dev_module)

    def test_headroom_is_isolated_to_the_ai_dev_environment(self):
        self.assertNotIn("/usr/bin/headroom", self.package_script)
        self.assertIn("uv tool install --upgrade headroom", self.ai_dev_module)
        self.assertNotIn("pip install --user --upgrade pipx", self.ai_dev_module)


if __name__ == "__main__":
    unittest.main()
