"""Unit tests for kyth_shared.desktop.exe_handler."""
import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

HAS_QT = any(importlib.util.find_spec(b) for b in ("PySide6", "PyQt6"))

if HAS_QT:
    from kyth_shared.desktop.exe_handler import (
        is_rpm_installer,
        load_auto_bottles,
        normalise_filename,
        save_auto_bottles,
    )


class ExeHandlerTests(unittest.TestCase):
    def setUp(self):
        if not HAS_QT:
            self.skipTest("PySide6/PyQt6 not available")

    def test_normalise_filename(self):
        self.assertEqual(normalise_filename("Setup_Discord-1.2.3-x64.exe"), "discord")
        self.assertEqual(normalise_filename("steam_installer_win32.exe"), "steam")
        self.assertEqual(normalise_filename("Package.rpm"), "package")

    def test_is_rpm_installer(self):
        self.assertTrue(is_rpm_installer("foo.rpm"))
        self.assertTrue(is_rpm_installer("FOO.RPM"))
        self.assertFalse(is_rpm_installer("foo.exe"))

    def test_save_and_load_auto_bottles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = os.path.join(tmpdir, "kyth", "exe-handler.conf")
            self.assertFalse(load_auto_bottles(conf))
            save_auto_bottles(True, conf)
            self.assertTrue(load_auto_bottles(conf))
            save_auto_bottles(False, conf)
            self.assertFalse(load_auto_bottles(conf))

    def test_installer_worker_is_a_tracked_thread(self):
        from kyth_shared.desktop.exe_handler import _InstallerWorker
        from kyth_shared.desktop.qt_threads import TrackedThread

        self.assertTrue(issubclass(_InstallerWorker, TrackedThread))


if __name__ == "__main__":
    unittest.main()

