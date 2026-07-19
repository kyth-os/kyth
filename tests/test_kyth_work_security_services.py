"""Work + security pure services (Phase H)."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import security, work  # noqa: E402


class WorkServiceTests(unittest.TestCase):
    def test_ms_fonts_missing_dir(self):
        with mock.patch.object(work, "MS_FONTS_DIR", "/nonexistent/fonts"):
            self.assertFalse(work.ms_fonts_installed())

    def test_m365_icon_fallback(self):
        with mock.patch("os.path.exists", return_value=False):
            self.assertEqual(work.m365_icon("Outlook"), "internet-web-browser")
        with mock.patch("os.path.exists", return_value=True):
            self.assertEqual(work.m365_icon("Outlook"), "kyth-m365-outlook")

    def test_create_shortcuts_no_browser(self):
        with mock.patch.object(work, "m365_desktop_entry", return_value=None):
            self.assertEqual(work.create_m365_shortcuts(), 0)

    def test_convert_pst_missing_tool(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            ok, msg = work.convert_pst("/tmp/mail.pst")
        self.assertFalse(ok)
        self.assertIn("readpst", msg)


class SecurityServiceTests(unittest.TestCase):
    def test_kali_box_false_on_failure(self):
        with mock.patch.object(security, "_run_command", return_value=None):
            self.assertFalse(security.is_socket_capable_kali_box("kali"))

    def test_kali_box_true_when_privileged(self):
        r = mock.Mock(
            returncode=0,
            stdout="docker.io/kalilinux/kali-rolling\ntrue\nlabel=disable \n",
        )
        with mock.patch.object(security, "_run_command", return_value=r):
            self.assertTrue(security.is_socket_capable_kali_box("kali"))

    def test_command_builders(self):
        cmd = security.distrobox_create_command("kali", "img")
        self.assertEqual(cmd[0], "distrobox")
        self.assertIn("--root", cmd)
        self.assertIn("kali", cmd)
        enter = security.distrobox_enter_command("kali", "bash")
        self.assertEqual(enter[-1], "bash")
        rms = security.distrobox_remove_commands("kali")
        self.assertGreaterEqual(len(rms), 2)


class DiagnosticsDrainTests(unittest.TestCase):
    def test_storage_sense_and_security_shape(self):
        from kyth_welcome.services import diagnostics

        with mock.patch.object(
            diagnostics, "_run_command", return_value=mock.Mock(returncode=0, stdout="enabled\n", stderr=""),
        ):
            self.assertTrue(diagnostics.storage_sense_enabled())
        with mock.patch.object(
            diagnostics, "_run_command", return_value=mock.Mock(returncode=0, stdout="active\n", stderr=""),
        ), mock.patch.object(
            diagnostics, "_command_stdout", side_effect=["Enforcing", "SecureBoot enabled"],
        ), mock.patch.object(
            diagnostics, "_has_staged_update", return_value=False,
        ), mock.patch.object(
            diagnostics, "_has_rollback_deployment", return_value=True,
        ):
            rows = diagnostics.collect_security_status()
        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(all(len(r) == 3 for r in rows))


class ProbeExpandedTests(unittest.TestCase):
    def test_new_disk_ttl_keys(self):
        from kyth_welcome.services import probe

        for key in (
            "bootc-branch",
            "kernel-flavor",
            "flatpak-updates",
            "controllers-detect",
        ):
            self.assertIn(key, probe.DISK_TTL)

    def test_collect_snapshot_includes_new_sections(self):
        from kyth_welcome.services import probe

        with mock.patch(
            "kyth_welcome.services.bootc._fetch_bootc_status_data",
            return_value={"status": {"booted": {"image": {"reference": "ghcr.io/mrtrick37/kyth:testing"}}}},
        ), mock.patch(
            "kyth_welcome.services.bootc._fetch_bootc_status_text",
            return_value="",
        ), mock.patch(
            "kyth_welcome.services.bootc._current_kernel_flavor",
            return_value="cachy",
        ), mock.patch(
            "kyth_welcome.services.process._run_command",
        ) as run, mock.patch(
            "kyth_welcome.services.probe._count_flatpak_updates",
            return_value=3,
        ), mock.patch(
            "kyth_welcome.services.hardware.drives._detect_controllers",
            return_value={"secure_boot": False},
        ):
            def side_effect(cmd, timeout=5):
                if cmd and cmd[0] == "flatpak":
                    return mock.Mock(returncode=0, stdout="com.a.B\n")
                if cmd and cmd[0] == "lspci":
                    return mock.Mock(returncode=0, stdout="VGA AMD\n")
                return mock.Mock(returncode=1, stdout="")

            run.side_effect = side_effect
            sections = probe.collect_snapshot()

        self.assertEqual(sections["bootc-branch"], "testing")
        self.assertEqual(sections["kernel-flavor"], "cachy")
        self.assertEqual(sections["flatpak-updates"], 3)
        self.assertEqual(sections["controllers-detect"]["secure_boot"], False)
        self.assertIs(sections["nvidia-detect"], False)


if __name__ == "__main__":
    unittest.main()
