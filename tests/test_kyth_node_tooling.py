"""Node/npm image defaults for rootless global developer tools."""
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
NODE_SCRIPT = ROOT / "build_files" / "scripts" / "nodejs.sh"
DOCKERFILE = ROOT / "Dockerfile"


class NodeToolingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package_script = PACKAGE_SCRIPT.read_text(encoding="utf-8")
        cls.node_script = NODE_SCRIPT.read_text(encoding="utf-8")
        cls.dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    def test_node_24_artifacts_are_pinned_and_verified(self):
        self.assertIn("ARG NODEJS_VERSION=24.15.0", self.dockerfile)
        self.assertIn('NODEJS_VERSION="${NODEJS_VERSION:-24.15.0}"', self.node_script)
        self.assertIn("sha256sum --check --strict", self.node_script)
        self.assertIn("nodejs.org/dist", self.node_script)
        self.assertIn('archive_arch="x64"', self.node_script)
        self.assertIn('archive_arch="arm64"', self.node_script)

    def test_node_engine_floor_is_verified(self):
        self.assertIn("major === 24 && minor < 15", self.node_script)

    def test_global_npm_prefix_is_user_writable(self):
        self.assertIn("cat >/etc/npmrc", self.package_script)
        self.assertIn("prefix=${HOME}/.local", self.package_script)
        self.assertIn('ln -sfn /etc/npmrc "${install_root}/etc/npmrc"', self.node_script)
        self.assertIn("npm config get prefix", self.node_script)


if __name__ == "__main__":
    unittest.main()
