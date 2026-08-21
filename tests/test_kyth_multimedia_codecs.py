"""Codec packaging must use Fedora 44 package names and fail closed."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODECS = ROOT / "build_files/scripts/packages/04-multimedia-codecs.sh"
HYGIENE = ROOT / "build_files/scripts/packages/03-rpmfusion-and-repo-hygiene.sh"


class MultimediaCodecPackageTests(unittest.TestCase):
    def test_installs_plugin_libav_not_legacy_name_alone(self):
        body = CODECS.read_text(encoding="utf-8")
        self.assertIn("gstreamer1-plugin-libav", body)
        self.assertIn("gstreamer1-vaapi", body)
        # Fail-closed check must query the real RPM name.
        self.assertIn("gstreamer1-plugin-libav", body.split("required_codec_rpms=(")[1].split(")")[0])
        # Must not use --skip-unavailable on the required install (hides gaps).
        required_install = [
            line
            for line in body.splitlines()
            if "dnf5 install" in line and "allowerasing" in line
        ]
        self.assertTrue(required_install)
        self.assertTrue(all("--skip-unavailable" not in line for line in required_install))
        self.assertTrue(any("disablerepo=fedora-multimedia" in line for line in required_install))

    def test_hygiene_removes_multimedia_repo_files(self):
        body = HYGIENE.read_text(encoding="utf-8")
        self.assertIn("*multimedia*.repo", body)
        self.assertIn("fedora-multimedia.enabled=0", body)
        self.assertIn("fedora-multimedia", body)


if __name__ == "__main__":
    unittest.main()
