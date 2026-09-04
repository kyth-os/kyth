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

    def test_local_build_paths_use_the_wrapper(self):
        for relative in ("build.just", "build_files/build-live-iso.sh"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("rootful-podman.sh", text, relative)


if __name__ == "__main__":
    unittest.main()
