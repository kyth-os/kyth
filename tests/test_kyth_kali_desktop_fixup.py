"""Behavioral tests for build_files/kyth-kali-desktop-fixup.

This script is the single shared implementation of "fix up Kali-exported
.desktop launchers for the host menu" — used by both the `ujust
setup-kali-box`/`export-kali-apps` CLI recipes and the System Hub Security
page's GUI install/export flow (services/security.py). Previously each of
those three call sites carried its own copy of this logic, which had already
drifted (the ujust setup-kali-box GUI branch was missing the pkexec/kdesu
sudo-rewrite that the other two copies had).

update-desktop-database/kbuildsycoca6 aren't available in this sandbox, so
they're stubbed onto PATH as no-ops; everything else runs for real against
a temp $HOME.
"""
from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "build_files" / "kyth-kali-desktop-fixup"


def _write_desktop(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def _run_fixup(home: pathlib.Path) -> subprocess.CompletedProcess:
    stub_bin = home / "stub-bin"
    stub_bin.mkdir(exist_ok=True)
    for stub in ("update-desktop-database", "kbuildsycoca6"):
        stub_path = stub_bin / stub
        stub_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub_path.chmod(stub_path.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PATH"] = f"{stub_bin}:{env['PATH']}"
    shared_path = str(ROOT / "build_files" / "kyth_shared")
    env["PYTHONPATH"] = f"{shared_path}:{env.get('PYTHONPATH', '')}"
    return subprocess.run(
        [str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
    )


class KaliDesktopFixupTests(unittest.TestCase):
    def test_script_parses_as_python(self):
        subprocess.run(["python3", "-m", "py_compile", str(SCRIPT)], check=True)

    def test_patches_categories_and_strips_display_hints_on_kali_entries(self):
        with tempfile.TemporaryDirectory() as home_dir:
            home = pathlib.Path(home_dir)
            apps = home / ".local" / "share" / "applications"
            apps.mkdir(parents=True)
            entry = apps / "kali-nmap.desktop"
            _write_desktop(
                entry,
                "[Desktop Entry]\n"
                "Name=nmap\n"
                "Exec=distrobox-enter --name kali -- nmap\n"
                "Categories=Network;\n"
                "NoDisplay=true\n"
                "OnlyShowIn=GNOME;\n"
                "NotShowIn=KDE;\n",
            )

            result = _run_fixup(home)
            self.assertEqual(result.returncode, 0, result.stderr)

            text = entry.read_text()
            self.assertIn("Categories=X-KythSecurity;", text)
            self.assertNotIn("NoDisplay=true", text)
            self.assertNotIn("OnlyShowIn=", text)
            self.assertNotIn("NotShowIn=", text)

    def test_rewrites_pkexec_escalation_to_sudo(self):
        with tempfile.TemporaryDirectory() as home_dir:
            home = pathlib.Path(home_dir)
            apps = home / ".local" / "share" / "applications"
            apps.mkdir(parents=True)
            entry = apps / "kali-wireshark.desktop"
            _write_desktop(
                entry,
                "[Desktop Entry]\n"
                "Name=Wireshark\n"
                "Exec=distrobox-enter --name kali -- pkexec wireshark\n"
                "Categories=Network;\n",
            )

            result = _run_fixup(home)
            self.assertEqual(result.returncode, 0, result.stderr)

            text = entry.read_text()
            self.assertIn("sudo -E wireshark", text)
            self.assertNotIn("pkexec", text)

    def test_ignores_entries_not_belonging_to_kali(self):
        with tempfile.TemporaryDirectory() as home_dir:
            home = pathlib.Path(home_dir)
            apps = home / ".local" / "share" / "applications"
            apps.mkdir(parents=True)
            entry = apps / "firefox.desktop"
            original = (
                "[Desktop Entry]\n"
                "Name=Firefox\n"
                "Exec=firefox %u\n"
                "Categories=Network;\n"
                "NoDisplay=true\n"
            )
            _write_desktop(entry, original)

            result = _run_fixup(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(entry.read_text(), original)

    def test_repoints_zenmap_root_launcher_through_distrobox_root_launch(self):
        with tempfile.TemporaryDirectory() as home_dir:
            home = pathlib.Path(home_dir)
            apps = home / ".local" / "share" / "applications"
            apps.mkdir(parents=True)
            entry = apps / "kali-zenmap-root.desktop"
            _write_desktop(
                entry,
                "[Desktop Entry]\n"
                "Name=Zenmap (as root)\n"
                "Exec=distrobox-enter --name kali -- zenmap\n"
                "TryExec=distrobox-enter\n"
                "Categories=Network;\n",
            )

            result = _run_fixup(home)
            self.assertEqual(result.returncode, 0, result.stderr)

            text = entry.read_text()
            self.assertIn(
                "Exec=kyth-distrobox-root-launch --root kali /usr/bin/zenmap", text,
            )
            self.assertIn("TryExec=kyth-distrobox-root-launch", text)

    def test_no_desktop_files_is_a_noop(self):
        with tempfile.TemporaryDirectory() as home_dir:
            home = pathlib.Path(home_dir)
            (home / ".local" / "share" / "applications").mkdir(parents=True)
            result = _run_fixup(home)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
