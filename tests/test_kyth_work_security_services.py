"""Work + security pure services (Phase H)."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

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
            ok, msg = work.convert_pst("/tmp/mail.pst")  # noqa: S108 — fixture string, not a real path opened on disk
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

    def test_kali_create_command_shape(self):
        cmd = security.build_kali_create_command("kali", "img", "kali-linux-headless", False)
        self.assertEqual(cmd[:2], ["bash", "-c"])
        script = cmd[2]
        self.assertIn("box='kali'", script)
        self.assertIn("image='img'", script)
        self.assertIn("kali-linux-headless", script)
        self.assertNotIn("distrobox-export", script)

    def test_kali_create_command_gui_tier_bulk_exports_apps(self):
        cmd = security.build_kali_create_command("kali", "img", "kali-linux-default", True)
        script = cmd[2]
        self.assertIn("distrobox-export --app", script)
        # Desktop-file fixup (Categories, NoDisplay, pkexec rewrite, zenmap
        # Exec rewrite) lives in build_files/kyth-kali-desktop-fixup, shared
        # with export-kali-apps below and the `ujust` CLI recipes, instead of
        # being duplicated inline here.
        self.assertIn("kyth-kali-desktop-fixup", script)

    def test_kali_export_command_shape(self):
        cmd = security.build_kali_export_command("kali")
        self.assertEqual(cmd[:2], ["bash", "-c"])
        self.assertIn("EXPORTED:$n", cmd[2])
        self.assertIn("kyth-kali-desktop-fixup", cmd[2])

    def test_kali_remove_command_shape(self):
        cmd = security.build_kali_remove_command("kali")
        self.assertEqual(cmd[:2], ["bash", "-c"])
        self.assertIn("box='kali'", cmd[2])
        self.assertIn("distrobox rm --force", cmd[2])
        self.assertIn("distrobox rm --root --force", cmd[2])

    def test_kali_command_builders_generate_syntactically_valid_bash(self):
        # These scripts are assembled via string concatenation/f-strings with
        # heavy quote nesting and no on-disk .sh file for
        # test_shell_scripts_validation.py to catch — unlike real .sh files,
        # nothing else runs bash -n over this output. A quoting bug here would
        # otherwise only surface by actually running it inside a live
        # distrobox.
        scripts = [
            security.build_kali_create_command("kali", "docker.io/kalilinux/kali-rolling", "kali-linux-headless", False)[2],
            security.build_kali_create_command("kali", "docker.io/kalilinux/kali-rolling", "kali-linux-default", True)[2],
            security.build_kali_create_command("kali", "docker.io/kalilinux/kali-rolling", "kali-linux-everything", True)[2],
            security.build_kali_export_command("kali")[2],
            security.build_kali_remove_command("kali")[2],
        ]
        for script in scripts:
            with self.subTest(script=script[:60]):
                result = subprocess.run(
                    ["bash", "-n", "-c", script],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


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
        from kyth_shared.system import probe

        with mock.patch(
            "kyth_shared.system.bootc._fetch_bootc_status_data",
            return_value={"status": {"booted": {"image": {"reference": "ghcr.io/mrtrick37/kyth:testing"}}}},
        ), mock.patch(
            "kyth_shared.system.bootc._fetch_bootc_status_text",
            return_value="",
        ), mock.patch(
            "kyth_shared.system.bootc._current_kernel_flavor",
            return_value="cachy",
        ), mock.patch(
            "kyth_shared.system.process._run_command",
        ) as run, mock.patch(
            "kyth_shared.system.probe._count_flatpak_updates",
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


class KaliInstallProgressTrackerTests(unittest.TestCase):
    def test_tracker_lifecycle(self):
        tracker = security.KaliInstallProgressTracker()

        # Phase 0/1: Pulling image layers
        msg, prog = tracker.parse_line("Trying to pull docker.io/kalilinux/kali-rolling...")
        self.assertEqual(msg, "Pulling kalilinux/kali-rolling from registry…")
        self.assertEqual(prog, 3)

        msg, prog = tracker.parse_line("Copying blob sha256:1234567890abcdef1234")
        self.assertEqual(msg, "Pulling image layer sha256:1234567890ab…")
        self.assertEqual(prog, 4)

        # Storing manifest
        msg, prog = tracker.parse_line("Writing manifest to image destination")
        self.assertEqual(msg, "Storing image manifest…")
        self.assertEqual(prog, 42)

        # Creating container
        msg, prog = tracker.parse_line("Creating container kali...")
        self.assertEqual(msg, "Creating Kali distrobox container…")
        self.assertEqual(prog, 44)

        # Phase 2: Bootstrapping
        msg, prog = tracker.parse_line("Installing basic packages...")
        self.assertEqual(msg, "Bootstrapping Kali environment…")
        self.assertEqual(prog, 55)

        # Phase 3: Fetching package lists & resolving deps
        msg, prog = tracker.parse_line("Reading package lists...")
        self.assertEqual(msg, "Fetching Kali package lists…")
        self.assertEqual(prog, 56)

        msg, prog = tracker.parse_line("The following new packages will be installed:")
        self.assertEqual(msg, "Resolving package dependencies…")
        self.assertEqual(prog, 58)

        # Set total packages
        msg, prog = tracker.parse_line("10 newly installed, 0 to remove")
        self.assertIsNone(msg)
        self.assertIsNone(prog)
        self.assertEqual(tracker.total_packages, 10)

        # Triggers download phase 4
        msg, prog = tracker.parse_line("Need to get 15.0 MB of archives.")
        self.assertEqual(msg, "Downloading 15.0 MB of packages (10 packages)…")
        self.assertEqual(prog, 60)

        # Phase 4: Download packages
        msg, prog = tracker.parse_line("Get:1 http://http.kali.org/kali kali-rolling/main amd64 nmap 7.93 [5.0 MB]")
        self.assertEqual(msg, "Downloading nmap… (1 / 10)")
        self.assertEqual(prog, 61)  # 60 + 0.1 * 15 = 61.5 -> 61

        msg, prog = tracker.parse_line("Get:10 http://http.kali.org/kali kali-rolling/main amd64 wireshark 4.0 [10.0 MB]")
        self.assertEqual(msg, "Downloading wireshark… (10 / 10)")
        self.assertEqual(prog, 75)  # 60 + 1.0 * 15 = 75

        # Preparing to unpack
        msg, prog = tracker.parse_line("Preparing to unpack .../nmap_7.93_amd64.deb ...")
        self.assertEqual(msg, "Unpacking packages… (0 / 10)")
        self.assertIsNone(prog)
        self.assertEqual(tracker.progress_value, 75)

        # Phase 5: Unpacking
        msg, prog = tracker.parse_line("Unpacking nmap (7.93) ...")
        self.assertEqual(msg, "Unpacking nmap… (1 / 10)")
        self.assertEqual(prog, 76)  # 75 + 0.1 * 13 = 76.3 -> 76
        self.assertEqual(tracker.progress_value, 76)

        msg, prog = tracker.parse_line("Setting up nmap (7.93) ...")
        self.assertEqual(msg, "Configuring nmap… (1 / 10)")
        self.assertEqual(prog, 89)  # 88 + 0.1 * 10 = 89

        # Phase 6: Configuring
        msg, prog = tracker.parse_line("Setting up wireshark (4.0) ...")
        self.assertEqual(msg, "Configuring wireshark… (2 / 10)")
        self.assertEqual(prog, 90)  # 88 + 0.2 * 10 = 90

        # Processing triggers
        msg, prog = tracker.parse_line("Processing triggers for man-db (2.10.2-1) ...")
        self.assertEqual(msg, "Running post-install triggers (man-db)…")
        self.assertEqual(prog, 98)


if __name__ == "__main__":
    unittest.main()
