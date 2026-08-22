"""Wayland session defaults and software-compose rescue."""
from __future__ import annotations

import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.wayland_compose import (  # noqa: E402
    SDDM_WAYLAND_CONF,
    SOFTWARE_COMPOSE_ENV,
    apply_software_compose_env,
    compositor_argv,
    has_drm_render_node,
    hwgl_forced,
    is_live_image,
    needs_software_compose,
    nomodeset_requested,
    remove_legacy_virt_software_gl,
    sddm_session_conf,
)


class WaylandComposeTests(unittest.TestCase):
    def test_hwgl_and_live_cmdline_tokens(self) -> None:
        self.assertTrue(hwgl_forced("quiet kyth.hwgl=1 rhgb"))
        self.assertFalse(hwgl_forced("quiet rhgb"))
        self.assertTrue(is_live_image("quiet kyth.live=1"))
        self.assertTrue(is_live_image("quiet kyth.live"))
        self.assertFalse(is_live_image("quiet rhgb"))
        self.assertTrue(nomodeset_requested("quiet nomodeset"))
        self.assertFalse(nomodeset_requested("quiet rhgb"))
        self.assertEqual(sddm_session_conf("quiet"), SDDM_WAYLAND_CONF)
        self.assertEqual(sddm_session_conf("quiet nomodeset"), SDDM_WAYLAND_CONF)

    def test_render_node_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dri = Path(tmp)
            self.assertFalse(has_drm_render_node(dri))
            (dri / "card0").touch()
            self.assertFalse(has_drm_render_node(dri))
            (dri / "renderD128").touch()
            self.assertTrue(has_drm_render_node(dri))

    def test_software_compose_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dri = Path(tmp)
            self.assertTrue(needs_software_compose(dri=dri, cmdline="quiet"))
            (dri / "renderD128").touch()
            self.assertFalse(needs_software_compose(dri=dri, cmdline="quiet"))
            self.assertTrue(needs_software_compose(dri=dri, cmdline="kyth.live=1"))
            self.assertFalse(needs_software_compose(dri=dri, cmdline="kyth.live=1 kyth.hwgl=1"))
            empty = Path(tmp) / "empty"
            empty.mkdir()
            self.assertTrue(needs_software_compose(dri=empty, cmdline="nomodeset"))
            (empty / "renderD128").touch()
            self.assertTrue(needs_software_compose(dri=empty, cmdline="nomodeset"))
            self.assertFalse(needs_software_compose(dri=empty, cmdline="nomodeset kyth.hwgl=1"))
            bare = Path(tmp) / "bare"
            bare.mkdir()
            self.assertFalse(needs_software_compose(dri=bare, cmdline="kyth.hwgl=1"))
            self.assertTrue(needs_software_compose(dri=bare, cmdline="quiet"))

    def test_compose_env_and_compositor_argv(self) -> None:
        env: dict[str, str] = {}
        apply_software_compose_env(env)
        self.assertEqual(env["KWIN_COMPOSE"], "Q")
        self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "1")
        self.assertEqual(set(SOFTWARE_COMPOSE_ENV), set(env))
        self.assertEqual(
            compositor_argv(["--foo"]),
            [
                "kwin_wayland",
                "--drm",
                "--no-lockscreen",
                "--no-global-shortcuts",
                "--locale1",
                "--foo",
            ],
        )

    def test_sddm_conf_is_wayland_only(self) -> None:
        self.assertIn("DisplayServer=wayland", SDDM_WAYLAND_CONF)
        self.assertIn("DefaultSession=plasma.desktop", SDDM_WAYLAND_CONF)
        self.assertNotIn("x11", SDDM_WAYLAND_CONF)
        self.assertNotIn("plasmax11", SDDM_WAYLAND_CONF)

    def test_remove_legacy_virt_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env_dir = home / ".config" / "plasma-workspace" / "env"
            env_dir.mkdir(parents=True)
            legacy = env_dir / "10-kyth-qemu-safe.sh"
            legacy.write_text("systemd-detect-virt -q && export LIBGL_ALWAYS_SOFTWARE=1\n")
            self.assertTrue(remove_legacy_virt_software_gl(home))
            self.assertFalse(legacy.exists())
            self.assertFalse(remove_legacy_virt_software_gl(home))

    def test_configure_session_rewrites_stale_x11_dropin(self) -> None:
        launcher = ROOT / "build_files" / "kyth-configure-session"
        with tempfile.TemporaryDirectory() as tmp:
            sddm_dir = Path(tmp)
            stale = sddm_dir / "11-kyth-session.conf"
            stale.write_text("[General]\nDisplayServer=x11\nDefaultSession=plasmax11.desktop\n")
            sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))
            spec_globals = runpy.run_path(str(launcher), run_name="not-main")
            self.assertEqual(spec_globals["configure_session"](sddm_dir), 0)
            text = stale.read_text(encoding="utf-8")
            self.assertIn("DisplayServer=wayland", text)
            self.assertIn("DefaultSession=plasma.desktop", text)
            self.assertNotIn("plasmax11", text)

    def test_configure_session_keeps_wayland_for_nomodeset(self) -> None:
        launcher = ROOT / "build_files" / "kyth-configure-session"
        with tempfile.TemporaryDirectory() as tmp:
            sddm_dir = Path(tmp)
            spec_globals = runpy.run_path(str(launcher), run_name="not-main")
            self.assertEqual(
                spec_globals["configure_session"](sddm_dir, cmdline="quiet nomodeset"),
                0,
            )
            text = (sddm_dir / "11-kyth-session.conf").read_text(encoding="utf-8")
            self.assertIn("DisplayServer=wayland", text)
            self.assertIn("DefaultSession=plasma.desktop", text)
            self.assertNotIn("plasmax11", text)


