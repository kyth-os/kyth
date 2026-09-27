"""Codec packaging must use Fedora 44 package names and fail closed."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODECS = ROOT / "build_files/scripts/packages/04-multimedia-codecs.sh"
HYGIENE = ROOT / "build_files/scripts/packages/03-rpmfusion-and-repo-hygiene.sh"
DOCKERFILE = ROOT / "Dockerfile"
MESA_GIT = ROOT / "build_files/scripts/mesa-git.sh"


class MultimediaCodecPackageTests(unittest.TestCase):
    def test_installs_plugin_libav_and_bad_free_for_va(self):
        body = CODECS.read_text(encoding="utf-8")
        self.assertIn("gstreamer1-plugin-libav", body)
        self.assertIn("gstreamer1-plugins-bad-free", body)
        # Fail-closed check must query real RPM names, not the obsolete vaapi NEVRA.
        required_block = body.split("required_codec_rpms=(")[1].split(")")[0]
        self.assertIn("gstreamer1-plugin-libav", required_block)
        self.assertIn("gstreamer1-plugins-bad-free", required_block)
        self.assertNotIn("gstreamer1-libav\n", required_block)
        self.assertNotIn("gstreamer1-vaapi\n", required_block)
        # VA capability is asserted via Provide + libgstva.so, not rpm -q NEVRA.
        self.assertIn("rpm -q --whatprovides gstreamer1-vaapi", body)
        self.assertIn("libgstva.so", body)
        # Required install must not skip-unavailable; multimedia repo is removed in 03.
        self.assertNotIn("--disablerepo=fedora-multimedia", body)
        install_block = body.split("dnf5 install -y --allowerasing")[1].split("mozilla-openh264")[0]
        self.assertNotIn("--skip-unavailable", install_block)
        self.assertNotIn("gstreamer1-vaapi", install_block)

    def test_hygiene_removes_multimedia_repo_files(self):
        body = HYGIENE.read_text(encoding="utf-8")
        self.assertIn("*multimedia*.repo", body)
        self.assertIn("fedora-multimedia.enabled=0", body)
        self.assertIn("fedora-multimedia", body)

    def test_post_package_layers_do_not_disablerepo_removed_multimedia(self):
        # packages/03 deletes fedora-multimedia; dnf5 exits 2 if later layers
        # still pass --disablerepo for a missing repo id.
        for path in (DOCKERFILE, MESA_GIT):
            body = path.read_text(encoding="utf-8")
            code_lines = [
                line
                for line in body.splitlines()
                if line.lstrip() and not line.lstrip().startswith("#")
            ]
            code = "\n".join(code_lines)
            self.assertNotIn("--disablerepo='fedora-multimedia'", code, path.name)
            self.assertNotIn('--disablerepo="fedora-multimedia"', code, path.name)
            self.assertNotIn("--disablerepo=fedora-multimedia", code, path.name)


if __name__ == "__main__":
    unittest.main()
