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
            "headroom": ["/usr/lib/headroom/*", "/usr/bin/headroom"],
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

    def test_custom_groups_precede_upstream_default_groups(self):
        names = list(self.groups)
        custom = ["kyth-initramfs", "headroom", "rpmdb", "kyth"]
        self.assertEqual(names[: len(custom)], custom)
        self.assertIn("initramfs", self.groups)
        self.assertIn("kernel", self.groups)
        self.assertIn("ostree", self.groups)
        self.assertIn("plymouth", self.groups)
        self.assertIn("nvidia-xorg", self.groups)
        self.assertGreater(len(self.groups), 75)


if __name__ == "__main__":
    unittest.main()
