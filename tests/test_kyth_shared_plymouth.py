from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import plymouth


class PlymouthPolicyTests(unittest.TestCase):
    def test_collect_images_requires_matching_kernel_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot, modules = root / "boot", root / "modules"
            image = boot / "ostree/deploy/initramfs-6.12.img"
            image.parent.mkdir(parents=True)
            image.touch()
            (modules / "6.12").mkdir(parents=True)
            self.assertEqual(plymouth.collect_images(boot, modules), [image])

    def test_fingerprint_tracks_missing_and_changed_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "theme"
            missing = plymouth.fingerprint((str(path),))
            path.write_text("one", encoding="utf-8")
            first = plymouth.fingerprint((str(path),))
            path.write_text("two", encoding="utf-8")
            second = plymouth.fingerprint((str(path),))
            self.assertEqual(len({missing, first, second}), 3)

    @patch("kyth_shared.plymouth.shutil.which", return_value="/usr/bin/lsinitrd")
    @patch("kyth_shared.plymouth.run_optional")
    @patch("kyth_shared.plymouth.run_text")
    def test_inspection_rejects_fallback_theme(self, mock_text, mock_run, _which):
        listing = "\n".join((*plymouth.REQUIRED_ENTRIES, "usr/share/plymouth/themes/bgrt/theme"))
        defaults = "Theme=kyth\nShowDelay=0\nDeviceTimeout=8\n"
        mock_text.side_effect = [
            subprocess.CompletedProcess([], 0, listing, ""),
            subprocess.CompletedProcess([], 0, defaults, ""),
        ]
        mock_run.return_value = subprocess.CompletedProcess([], 1, b"", b"")
        errors = plymouth.inspect_image(Path("/boot/initramfs-test.img"))
        self.assertTrue(any("fallback theme" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
