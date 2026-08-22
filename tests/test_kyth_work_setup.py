"""Wizard Work Ready orchestrator — real idempotent apply, not a success stub."""
from __future__ import annotations

import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_welcome.services.work import orchestrate_work_setup  # noqa: E402


def _completed(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class WorkSetupOrchestratorTests(unittest.TestCase):
    def test_dry_run_does_not_install(self):
        with patch(
            "kyth_welcome.services.work._app_installed", return_value=False
        ), patch(
            "kyth_welcome.services.work._install_work_flatpak"
        ) as install, patch(
            "kyth_welcome.services.work._fonts_check",
            return_value=(True, "Noto + MS fonts ready"),
        ):
            ok, msg = orchestrate_work_setup(dry_run=True)
        self.assertTrue(ok)
        self.assertIn("dry-run ok", msg)
        self.assertIn("Brave", msg)
        install.assert_not_called()

    def test_apply_installs_missing_work_apps(self):
        installed = {"com.brave.Browser": False, "org.libreoffice.LibreOffice": False}

        def _is_installed(app_id):
            return installed[app_id]

        def _install(app_id):
            installed[app_id] = True
            return True, "installed"

        with patch(
            "kyth_welcome.services.work._app_installed", side_effect=_is_installed
        ), patch(
            "kyth_welcome.services.work._install_work_flatpak", side_effect=_install
        ), patch(
            "kyth_welcome.services.work._fonts_check",
            return_value=(False, "Noto ready, MS via ujust install-ms-fonts"),
        ), patch(
            "kyth_welcome.services.work.create_m365_shortcuts", return_value=2
        ):
            ok, msg = orchestrate_work_setup(dry_run=False)
        self.assertTrue(ok)
        self.assertIn("Brave: installed", msg)
        self.assertIn("LibreOffice: installed", msg)
        self.assertIn("M365 shortcuts: 2 written", msg)

    def test_apply_reports_failure_instead_of_pretending_success(self):
        with patch(
            "kyth_welcome.services.work._app_installed", return_value=False
        ), patch(
            "kyth_welcome.services.work._install_work_flatpak",
            return_value=(False, "offline — will apply when networked"),
        ), patch(
            "kyth_welcome.services.work._fonts_check",
            return_value=(True, "Noto + MS fonts ready"),
        ), patch(
            "kyth_welcome.services.work.create_m365_shortcuts", return_value=0
        ):
            ok, msg = orchestrate_work_setup(dry_run=False)
        self.assertFalse(ok)
        self.assertIn("offline", msg)


if __name__ == "__main__":
    unittest.main()
