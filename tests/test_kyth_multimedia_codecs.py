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
        required_block = body.split("required_codec_rpms=(")[1].split(")")[0]
        self.assertIn("gstreamer1-plugin-libav", required_block)
        self.assertNotIn("gstreamer1-libav\n", required_block)
        # Required install must disable multimedia and must not skip-unavailable.
        self.assertIn("--disablerepo=fedora-multimedia", body)
        # The required dnf5 install block (through mozilla-openh264) must not skip.
        install_block = body.split("dnf5 install -y --allowerasing")[1].split("mozilla-openh264")[0]
        self.assertNotIn("--skip-unavailable", install_block)

    def test_hygiene_removes_multimedia_repo_files(self):
        body = HYGIENE.read_text(encoding="utf-8")
        self.assertIn("*multimedia*.repo", body)
        self.assertIn("fedora-multimedia.enabled=0", body)
        self.assertIn("fedora-multimedia", body)


if __name__ == "__main__":
    unittest.main()
