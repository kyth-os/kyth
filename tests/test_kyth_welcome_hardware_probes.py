import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.hardware import (  # noqa: E402
    _audio_probe,
    _codec_probe,
    _connectivity_probe,
    _controller_probe,
    _cpu_probe,
    _displaylink_probe,
    _firmware_probe,
    _gpu_probe,
    _memory_probe,
    _peripheral_probe,
    _platform_probe,
    _storage_probe,
    _thermal_probe,
)


class HardwareProbeTests(unittest.TestCase):
    def test_cpu_probe_reads_proc_cpuinfo_and_lscpu(self):
        cpuinfo = (
            "processor\t: 0\n"
            "model name\t: AMD Ryzen 7 7800X3D 8-Core Processor   \n"
            "processor\t: 1\n"
            "model name\t: AMD Ryzen 7 7800X3D 8-Core Processor   \n"
        )
        lscpu_out = "Core(s) per socket: 8\nSocket(s): 1\n"
        with (
            patch("builtins.open", unittest.mock.mock_open(read_data=cpuinfo)),
            patch("kyth_welcome.services.hardware.system._command_stdout", return_value=lscpu_out),
            patch("kyth_welcome.services.hardware.system._run_command", return_value=None),
        ):
            probe = _cpu_probe()

        self.assertEqual(probe.title, "CPU")
        self.assertEqual(probe.status, "ok")
        self.assertIn("AMD Ryzen 7 7800X3D 8-Core", probe.summary)

    def test_cpu_probe_handles_proc_error(self):
        with patch("builtins.open", side_effect=OSError("Access denied")):
            probe = _cpu_probe()

        self.assertEqual(probe.title, "CPU")
        self.assertEqual(probe.status, "dim")
        self.assertIn("Could not read", probe.summary)

    def test_memory_probe_calculates_ram_and_swap(self):
        meminfo = (
            "MemTotal:       32800000 kB\n"
            "MemAvailable:   16400000 kB\n"
        )
        with (
            patch("builtins.open", unittest.mock.mock_open(read_data=meminfo)),
            patch("kyth_welcome.services.hardware.system._command_stdout", return_value="/dev/zram0 4G zram\n"),
        ):
            probe = _memory_probe()

        self.assertEqual(probe.title, "Memory")
        self.assertEqual(probe.status, "ok")
        self.assertIn("31 GB RAM", probe.summary)
        self.assertIn("Swap:", probe.details)

    def test_thermal_probe_no_sensors(self):
        with patch("glob.glob", return_value=[]):
            probe = _thermal_probe()

        self.assertEqual(probe.title, "Thermal")
        self.assertEqual(probe.status, "dim")

    def test_storage_probe_warns_when_low_space(self):
        usage = MagicMock(total=100 * (1024**3), free=10 * (1024**3))
        with (
            patch("shutil.disk_usage", return_value=usage),
            patch("kyth_welcome.services.hardware.system._run_command", return_value=None),
        ):
            probe = _storage_probe()

        self.assertEqual(probe.title, "Storage")
        self.assertEqual(probe.status, "warn")
        self.assertIn("10.0% free space", probe.summary)

    def test_platform_probe_detects_vm(self):
        virt = MagicMock(returncode=0, stdout="qemu\n")
        spice = MagicMock(returncode=0)
        with patch("kyth_welcome.services.hardware.system._run_command", side_effect=[virt, spice]):
            probe = _platform_probe()

        self.assertEqual(probe.title, "Platform")
        self.assertEqual(probe.status, "dim")
        self.assertIn("inside qemu", probe.summary)

    def test_firmware_probe_no_fwupd(self):
        with patch("kyth_welcome.services.hardware.io._run_command", return_value=None):
            probe = _firmware_probe()

        self.assertEqual(probe.title, "Firmware")
        self.assertEqual(probe.status, "dim")

    def test_connectivity_probe_detects_wifi_and_bt(self):
        pci = "02:00.0 Network controller: Intel Corporation Wi-Fi 6 AX200"
        usb = "Bus 001 Device 002: ID 8087:0029 Intel Corp. AX200 Bluetooth"
        with (
            patch("kyth_welcome.services.hardware.io._command_stdout", side_effect=["", "wlan0:wifi:connected\n"]),
        ):
            probe = _connectivity_probe(pci, usb)

        self.assertEqual(probe.title, "Connectivity")
        self.assertEqual(probe.status, "ok")
        self.assertIn("Wi-Fi, Bluetooth", probe.summary)

    def test_audio_probe_healthy(self):
        pactl = MagicMock(returncode=0, stdout="Server Name: PulseAudio (on PipeWire 1.0)\n")
        pipewire = MagicMock(returncode=0)
        wireplumber = MagicMock(returncode=0)
        with (
            patch("kyth_welcome.services.hardware.io._run_command", side_effect=[pipewire, wireplumber, pactl]),
            patch("kyth_welcome.services.hardware.io._command_stdout", return_value="1 alsa_output.pci 16bit 2ch 44100Hz\n"),
        ):
            probe = _audio_probe()

        self.assertEqual(probe.title, "Audio")
        self.assertEqual(probe.status, "ok")
        self.assertIn("1 playback sink", probe.summary)

    def test_controller_probe_detects_xbox_dongle_and_firmware_hint(self):
        usb = "Bus 001 Device 005: ID 045e:02e6 Microsoft Corp. Xbox Wireless Adapter for Windows"
        lsmod = "xpad 40960 0\n"
        with (
            patch("os.listdir", return_value=[]),
            patch("shutil.which", return_value="/usr/bin/xone-dongle-install"),
        ):
            probe = _controller_probe(usb, lsmod)

        self.assertEqual(probe.title, "Controllers")
        self.assertEqual(probe.status, "warn")
        self.assertIn("firmware setup required", probe.summary)

    def test_peripheral_probe_detects_razer_and_openrazer(self):
        usb = "Bus 001 Device 003: ID 1532:007a Razer USA, Ltd Razer DeathAdder V2"
        daemon = MagicMock(returncode=0)
        with patch("kyth_welcome.services.hardware.io._run_command", return_value=daemon):
            probe = _peripheral_probe(usb)

        self.assertEqual(probe.title, "Peripherals")
        self.assertEqual(probe.status, "ok")
        self.assertIn("Razer", probe.summary)

    def test_displaylink_probe_active_driver(self):
        usb = "Bus 001 Device 004: ID 17e9:4307 DisplayLink USB-C Dock"
        lsmod = "evdi 122880 1\n"
        probe = _displaylink_probe(usb, lsmod)

        self.assertEqual(probe.title, "DisplayLink dock")
        self.assertEqual(probe.status, "ok")
        self.assertIn("driver active", probe.summary)

    def test_gpu_probe_detects_amdgpu(self):
        pci = "03:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 31 [Radeon RX 7900 XTX]"
        lsmod = "amdgpu 14417920 60\n"
        with patch("shutil.which", return_value="/usr/bin/glxinfo"):
            probe = _gpu_probe(pci, lsmod)

        self.assertEqual(probe.title, "Graphics")
        self.assertEqual(probe.status, "ok")
        self.assertIn("AMD GPU", probe.summary)
        self.assertIn("Radeon RX 7900 XTX", probe.details)

    def test_codec_probe_detects_vaapi(self):
        vainfo = "VAProfileH264Main : VAEntrypointVLD\nVAProfileHEVCMain : VAEntrypointVLD\n"
        with (
            patch("shutil.which", return_value="/usr/bin/vainfo"),
            patch("kyth_welcome.services.process._command_stdout", return_value=vainfo),
        ):
            probe = _codec_probe()

        self.assertEqual(probe.title, "Video Decode")
        self.assertEqual(probe.status, "ok")


if __name__ == "__main__":
    unittest.main()
