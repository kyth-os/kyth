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
    PLASMA_WAYLAND_SESSION,
    PLM_SESSION_CONF,
    SOFTWARE_COMPOSE_ENV,
    apply_software_compose_env,
    compositor_argv,
    greeter_session_conf,
    has_drm_card,
    has_drm_render_node,
    hwgl_forced,
    is_live_image,
    migrate_greeter_last_session,
    migrate_home_dmrcs,
    migrate_user_dmrc,
    needs_software_compose,
    software_compose_rescue_justified,
    nomodeset_requested,
    remove_legacy_virt_software_gl,
    session_is_plasma_x11,
    write_greeter_compose_env,
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
        self.assertEqual(greeter_session_conf("quiet"), PLM_SESSION_CONF)
        self.assertEqual(greeter_session_conf("quiet nomodeset"), PLM_SESSION_CONF)

    def test_render_node_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dri = Path(tmp)
            self.assertFalse(has_drm_render_node(dri))
            self.assertFalse(has_drm_card(dri))
            (dri / "card0").touch()
            self.assertFalse(has_drm_render_node(dri))
            self.assertTrue(has_drm_card(dri))
            (dri / "renderD128").touch()
            self.assertTrue(has_drm_render_node(dri))
            self.assertTrue(has_drm_card(dri))

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
    def test_software_compose_rescue_justified_ignores_missing_drm(self) -> None:
        self.assertTrue(software_compose_rescue_justified("quiet nomodeset"))
        self.assertTrue(software_compose_rescue_justified("quiet kyth.live"))
        self.assertFalse(software_compose_rescue_justified("quiet"))


    def test_compose_env_and_compositor_argv(self) -> None:
        env: dict[str, str] = {}
        apply_software_compose_env(env)
        self.assertEqual(env["KWIN_COMPOSE"], "Q")
        self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "1")
        self.assertEqual(set(SOFTWARE_COMPOSE_ENV), set(env))
        self.assertEqual(compositor_argv(["--foo"]), ["kwin_wayland", "--foo"])
        self.assertEqual(
            compositor_argv(),
            [
                "kwin_wayland",
                "--no-lockscreen",
                "--no-global-shortcuts",
                "--no-kactivities",
                "--inputmethod",
                "plasma-keyboard",
                "--locale1",
            ],
        )

    def test_plm_conf_is_wayland_only(self) -> None:
        self.assertIn("DefaultSession=plasma.desktop", PLM_SESSION_CONF)
        self.assertIn("Session=plasma.desktop", PLM_SESSION_CONF)
        self.assertNotIn("plasmax11", PLM_SESSION_CONF)
        self.assertNotIn("DisplayServer=x11", PLM_SESSION_CONF)

    def test_write_greeter_compose_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kyth-greeter.env"
            with mock.patch(
                "kyth_shared.wayland_compose.needs_software_compose", return_value=True
            ):
                self.assertTrue(write_greeter_compose_env(path))
            text = path.read_text(encoding="utf-8")
            self.assertIn("KWIN_COMPOSE=Q", text)
            self.assertIn("LIBGL_ALWAYS_SOFTWARE=1", text)
            with mock.patch(
                "kyth_shared.wayland_compose.needs_software_compose", return_value=False
            ):
                self.assertTrue(write_greeter_compose_env(path))
            self.assertEqual(path.read_text(encoding="utf-8"), "")

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

    def test_x11_session_values(self) -> None:
        self.assertTrue(session_is_plasma_x11("plasmax11.desktop"))
        self.assertTrue(session_is_plasma_x11("/usr/share/xsessions/plasmax11.desktop"))
        self.assertTrue(session_is_plasma_x11("/usr/share/xsessions/plasma.desktop"))
        self.assertFalse(session_is_plasma_x11("plasma.desktop"))
        self.assertFalse(session_is_plasma_x11("/usr/share/wayland-sessions/plasma.desktop"))
        self.assertFalse(session_is_plasma_x11(""))

    def test_migrate_greeter_last_session_and_dmrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.conf"
            state.write_text("[Last]\nUser=liveuser\nSession=/usr/share/xsessions/plasmax11.desktop\n")
            self.assertTrue(migrate_greeter_last_session(state))
            text = state.read_text(encoding="utf-8")
            self.assertIn(f"Session={PLASMA_WAYLAND_SESSION}", text)
            self.assertIn("User=liveuser", text)
            self.assertFalse(migrate_greeter_last_session(state))

            homes = Path(tmp) / "home"
            user = homes / "alice"
            user.mkdir(parents=True)
            (user / ".dmrc").write_text("[Desktop]\nSession=plasmax11\n")
            (homes / "skip").mkdir()
            self.assertEqual(migrate_home_dmrcs(homes), 1)
            self.assertEqual((user / ".dmrc").read_text(encoding="utf-8"), "[Desktop]\nSession=plasma.desktop\n")
            self.assertFalse(migrate_user_dmrc(user))

    def test_configure_session_rewrites_stale_x11_dropin(self) -> None:
        launcher = ROOT / "build_files" / "kyth-configure-session"
        with tempfile.TemporaryDirectory() as tmp:
            conf_dir = Path(tmp)
            stale = conf_dir / "11-kyth-session.conf"
            stale.write_text("[General]\nDisplayServer=x11\nDefaultSession=plasmax11.desktop\n")
            sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))
            spec_globals = runpy.run_path(str(launcher), run_name="not-main")
            self.assertEqual(spec_globals["configure_session"](conf_dir), 0)
            text = stale.read_text(encoding="utf-8")
            self.assertIn("DefaultSession=plasma.desktop", text)
            self.assertIn("Session=plasma.desktop", text)
            self.assertNotIn("plasmax11", text)

    def test_configure_host_session_rewrites_last_session(self) -> None:
        launcher = ROOT / "build_files" / "kyth-configure-session"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf_dir = root / "plasmalogin"
            conf_dir.mkdir()
            state = root / "state.conf"
            state.write_text("[Last]\nSession=/usr/share/xsessions/plasmax11.desktop\n")
            homes = root / "home"
            user = homes / "bob"
            user.mkdir(parents=True)
            (user / ".dmrc").write_text("[Desktop]\nSession=plasmax11.desktop\n")
            env_file = root / "kyth-greeter.env"
            spec_globals = runpy.run_path(str(launcher), run_name="not-main")
            self.assertEqual(
                spec_globals["configure_host_session"](
                    conf_dir, state_file=state, homes=homes, env_file=env_file
                ),
                0,
            )
            self.assertIn("DefaultSession=plasma.desktop", (conf_dir / "11-kyth-session.conf").read_text())
            self.assertIn(f"Session={PLASMA_WAYLAND_SESSION}", state.read_text())
            self.assertIn("Session=plasma.desktop", (user / ".dmrc").read_text())
            self.assertTrue(env_file.is_file())

    def test_configure_session_keeps_wayland_for_nomodeset(self) -> None:
        launcher = ROOT / "build_files" / "kyth-configure-session"
        with tempfile.TemporaryDirectory() as tmp:
            conf_dir = Path(tmp)
            spec_globals = runpy.run_path(str(launcher), run_name="not-main")
            self.assertEqual(
                spec_globals["configure_session"](conf_dir, cmdline="quiet nomodeset"),
                0,
            )
            text = (conf_dir / "11-kyth-session.conf").read_text(encoding="utf-8")
            self.assertIn("DefaultSession=plasma.desktop", text)
            self.assertNotIn("plasmax11", text)


