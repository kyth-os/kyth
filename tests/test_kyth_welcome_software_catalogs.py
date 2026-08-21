"""App Store static catalogs stay importable without Qt."""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.software_catalogs import (  # noqa: E402
    CURATED_APPIMAGES,
    FAMILIAR_APPS,
    SEC_BOX_NAME,
    STARTER_PACKS,
)


class SoftwareCatalogTests(unittest.TestCase):
    def test_starter_packs_have_apps(self):
        self.assertGreaterEqual(len(STARTER_PACKS), 3)
        for pack in STARTER_PACKS:
            self.assertTrue(pack["name"])
            self.assertTrue(pack["apps"])

    def test_familiar_and_appimages_nonempty(self):
        self.assertGreaterEqual(len(FAMILIAR_APPS), 10)
        self.assertGreaterEqual(len(CURATED_APPIMAGES), 3)
        self.assertEqual(SEC_BOX_NAME, "kali")

    def test_store_landing_catalogs(self):
        from kyth_welcome.services.software_catalogs import (
            STORE_CATEGORIES,
            STORE_SHELVES,
            TRENDING_APPS,
        )

        self.assertGreaterEqual(len(STORE_CATEGORIES), 5)
        self.assertGreaterEqual(len(TRENDING_APPS), 4)
        self.assertTrue(all("name" in shelf and "apps" in shelf for shelf in STORE_SHELVES))


if __name__ == "__main__":
    unittest.main()
