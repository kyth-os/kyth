"""kyth-configure-session must fail-open so SDDM ExecStartPre cannot block login."""
from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
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
        sddm_dir = mock.Mock()
        sddm_dir.mkdir.side_effect = PermissionError("denied")
        with mock.patch.object(mod, "Path", return_value=sddm_dir):
            self.assertEqual(mod.configure_session(), 0)

    def test_write_failure_does_not_block_the_greeter(self):
        mod = _load_configure_session()
        conf = mock.Mock()
        conf.write_text.side_effect = OSError("read-only")
        sddm_dir = mock.Mock()
        sddm_dir.__truediv__ = mock.Mock(return_value=conf)
        with mock.patch.object(mod, "Path", return_value=sddm_dir), mock.patch.object(
            mod.shutil, "which", return_value=None
        ):
            self.assertEqual(mod.configure_session(), 0)

    def test_bare_metal_writes_wayland_session(self):
        mod = _load_configure_session()
        conf = mock.Mock()
        sddm_dir = mock.Mock()
        sddm_dir.__truediv__ = mock.Mock(return_value=conf)
        with mock.patch.object(mod, "Path", return_value=sddm_dir), mock.patch.object(
            mod.shutil, "which", return_value=None
        ):
            self.assertEqual(mod.configure_session(), 0)
        written = conf.write_text.call_args.args[0]
        self.assertIn("DisplayServer=wayland", written)
        self.assertIn("DefaultSession=plasma.desktop", written)

    def test_virtual_machine_writes_x11_session(self):
        mod = _load_configure_session()
        conf = mock.Mock()
        sddm_dir = mock.Mock()
        sddm_dir.__truediv__ = mock.Mock(return_value=conf)
        with mock.patch.object(mod, "Path", return_value=sddm_dir), mock.patch.object(
            mod.shutil, "which", return_value="/usr/bin/systemd-detect-virt"
        ), mock.patch.object(mod, "run_command", return_value=SimpleNamespace(returncode=0)):
            self.assertEqual(mod.configure_session(), 0)
        written = conf.write_text.call_args.args[0]
        self.assertIn("DisplayServer=x11", written)
        self.assertIn("DefaultSession=plasmax11.desktop", written)


class SessionConfOwnershipTests(unittest.TestCase):
    def test_static_sddm_conf_documents_eleven_as_session_owner(self):
        body = (ROOT / "build_files/scripts/branding/13-sddm-session-background.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("11-kyth-session.conf", body)
        self.assertIn("conservative X11 fallback", body)
        self.assertIn("/etc/sddm.conf.d/10-kyth.conf", body)


if __name__ == "__main__":
    unittest.main()
