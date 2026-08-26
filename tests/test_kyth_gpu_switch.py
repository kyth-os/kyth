"""Hybrid-graphics GPU switching (services/hardware/gpu_switch.py) —
supergfxctl is never installed in CI, so every subprocess/shutil.which
call here is mocked; these tests only check that this module parses and
reacts to that CLI's output correctly."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.hardware import gpu_switch  # noqa: E402


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


class GpuSwitchTests(unittest.TestCase):
    def test_reports_unavailable_when_supergfxctl_missing(self):
        with patch("shutil.which", return_value=None):
            self.assertFalse(gpu_switch.supergfxctl_available())
            self.assertEqual(gpu_switch.current_mode(), "")
            self.assertEqual(gpu_switch.supported_modes(), ())
            ok, message = gpu_switch.set_mode("Hybrid")
        self.assertFalse(ok)
        self.assertIn("ujust install-asus-tools", message)

    def test_current_mode_strips_cli_output(self):
        with (
            patch("shutil.which", return_value="/usr/bin/supergfxctl"),
            patch.object(gpu_switch, "run_sync", return_value=_completed(stdout="Hybrid\n")),
        ):
            self.assertEqual(gpu_switch.current_mode(), "Hybrid")

    def test_supported_modes_parses_bracketed_csv(self):
        with (
            patch("shutil.which", return_value="/usr/bin/supergfxctl"),
            patch.object(gpu_switch, "run_sync", return_value=_completed(stdout="[Hybrid, Integrated, AsusMuxDgpu]\n")),
        ):
            self.assertEqual(gpu_switch.supported_modes(), ("Hybrid", "Integrated", "AsusMuxDgpu"))

    def test_supported_modes_falls_back_to_static_list_on_unparseable_output(self):
        with (
            patch("shutil.which", return_value="/usr/bin/supergfxctl"),
            patch.object(gpu_switch, "run_sync", return_value=_completed(stdout="")),
        ):
            self.assertEqual(gpu_switch.supported_modes(), gpu_switch.SUPPORTED_MODES)

    def test_set_mode_success(self):
        with (
            patch("shutil.which", return_value="/usr/bin/supergfxctl"),
            patch.object(gpu_switch, "run_sync", return_value=_completed(stdout="Setting mode to Hybrid\n")),
        ):
            ok, message = gpu_switch.set_mode("Hybrid")
        self.assertTrue(ok)
        self.assertIn("Hybrid", message)

    def test_set_mode_failure_surfaces_stderr(self):
        with (
            patch("shutil.which", return_value="/usr/bin/supergfxctl"),
            patch.object(gpu_switch, "run_sync", return_value=_completed(stderr="unsupported mode", returncode=1)),
        ):
            ok, message = gpu_switch.set_mode("Bogus")
        self.assertFalse(ok)
        self.assertEqual(message, "unsupported mode")

    def test_is_hybrid_system_reads_hardware_view(self):
        fake_view = SimpleNamespace(is_hybrid=True)
        fake_module = SimpleNamespace(get_hardware_view=lambda: fake_view)
        with patch.dict(sys.modules, {"kyth_shared.system.hardware_view": fake_module}):
            self.assertTrue(gpu_switch.is_hybrid_system())

    def test_is_hybrid_system_defaults_false_on_error(self):
        def _boom():
            raise OSError("no policy loaded")

        fake_module = SimpleNamespace(get_hardware_view=_boom)
        with patch.dict(sys.modules, {"kyth_shared.system.hardware_view": fake_module}):
            self.assertFalse(gpu_switch.is_hybrid_system())


if __name__ == "__main__":
    unittest.main()
