"""Unit tests for the shared GPU detection module."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.system.gpu import (
    is_kernel_module_loaded,
    loaded_kernel_modules,
    lspci_gpu_lines,
    rpm_package_installed,
    run_lspci_nn,
)


class GpuTests(unittest.TestCase):
    @mock.patch("subprocess.run")
    def test_run_lspci_nn(self, mock_run) -> None:
        mock_run.return_value = mock.Mock(stdout="00:02.0 VGA compatible controller [0300]: Intel Corp\n")
        lines = run_lspci_nn()
        self.assertEqual(lines, ["00:02.0 VGA compatible controller [0300]: Intel Corp"])
        mock_run.assert_called_once_with(["lspci", "-nn"], capture_output=True, text=True, check=False, timeout=30)

    @mock.patch("subprocess.run")
    def test_run_lspci_nn_missing_binary(self, mock_run) -> None:
        mock_run.side_effect = FileNotFoundError
        self.assertEqual(run_lspci_nn(), [])

    @mock.patch("kyth_shared.system.gpu.run_lspci_nn")
    def test_lspci_gpu_lines_filters_display_controllers(self, mock_lspci) -> None:
        mock_lspci.return_value = [
            "00:02.0 VGA compatible controller [0300]: Intel Corp",
            "00:1f.3 Audio device [0403]: Intel Corp",
            "01:00.0 3D controller [0302]: NVIDIA Corp",
        ]
        self.assertEqual(
            lspci_gpu_lines(),
            [
                "00:02.0 VGA compatible controller [0300]: Intel Corp",
                "01:00.0 3D controller [0302]: NVIDIA Corp",
            ],
        )

    def test_loaded_kernel_modules(self) -> None:
        data = "nvidia 12345 0 - Live 0x0\ni915 98765 2 - Live 0x0\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=data)):
            modules = loaded_kernel_modules()
        self.assertEqual(modules, {"nvidia", "i915"})

    def test_loaded_kernel_modules_missing_proc(self) -> None:
        with mock.patch("builtins.open", side_effect=OSError):
            self.assertEqual(loaded_kernel_modules(), set())

    @mock.patch("kyth_shared.system.gpu.loaded_kernel_modules")
    def test_is_kernel_module_loaded(self, mock_loaded) -> None:
        mock_loaded.return_value = {"amdgpu"}
        self.assertTrue(is_kernel_module_loaded("amdgpu"))
        self.assertFalse(is_kernel_module_loaded("nvidia"))

    @mock.patch("subprocess.run")
    def test_rpm_package_installed(self, mock_run) -> None:
        mock_run.return_value = mock.Mock(returncode=0)
        self.assertTrue(rpm_package_installed("akmod-nvidia"))
        mock_run.assert_called_once_with(["rpm", "-q", "akmod-nvidia"], capture_output=True, check=False, timeout=30)

    @mock.patch("subprocess.run")
    def test_rpm_package_installed_missing(self, mock_run) -> None:
        mock_run.return_value = mock.Mock(returncode=1)
        self.assertFalse(rpm_package_installed("akmod-nvidia"))


if __name__ == "__main__":
    unittest.main()
