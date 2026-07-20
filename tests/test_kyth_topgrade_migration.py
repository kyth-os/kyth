"""Tests for kyth-topgrade-migrate script."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATE_PATH = ROOT / "build_files" / "kyth-topgrade-migrate"

loader = SourceFileLoader("kyth_topgrade_migrate", str(MIGRATE_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
migrate = importlib.util.module_from_spec(spec)
loader.exec_module(migrate)


class TopgradeMigrationTests(unittest.TestCase):
    def test_needs_patch_detects_missing_helix_and_toolbx(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".toml", delete=False) as f:
            f.write(
                '[misc]\nno_self_update = true\ndisable = ["system", "distrobox", "containers"]\n\n'
                '[commands]\n"KythOS system update" = "sudo -n bootc upgrade"\n'
                '"KythOS rclone update" = "sudo -n /usr/bin/kyth-rclone-update"\n'
            )
            f.flush()
            path = f.name

        self.assertTrue(migrate.needs_patch(path))
        migrate.patch_config(path)

        with open(path) as f:
            content = f.read()
        self.assertIn('"helix"', content)
        self.assertIn('"toolbx"', content)
        self.assertFalse(migrate.needs_patch(path))

    def test_patch_config_handles_already_correct_config(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".toml", delete=False) as f:
            f.write(
                '[misc]\nno_self_update = true\n'
                'disable = ["system", "distrobox", "containers", "toolbx", "helix"]\n\n'
                '[commands]\n"KythOS system update" = "sudo -n bootc upgrade"\n'
                '"KythOS rclone update" = "sudo -n /usr/bin/kyth-rclone-update"\n'
            )
            f.flush()
            path = f.name

        self.assertFalse(migrate.needs_patch(path))


if __name__ == "__main__":
    unittest.main()
