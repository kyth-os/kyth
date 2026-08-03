import fnmatch
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
META_PATH = ROOT / "build_files" / "rechunk-meta.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "build.yml"


class RechunkMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(META_PATH.read_text(encoding="utf-8"))
        cls.groups = cls.document["meta"]
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_metadata_tracks_the_pinned_rechunker_revision(self):
        match = re.search(
            r"uses:\s+mrtrick37/legacy-rechunk@([0-9a-f]{40})",
            self.workflow,
        )
        self.assertIsNotNone(match)
        self.assertEqual(self.document["_source"], "mrtrick37/legacy-rechunk")
        self.assertEqual(self.document["_source_revision"], match.group(1))
        self.assertIn("meta: build_files/rechunk-meta.json", self.workflow)

    def test_large_independent_payloads_are_dedicated(self):
        expected = {
            "kyth-initramfs": ["/usr/lib/modules/*/initramfs"],
            "rpmdb": ["/usr/share/rpm/rpmdb.sqlite"],
        }
        for name, paths in expected.items():
            with self.subTest(group=name):
                self.assertEqual(self.groups[name]["files"], paths)
                self.assertIs(self.groups[name]["dedicated"], True)

    def test_kyth_group_covers_installer_and_system_hub_payloads(self):
        paths = set(self.groups["kyth"]["files"])
        self.assertIs(self.groups["kyth"]["dedicated"], False)
        self.assertIn("/usr/bin/kyth*", paths)
        self.assertIn("/usr/lib/kyth-*", paths)
        self.assertIn("/usr/libexec/kyth*", paths)
        self.assertIn("/usr/lib/systemd/system/kyth*", paths)
        self.assertIn("/usr/lib/systemd/user/kyth*", paths)
        self.assertIn("/usr/share/applications/kyth*", paths)
        self.assertIn("/usr/share/kyth*", paths)

    def test_kyth_group_covers_pip_installed_site_packages(self):
        # kyth_shared/kyth_welcome/kyth_installer are `pip install --prefix=/usr`'d
        # (not RPM packages), landing at
        # /usr/lib{,64}/python3.<minor>/site-packages/kyth_<name>/ — none of the
        # /usr/bin, /usr/lib/kyth-*, /usr/share/kyth* globs above match that nested
        # path, so without this the highest-churn Python source in the whole image
        # fell through to the single shared "unpackaged" dedicated layer alongside
        # unrelated large blobs like Proton-CachyOS.
        paths = set(self.groups["kyth"]["files"])
        self.assertIn("/usr/lib/python3*/site-packages/kyth_*", paths)
        self.assertIn("/usr/lib64/python3*/site-packages/kyth_*", paths)
        for pattern in ("/usr/lib/python3*/site-packages/kyth_*", "/usr/lib64/python3*/site-packages/kyth_*"):
            for pkg in ("kyth_shared", "kyth_welcome", "kyth_installer"):
                self.assertTrue(
                    fnmatch.fnmatch(f"/usr/lib/python3.13/site-packages/{pkg}", pattern.replace("lib64", "lib")),
                    f"{pattern} does not match a real {pkg} site-packages path",
                )

    def test_proton_cachyos_is_its_own_dedicated_layer(self):
        # A large, independently-versioned binary blob (extracted by
        # proton-cachyos.sh, not RPM-packaged) that previously had no group of
        # its own and fell through to "unpackaged" alongside unrelated content —
        # bundling it with the Python source above would have meant every
        # kyth_welcome/kyth_installer edit re-downloading a multi-hundred-MB
        # Proton build, and vice versa.
        self.assertEqual(
            self.groups["proton-cachyos"]["files"],
            ["/usr/share/steam/compatibilitytools.d/*"],
        )
        self.assertIs(self.groups["proton-cachyos"]["dedicated"], True)

    def test_custom_groups_precede_upstream_default_groups(self):
        names = list(self.groups)
        custom = ["kyth-initramfs", "rpmdb", "kyth"]
        self.assertEqual(names[: len(custom)], custom)
        self.assertIn("initramfs", self.groups)
        self.assertIn("kernel", self.groups)
        self.assertIn("ostree", self.groups)
        self.assertIn("plymouth", self.groups)
        self.assertIn("nvidia-xorg", self.groups)
        self.assertGreater(len(self.groups), 75)

    def test_workflow_rechunk_groups_match_metadata(self):
        match = re.search(r"for group in ([^;]+); do", self.workflow)
        self.assertIsNotNone(match, "Could not find 'for group in ...' loop in build.yml")
        workflow_groups = match.group(1).split()
        for g in workflow_groups:
            self.assertIn(
                g,
                self.groups,
                f"Workflow build.yml asserts rechunk group '{g}' which is missing from rechunk-meta.json",
            )

    def test_supply_chain_workflow_matches_carved_out_components(self):
        supply_chain_path = ROOT / ".github" / "workflows" / "supply-chain.yml"
        self.assertTrue(supply_chain_path.exists())
        content = supply_chain_path.read_text(encoding="utf-8")
        self.assertNotIn(
            'test -n "${PROTON_CACHYOS_VERSION}"',
            content,
            "supply-chain.yml contains strict non-empty assertion for carved-out PROTON_CACHYOS_VERSION",
        )


if __name__ == "__main__":
    unittest.main()
