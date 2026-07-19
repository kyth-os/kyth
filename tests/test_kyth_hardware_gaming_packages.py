"""Smoke tests for hardware/ and gaming/ service packages."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

try:
    from kyth_welcome.services import gaming, hardware  # noqa: E402
    from kyth_welcome.services.gaming.steam import _parse_steam_acf_text  # noqa: E402
    from kyth_welcome.services.hardware.display import _format_display_mode, _strip_ansi  # noqa: E402
    from kyth_welcome.services.hardware.types import HardwareProbe  # noqa: E402
except ImportError:
    raise unittest.SkipTest("PyQt6/PySide6 required by kyth_welcome.core_base → qt imports")


class HardwarePackageTests(unittest.TestCase):
    def test_public_surface(self):
        self.assertTrue(callable(hardware._detect_nvidia))
        self.assertTrue(callable(hardware._collect_hardware_probes))
        self.assertTrue(callable(hardware._detect_controllers))
        self.assertIs(hardware.HardwareProbe, HardwareProbe)

    def test_display_helpers(self):
        self.assertEqual(_strip_ansi("\x1b[32mOK\x1b[0m"), "OK")
        self.assertEqual(_format_display_mode("2560x1440@165.00"), "2560×1440 @ 165Hz")

    def test_hardware_probe_dataclass(self):
        probe = HardwareProbe("GPU", "ok", "fine", "details")
        self.assertEqual(probe.title, "GPU")
        self.assertIsNone(probe.action_cmd)


class GamingPackageTests(unittest.TestCase):
    def test_public_surface(self):
        self.assertGreaterEqual(len(gaming.GAMING_TOOLS), 5)
        self.assertTrue(callable(gaming._gaming_health_items))
        self.assertTrue(callable(gaming._probe_windows_partitions))
        self.assertTrue(callable(gaming._find_ntfs_drives))  # re-export

    def test_parse_steam_acf_text(self):
        text = (
            '"AppState"\n'
            "{\n"
            '\t"appid"\t\t"440"\n'
            '\t"name"\t\t"Team Fortress 2"\n'
            "}\n"
        )
        data = _parse_steam_acf_text(text)
        self.assertEqual(data.get("appid"), "440")
        self.assertEqual(data.get("name"), "Team Fortress 2")

    def test_command_builders(self):
        cmd = gaming.scx_scheduler_command("scx_lavd")
        self.assertIsInstance(cmd, list)
        self.assertTrue(cmd)


if __name__ == "__main__":
    unittest.main()
