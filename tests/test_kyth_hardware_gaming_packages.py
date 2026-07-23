"""Smoke tests for hardware/ and gaming/ service packages."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

try:
    from kyth_welcome.services import gaming, hardware
    from kyth_welcome.services.gaming.steam import _parse_steam_acf_text
    from kyth_welcome.services.hardware.display import _format_display_mode, _strip_ansi
    from kyth_welcome.services.hardware.types import HardwareProbe
except ImportError:
    raise unittest.SkipTest("PyQt6/PySide6 required by kyth_welcome.core_base → qt imports") from None


class HardwarePackageTests(unittest.TestCase):
    def test_public_surface(self):
        self.assertTrue(callable(hardware._detect_nvidia))
        self.assertTrue(callable(hardware._collect_hardware_probes))
        self.assertTrue(callable(hardware._detect_controllers))
        self.assertIs(hardware.HardwareProbe, HardwareProbe)

    def test_display_helpers(self):
        self.assertEqual(_strip_ansi("\x1b[32mOK\x1b[0m"), "OK")
        self.assertEqual(_format_display_mode("2560x1440@165.00"), "2560×1440 @ 165Hz")  # noqa: RUF001 — multiplication sign, matches display.py's output

    def test_hardware_probe_dataclass(self):
        probe = HardwareProbe("GPU", "ok", "fine", "details")
        self.assertEqual(probe.title, "GPU")
        self.assertIsNone(probe.action_cmd)


class NvidiaStatusViewTests(unittest.TestCase):
    """page_nvidia.py's whole status display is driven by this decision
    tree — no Qt, so it's testable directly without a display."""

    def _view(self, **overrides):
        base = dict(
            has_gpu=True, loaded=False, built=False, installed=True,
            hw_setup_done=False, svc_state="",
        )
        base.update(overrides)
        return hardware.nvidia_status_view(**base)

    def test_no_gpu(self):
        view = self._view(has_gpu=False)
        self.assertEqual(view.status_style, "status-dim")
        self.assertFalse(view.install_visible)
        self.assertFalse(view.reboot_visible)
        self.assertFalse(view.keep_polling)

    def test_loaded_is_the_happy_path(self):
        view = self._view(loaded=True, built=True)
        self.assertEqual(view.status_style, "status-ok")
        self.assertFalse(view.install_visible)
        self.assertFalse(view.reboot_visible)

    def test_built_but_not_loaded_prompts_reboot(self):
        view = self._view(built=True)
        self.assertEqual(view.status_style, "status-warn")
        self.assertTrue(view.reboot_visible)
        self.assertFalse(view.install_visible)

    def test_auto_building_shows_progress_and_keeps_polling(self):
        view = self._view(svc_state="activating")
        self.assertTrue(view.progress_visible)
        self.assertTrue(view.keep_polling)
        self.assertFalse(view.install_visible)

    def test_failed_build_offers_retry(self):
        view = self._view(hw_setup_done=True, svc_state="failed")
        self.assertEqual(view.status_style, "status-err")
        self.assertTrue(view.install_visible)
        self.assertEqual(view.install_text, "Retry Build")

    def test_installed_but_not_yet_built_offers_manual_build(self):
        view = self._view(installed=True)
        self.assertTrue(view.install_visible)
        self.assertEqual(view.install_text, "Build Driver Now")

    def test_missing_akmod_package_is_an_error(self):
        view = self._view(installed=False)
        self.assertEqual(view.status_style, "status-err")
        self.assertFalse(view.install_visible)

    def test_failed_state_without_hw_setup_done_falls_through_to_installed(self):
        # svc_state == "failed" alone isn't enough to offer a retry — the
        # hw-setup-done marker must also be present, otherwise this looks
        # like the ordinary "not built yet" case.
        view = self._view(installed=True, svc_state="failed", hw_setup_done=False)
        self.assertEqual(view.install_text, "Build Driver Now")


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
        cmd = gaming.scx_scheduler_command("scx_rusty")
        self.assertIsInstance(cmd, list)
        self.assertTrue(cmd)


if __name__ == "__main__":
    unittest.main()