class WaylandBrandingContractTests(unittest.TestCase):
    def test_sddm_image_default_is_wayland(self) -> None:
        fragment = (
            ROOT / "build_files" / "scripts" / "branding" / "13-sddm-session-background.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("DisplayServer=wayland", fragment)
        self.assertIn("DefaultSession=plasma.desktop", fragment)
        self.assertIn("CompositorCommand=/usr/bin/kyth-sddm-compositor", fragment)
        self.assertIn("SessionDir=/usr/share/kyth/no-xsessions", fragment)
        self.assertIn("install -d -m 0755 /usr/share/kyth/no-xsessions", fragment)
        self.assertIn("10-kyth-software-compose.sh", fragment)
        self.assertIn("nomodeset", fragment)
        self.assertNotIn("DisplayServer=x11", fragment)
        self.assertNotIn("plasmax11.desktop", fragment)
        self.assertNotIn("systemd-detect-virt", fragment)

    def test_session_pre_installs_compositor_wrapper(self) -> None:
        fragment = (
            ROOT / "build_files" / "scripts" / "branding" / "12-wayland-x11-autodetect.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("kyth-sddm-compositor", fragment)
        self.assertIn("ExecStartPre=/usr/bin/kyth-configure-session", fragment)
        compositor = (ROOT / "build_files" / "kyth-sddm-compositor").read_text(encoding="utf-8")
        self.assertIn("needs_software_compose", compositor)
        self.assertIn("kwin_wayland", compositor)

    def test_image_does_not_install_plasma_x11_session(self) -> None:
        baseline = (ROOT / "build_files" / "scripts" / "packages" / "05-baseline-desktop-tooling.sh").read_text(
            encoding="utf-8"
        )
        amd = (ROOT / "build_files" / "scripts" / "packages" / "13-gpu-amd-and-qemu-guest.sh").read_text(
            encoding="utf-8"
        )
        cleanup = (ROOT / "build_files" / "scripts" / "packages" / "17-desktop-package-cleanup.sh").read_text(
            encoding="utf-8"
        )
        for package in (
            "plasma-workspace-x11",
            "xorg-x11-server-Xorg",
            "xorg-x11-xinit",
            "xorg-x11-drv-libinput",
        ):
            self.assertNotIn(package, baseline)
            self.assertIn(package, cleanup)
        self.assertNotIn("xorg-x11-drv-amdgpu", amd)
        self.assertNotIn("xorg-x11-drv-ati", amd)
        self.assertIn("xorg-x11-drv-amdgpu", cleanup)
        self.assertIn("kwin-x11", cleanup)
        nvidia = (ROOT / "build_files" / "scripts" / "packages" / "16-gpu-nvidia.sh").read_text(encoding="utf-8")
        self.assertIn("xorg-x11-drv-nvidia", nvidia)
        self.assertNotIn("xorg-x11-drv-nvidia", cleanup)

    def test_live_iso_autologin_follows_wayland_default(self) -> None:
        body = (ROOT / "installer" / "build.sh").read_text(encoding="utf-8")
        self.assertIn("User=liveuser", body)
        self.assertNotIn("Session=plasmax11.desktop", body)
        self.assertNotIn("Session=plasma.desktop", body)
        self.assertIn("KWIN_COMPOSE=Q", body)


class SddmCompositorEntryTests(unittest.TestCase):
    def test_compositor_execs_kwin_with_software_env(self) -> None:
        launcher = ROOT / "build_files" / "kyth-sddm-compositor"
        exec_calls: list[tuple] = []

        def fake_execvp(binary: str, argv: list[str]) -> None:
            exec_calls.append((binary, argv))
            raise SystemExit(0)

        with (
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(sys, "argv", ["kyth-sddm-compositor"]),
            mock.patch("kyth_shared.wayland_compose.needs_software_compose", return_value=True),
            mock.patch("shutil.which", return_value="/usr/bin/kwin_wayland"),
            mock.patch("os.execvp", side_effect=fake_execvp),
        ):
            try:
                runpy.run_path(str(launcher), run_name="__main__")
            except SystemExit as exc:
                self.assertEqual(exc.code, 0)
            self.assertEqual(os.environ.get("KWIN_COMPOSE"), "Q")
            self.assertEqual(exec_calls[0][0], "/usr/bin/kwin_wayland")
            self.assertEqual(exec_calls[0][1][0], "/usr/bin/kwin_wayland")
            self.assertIn("--drm", exec_calls[0][1])


if __name__ == "__main__":
    unittest.main()
