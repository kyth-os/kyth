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

    @patch("kyth_shared.plymouth.inspect_image", return_value=[])
    @patch("kyth_shared.plymouth.run")
    def test_refresh_builds_sidecar_then_atomically_renames(self, mock_run, _inspect):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "initramfs-6.12.img"
            image.write_bytes(b"live-image")
            include = Path(tmp) / "include"
            include.mkdir()

            def fake_dracut(argv, **kwargs):
                # Pretend dracut wrote the sidecar output.
                Path(argv[-2]).write_bytes(b"fresh-initramfs")
                return subprocess.CompletedProcess([], 0, "", "")

            mock_run.side_effect = fake_dracut
            plymouth._refresh_image(image, include)
            argv = mock_run.call_args[0][0]
            # dracut targets the .new sidecar, never the live image in place.
            self.assertIn(str(image) + ".new", argv)
            self.assertNotIn(str(image), [a for a in argv if a == str(image)])
            self.assertFalse((image.with_name(image.name + ".new")).exists())
            self.assertEqual(image.read_bytes(), b"fresh-initramfs")

    @patch("kyth_shared.plymouth.inspect_image", return_value=["bad initramfs"])
    @patch("kyth_shared.plymouth.run")
    def test_refresh_failure_removes_sidecar_and_scrubs_scratch(self, mock_run, _inspect):
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "initramfs-6.12.img"
            image.write_bytes(b"live-image")
            include = Path(tmp) / "include"
            include.mkdir()
            staged = image.with_name(image.name + ".new")
            with patch("kyth_shared.plymouth._scrub_dracut_scratch") as mock_scrub:
                with self.assertRaises(RuntimeError):
                    plymouth._refresh_image(image, include)
                mock_scrub.assert_called_once_with()
            # Live image untouched, sidecar cleaned up.
            self.assertEqual(image.read_bytes(), b"live-image")
            self.assertFalse(staged.exists())

    def test_scrub_removes_only_dracut_scratch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("kyth_shared.plymouth.Path") as mock_path:
                real_tmp = Path(tmp)
                mock_path.return_value = real_tmp
                (real_tmp / "dracut.abc123").mkdir()
                (real_tmp / "dracut.abc123" / "stage").write_text("x")
                (real_tmp / ".dracut-tmp").write_text("y")
                (real_tmp / "keep-me").write_text("z")
                plymouth._scrub_dracut_scratch()
                self.assertFalse((real_tmp / "dracut.abc123").exists())
                self.assertFalse((real_tmp / ".dracut-tmp").exists())
                self.assertTrue((real_tmp / "keep-me").exists())


if __name__ == "__main__":
    unittest.main()
