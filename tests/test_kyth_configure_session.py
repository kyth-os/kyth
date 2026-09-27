"""kyth-configure-session must fail-open so PLM ExecStartPre cannot block login."""
from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

SCRIPT = ROOT / "build_files" / "kyth-configure-session"


def _load_configure_session():
    loader = SourceFileLoader("kyth_configure_session", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ConfigureSessionFailOpenTests(unittest.TestCase):
    def test_mkdir_failure_does_not_block_the_greeter(self):
        mod = _load_configure_session()
        conf_dir = mock.Mock()
        conf_dir.mkdir.side_effect = PermissionError("denied")
        with mock.patch.object(mod, "Path", return_value=conf_dir):
            self.assertEqual(mod.configure_session(), 0)

    def test_write_failure_does_not_block_the_greeter(self):
        mod = _load_configure_session()
        conf = mock.Mock()
        conf.write_text.side_effect = OSError("read-only")
        conf_dir = mock.Mock()
        conf_dir.__truediv__ = mock.Mock(return_value=conf)
        with mock.patch.object(mod, "Path", return_value=conf_dir):
            self.assertEqual(mod.configure_session(), 0)

    def test_default_writes_wayland_session(self):
        mod = _load_configure_session()
        conf = mock.Mock()
        conf_dir = mock.Mock()
        conf_dir.__truediv__ = mock.Mock(return_value=conf)
        with mock.patch.object(mod, "Path", return_value=conf_dir):
            self.assertEqual(mod.configure_session(), 0)
        written = conf.write_text.call_args.args[0]
        self.assertIn("DefaultSession=plasma.desktop", written)
        self.assertIn("Session=plasma.desktop", written)
        self.assertNotIn("plasmax11", written)

    def test_nomodeset_writes_wayland_session(self):
        mod = _load_configure_session()
        conf = mock.Mock()
        conf_dir = mock.Mock()
        conf_dir.__truediv__ = mock.Mock(return_value=conf)
        with mock.patch.object(mod, "Path", return_value=conf_dir):
            self.assertEqual(mod.configure_session(cmdline="quiet nomodeset"), 0)
        written = conf.write_text.call_args.args[0]
        self.assertIn("DefaultSession=plasma.desktop", written)
        self.assertNotIn("plasmax11", written)


class SessionConfOwnershipTests(unittest.TestCase):
    def test_static_plm_conf_documents_eleven_as_session_owner(self):
        body = (
            ROOT / "build_files/scripts/branding/13-plasmalogin-session-background.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("11-kyth-session.conf", body)
        self.assertIn("Wayland session default", body)
        self.assertIn("/etc/plasmalogin.conf.d/10-kyth.conf", body)
        self.assertIn("write_config /etc/plasmalogin.conf <<", body)
        self.assertIn("WallpaperPluginId=org.kde.image", body)
        self.assertIn("/var/lib/plasmalogin/wallpapers/kyth.svg", body)
        self.assertIn("tmpfiles.d/kyth-plasmalogin-wallpaper.conf", body)


if __name__ == "__main__":
    unittest.main()
