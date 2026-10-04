from __future__ import annotations

import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "build_files" / "scripts" / "rootful-podman.sh"


class RootfulPodmanWrapperTests(unittest.TestCase):
    def test_wrapper_is_bash_valid_and_isolates_cgroups(self):
        result = subprocess.run(["bash", "-n", str(WRAPPER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("unshare --cgroup podman", text)
        self.assertIn("--preserve-env=MOK_KEY", text)
        self.assertIn("distrobox-host-exec", text)
        self.assertIn('podman "$@"', text)
        self.assertIn("CONTAINER_ID", text)
        self.assertIn("/run/host/usr/bin/distrobox-host-exec", text)
        self.assertIn("XDG_RUNTIME_DIR", text)

    def test_local_build_paths_use_the_wrapper(self):
        for relative in ("build.just", "build_files/build-live-iso.sh"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("rootful-podman.sh", text, relative)

    def test_local_live_iso_requires_registry_source_without_exporting_layers(self):
        text = (ROOT / "build_files" / "build-live-iso.sh").read_text(encoding="utf-8")
        self.assertNotIn("skopeo copy", text)
        self.assertNotIn("LOCAL_IMAGE_DIR", text)
        self.assertIn("INSTALL_SOURCE_IMAGE to a signed registry digest", text)
        self.assertIn('INSTALL_SOURCE_IMAGE="${INSTALL_SOURCE_IMAGE:-${BASE_IMAGE}}"', text)
        self.assertIn("INSTALLER_BUILD_HASH", text)


if __name__ == "__main__":
    unittest.main()
