"""Unit tests for the shared performance module."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.performance import (
    flush_page_caches,
    get_amd_ccd0_cpus,
    get_cpu_topology,
    get_current_epp,
    get_intel_pcores,
    get_power_profile,
    has_3d_vcache,
    set_epp,
    set_power_profile,
    set_transparent_hugepages,
    switch_sched_ext_profile,
)


class PerformanceTests(unittest.TestCase):
    def test_get_cpu_topology(self) -> None:
        cpuinfo = "vendor_id\t: AuthenticAMD\nmodel name\t: AMD Ryzen 7 7800X3D 8-Core Processor\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=cpuinfo)):
            vendor, model = get_cpu_topology()
            self.assertEqual(vendor, "AuthenticAMD")
            self.assertEqual(model, "AMD Ryzen 7 7800X3D 8-Core Processor")

    def test_has_3d_vcache(self) -> None:
        cpuinfo = "flags\t: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb rdtscp lm 3dnowprefetch...\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=cpuinfo)):
            self.assertTrue(has_3d_vcache())

    @mock.patch("pathlib.Path.is_file")
    @mock.patch("pathlib.Path.read_text")
    def test_get_amd_ccd0_cpus(self, mock_read, mock_is_file) -> None:
        mock_is_file.return_value = True
        mock_read.return_value = "0-7,16-23\n"
        self.assertEqual(get_amd_ccd0_cpus(), "0-7,16-23")

    @mock.patch("pathlib.Path.glob")
    @mock.patch("pathlib.Path.is_file")
    @mock.patch("pathlib.Path.read_text")
    def test_get_intel_pcores(self, mock_read, mock_is_file, mock_glob) -> None:
        mock_is_file.return_value = True
        mock_read.return_value = "5000000"
        mock_glob.return_value = [
            pathlib.Path("/sys/devices/system/cpu/cpu0"),
            pathlib.Path("/sys/devices/system/cpu/cpu1"),
        ]
        self.assertEqual(get_intel_pcores(), "0,1")

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_set_epp_sudo(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/bin/sudo"
        mock_run.return_value = mock.Mock(returncode=0)
        self.assertTrue(set_epp("performance"))
        mock_run.assert_called_once_with(
            ["sudo", "-n", "/usr/bin/kyth-set-epp", "performance"],
            capture_output=True,
            check=False,
            timeout=30,
        )

    @mock.patch("pathlib.Path.is_file")
    @mock.patch("pathlib.Path.read_text")
    def test_get_current_epp(self, mock_read, mock_is_file) -> None:
        mock_is_file.return_value = True
        mock_read.return_value = "balance_performance\n"
        self.assertEqual(get_current_epp(), "balance_performance")

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_set_power_profile(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/bin/powerprofilesctl"
        mock_run.return_value = mock.Mock(returncode=0)
        self.assertTrue(set_power_profile("balanced"))

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_get_power_profile(self, mock_which, mock_run) -> None:
        mock_which.return_value = "/bin/powerprofilesctl"
        mock_run.return_value = mock.Mock(returncode=0, stdout="performance\n")
        self.assertEqual(get_power_profile(), "performance")

    @mock.patch("os.access")
    @mock.patch("os.sync")
    def test_flush_page_caches(self, mock_sync, mock_access) -> None:
        mock_access.return_value = True
        with mock.patch("pathlib.Path.write_text") as mock_write:
            flush_page_caches()
            mock_sync.assert_called_once()
            mock_write.assert_called_once_with("3\n", encoding="utf-8")

    @mock.patch("os.access")
    def test_set_transparent_hugepages(self, mock_access) -> None:
        mock_access.return_value = True
        with mock.patch("pathlib.Path.write_text") as mock_write:
            set_transparent_hugepages("madvise")
            mock_write.assert_called_once_with("madvise\n", encoding="utf-8")

    @mock.patch("subprocess.run")
    @mock.patch("shutil.which")
    def test_switch_sched_ext_profile(self, mock_which, mock_run) -> None:
        mock_which.side_effect = lambda c: f"/bin/{c}" if c in ("scx_rusty", "sudo") else None
        switch_sched_ext_profile("rusty")
        mock_run.assert_called_once_with(
            ["sudo", "-n", "/usr/bin/kyth-scx", "set", "rusty"],
            capture_output=True,
            check=False,
            timeout=30,
        )

    @mock.patch("shutil.which")
    def test_get_gamescope_cmd(self, mock_which) -> None:
        from kyth_shared.performance import get_gamescope_cmd
        mock_which.return_value = "/usr/bin/gamescope"
        res = get_gamescope_cmd(["vkcube"])
        self.assertEqual(res, ["gamescope", "-f", "-e", "--rt", "--", "vkcube"])


if __name__ == "__main__":
    unittest.main()

