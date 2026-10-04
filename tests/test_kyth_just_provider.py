#!/usr/bin/env python3
"""Tests for branding/32-kyth-just-provider.sh (Fedora-base just delivery)."""

import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
PROVIDER = REPO / "build_files/scripts/branding/32-kyth-just-provider.sh"
UJUST_RECIPES = REPO / "build_files/scripts/branding/31-ujust-recipes.sh"


class JustProviderFragmentTests(unittest.TestCase):
    def test_fragment_exists(self):
        self.assertTrue(PROVIDER.is_file(), "32-kyth-just-provider.sh must exist")

    def test_noops_when_ujust_already_present(self):
        """On a ublue base (or any image already shipping ujust) the fragment
        must not install a competing shim or recipe tree."""
        source = PROVIDER.read_text(encoding="utf-8")
        self.assertIn("command -v ujust", source)

    def test_installs_kyth_owned_recipe_tree(self):
        source = PROVIDER.read_text(encoding="utf-8")
        self.assertIn("/usr/share/kyth/just/75-kyth.just", source)
        self.assertIn("/usr/share/kyth/just/kyth", source)
        self.assertIn("/usr/share/kyth/justfile", source)
        # Must not write into the ublue tree; that path belongs to 31's
        # ublue-base branch. (Comments may mention it; check code lines.)
        code = "\n".join(
            line for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertNotIn("/usr/share/ublue-os", code)

    def test_shim_execs_just_with_kyth_justfile(self):
        source = PROVIDER.read_text(encoding="utf-8")
        self.assertIn("/usr/bin/ujust", source)
        self.assertIn("exec /usr/bin/just --justfile /usr/share/kyth/justfile", source)

    def test_shim_keeps_documented_recipe_names(self):
        """The shim must preserve the `ujust <recipe>` contract (e.g.
        `ujust kyth-upgrade`) — it passes args through unchanged."""
        source = PROVIDER.read_text(encoding="utf-8")
        self.assertIn('"$@"', source)

    def test_31_skips_ublue_install_without_ublue_base(self):
        """31's ublue-tree install must be gated on the ublue justfile so a
        Fedora-base build doesn't leave a stray /usr/share/ublue-os tree."""
        source = UJUST_RECIPES.read_text(encoding="utf-8")
        self.assertIn("if [[ -f /usr/share/ublue-os/justfile ]]", source)


if __name__ == "__main__":
    unittest.main()