class WaylandBrandingContractTests(unittest.TestCase):
    def test_plm_image_default_is_wayland(self) -> None:
        fragment = (
            ROOT / "build_files" / "scripts" / "branding" / "13-plasmalogin-session-background.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("DefaultSession=plasma.desktop", fragment)
        self.assertIn("Session=plasma.desktop", fragment)
        self.assertIn("kyth/contents/images/1920x1080.svg", fragment)
        self.assertIn("write_config /etc/plasmalogin.conf <<", fragment)
        self.assertIn("/var/lib/plasmalogin/wallpapers/kyth.svg", fragment)
        self.assertIn("tmpfiles.d/kyth-plasmalogin-wallpaper.conf", fragment)
        self.assertIn("WallpaperPluginId=org.kde.image", fragment)
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
        self.assertIn("kyth-greeter-compositor", fragment)
        self.assertIn("ExecStartPre=/usr/bin/kyth-configure-session", fragment)
        self.assertIn("plasmalogin.service.d", fragment)
        self.assertIn("plasma-login-kwin_wayland.service.d", fragment)
        compositor = (ROOT / "build_files" / "kyth-greeter-compositor").read_text(encoding="utf-8")
        self.assertIn("needs_software_compose", compositor)
        self.assertIn("kwin_wayland", compositor)
        self.assertIn("GREETER_NO_DRM_HINT", compositor)

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
        self.assertIn("plasma-login-manager", baseline)
        self.assertNotIn("sddm", baseline)
        self.assertIn("plasma-login-manager", cleanup)
        self.assertIn("/usr/bin/plasmalogin", cleanup)
        self.assertIn("sddm", cleanup)
        for package in (
            "plasma-workspace-x11",
            "xorg-x11-server-Xorg",
            "xorg-x11-drv-libinput",
        ):
            self.assertNotIn(package, baseline)
            self.assertIn(package, cleanup)
        leftover_start = cleanup.index("forbidden_x11_session_rpms=(")
        leftover_end = cleanup.index("leftover_x11_session_rpms=(")
        leftover_list = cleanup[leftover_start:leftover_end]
        self.assertNotIn("xorg-x11-xinit", leftover_list)
        self.assertIn("xorg-x11-xinit must remain", cleanup)
        self.assertNotIn("xorg-x11-xinit", baseline)
        self.assertNotIn("xorg-x11-drv-amdgpu", amd)
        self.assertNotIn("xorg-x11-drv-ati", amd)
        self.assertIn("xorg-x11-drv-amdgpu", cleanup)
        self.assertIn("kwin-x11", cleanup)
        self.assertIn("leftover_x11_session_rpms", cleanup)
        self.assertIn("xorg-x11-server-Xwayland", cleanup)
        self.assertIn("exit 1", cleanup)
        nvidia = (ROOT / "build_files" / "scripts" / "packages" / "16-gpu-nvidia.sh").read_text(encoding="utf-8")
        self.assertIn("xorg-x11-drv-nvidia", nvidia)
        self.assertNotIn("xorg-x11-drv-nvidia", cleanup)

    def test_live_iso_autologin_follows_wayland_default(self) -> None:
        body = (ROOT / "installer" / "build.sh").read_text(encoding="utf-8")
        self.assertIn("User=liveuser", body)
        self.assertNotIn("Session=plasmax11.desktop", body)
        self.assertNotIn("Session=plasma.desktop", body)
        self.assertIn("KWIN_COMPOSE=Q", body)


class GreeterCompositorEntryTests(unittest.TestCase):
    def test_compositor_execs_kwin_with_software_env(self) -> None:
        launcher = ROOT / "build_files" / "kyth-greeter-compositor"
        exec_calls: list[tuple] = []

        def fake_execvp(binary: str, argv: list[str]) -> None:
            exec_calls.append((binary, argv))
            raise SystemExit(0)

        with (
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(sys, "argv", ["kyth-greeter-compositor", "--no-lockscreen"]),
            mock.patch("kyth_shared.wayland_compose.needs_software_compose", return_value=True),
            mock.patch("kyth_shared.wayland_compose.has_drm_card", return_value=True),
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
            self.assertIn("--no-lockscreen", exec_calls[0][1])
            self.assertNotIn("--drm", exec_calls[0][1])


if __name__ == "__main__":
    unittest.main()
