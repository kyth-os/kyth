"""ujust update must use Kyth's guarded updater, not Universal Blue's rpm-ostree path."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
JUST = ROOT / "build_files" / "just" / "kyth" / "system-updates.just"
UJUST_RECIPES = ROOT / "build_files" / "scripts" / "branding" / "31-ujust-recipes.sh"
AUTOMATIC = (
    ROOT / "build_files" / "scripts" / "sysconfig" / "systemd" / "36-disable-rpm-ostree-automatic.sh"
)
FULL_UPDATE = ROOT / "build_files" / "kyth-full-update"

# Representative Universal Blue 10-update.just recipe (trimmed).
UBLUE_UPDATE_JUST = """\
alias upgrade := update

update VERB_LEVEL="full":
    #!/usr/bin/bash
    update_command() {
        echo "Running $command..."
        $command
        echo "Completed $command"
    }
    update_command "rpm-ostree update"
    update_command "flatpak update -y"
"""


class UjustUpdateTests(unittest.TestCase):
    def test_update_recipe_runs_kyth_full_update(self):
        source = JUST.read_text(encoding="utf-8")
        self.assertIn("update VERB_LEVEL=", source)
        self.assertIn("exec /usr/bin/kyth-full-update", source)
        self.assertNotIn('update_command "rpm-ostree update"', source)
        self.assertTrue(FULL_UPDATE.is_file())

    def test_status_recipe_uses_bootc_guard(self):
        source = JUST.read_text(encoding="utf-8")
        self.assertIn("kyth-bootc-guard status", source)

    def test_update_recipe_lists_from_the_justfile(self):
        if shutil.which("just") is None:
            self.skipTest("just is unavailable on this validation runner")
        result = subprocess.run(
            ["just", "--justfile", str(JUST), "--list"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"(?m)^\s+update\b")

    def test_branding_renames_ublue_update_before_installing_kyth_just(self):
        source = UJUST_RECIPES.read_text(encoding="utf-8")
        rename_at = source.find("ublue-legacy-update")
        copy_at = source.find("cp /ctx/just/kyth.just")
        self.assertNotEqual(rename_at, -1)
        self.assertNotEqual(copy_at, -1)
        self.assertLess(rename_at, copy_at)
        self.assertIn("/usr/share/ublue-os/just/10-update.just", source)

    def test_ublue_update_rename_leaves_alias_pointing_at_update(self):
        """`alias upgrade := update` must keep resolving to Kyth's recipe."""
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "10-update.just"
            path.write_text(UBLUE_UPDATE_JUST, encoding="utf-8")
            rewritten = subprocess.run(
                [
                    "sed",
                    "-E",
                    "-e",
                    r"s/^update( VERB_LEVEL=|:)/ublue-legacy-update\1/",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("alias upgrade := update", rewritten)
            self.assertIn("ublue-legacy-update VERB_LEVEL=", rewritten)
            self.assertNotRegex(rewritten, r"(?m)^update[ :]")
            self.assertIn('update_command "rpm-ostree update"', rewritten)

    def test_image_disables_rpm_ostree_automatic_staging(self):
        source = AUTOMATIC.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/bin/bash"))
        self.assertIn("set -euo pipefail", source)
        self.assertIn("rpm-ostreed-automatic.timer", source)
        self.assertIn("AutomaticUpdatePolicy=none", source)
        self.assertNotRegex(source, r"(?m)^AutomaticUpdatePolicy=stage")


if __name__ == "__main__":
    unittest.main()
