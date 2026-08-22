"""Wayland session defaults and software-compose rescue.

The installed and live images start SDDM and Plasma on Wayland only. When there
is no DRM render node, on live media, or with ``nomodeset``, KWin uses QPainter
+ llvmpipe. ``kyth.hwgl=1`` on the kernel command line forces hardware GL.
XWayland remains for games and Electron; Plasma X11 is not a session.
"""
from __future__ import annotations

import os
from pathlib import Path

SOFTWARE_COMPOSE_ENV: dict[str, str] = {
    "LIBGL_ALWAYS_SOFTWARE": "1",
    "GALLIUM_DRIVER": "llvmpipe",
    "MESA_LOADER_DRIVER_OVERRIDE": "llvmpipe",
    "QT_QUICK_BACKEND": "software",
    "KWIN_COMPOSE": "Q",
}

DEFAULT_KWIN_WAYLAND: tuple[str, ...] = (
    "kwin_wayland",
    "--drm",
    "--no-lockscreen",
    "--no-global-shortcuts",
    "--locale1",
)

SDDM_WAYLAND_CONF = "[General]\nDisplayServer=wayland\nDefaultSession=plasma.desktop\n"
LEGACY_QEMU_SAFE_NAME = "10-kyth-qemu-safe.sh"


def read_cmdline(path: Path | None = None) -> str:
    try:
        return (path or Path("/proc/cmdline")).read_text(encoding="utf-8")
    except OSError:
        return ""


def _cmdline_tokens(cmdline: str | None) -> list[str]:
    return (cmdline if cmdline is not None else read_cmdline()).split()


def hwgl_forced(cmdline: str | None = None) -> bool:
    return "kyth.hwgl=1" in _cmdline_tokens(cmdline)


def is_live_image(cmdline: str | None = None) -> bool:
    return any(token == "kyth.live" or token.startswith("kyth.live=") for token in _cmdline_tokens(cmdline))


def nomodeset_requested(cmdline: str | None = None) -> bool:
    """nomodeset disables GPU KMS — stay on Wayland with software compose."""
    return "nomodeset" in _cmdline_tokens(cmdline)


def sddm_session_conf(cmdline: str | None = None) -> str:
    """Always Plasma Wayland. ``cmdline`` is accepted for call-site compatibility."""
    del cmdline
    return SDDM_WAYLAND_CONF


def has_drm_render_node(dri: Path | None = None) -> bool:
    root = dri or Path("/dev/dri")
    try:
        return any(root.glob("renderD*"))
    except OSError:
        return False


def needs_software_compose(
    *,
    dri: Path | None = None,
    cmdline: str | None = None,
) -> bool:
    """Return True when the greeter or session should use software compose."""
    if hwgl_forced(cmdline):
        return False
    if nomodeset_requested(cmdline) or is_live_image(cmdline):
        return True
    return not has_drm_render_node(dri)


def apply_software_compose_env(env: dict[str, str] | None = None) -> dict[str, str]:
    target = os.environ if env is None else env
    target.update(SOFTWARE_COMPOSE_ENV)
    return target


def compositor_argv(extra: list[str] | None = None) -> list[str]:
    argv = list(DEFAULT_KWIN_WAYLAND)
    if extra:
        argv.extend(extra)
    return argv


def legacy_qemu_safe_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".config" / "plasma-workspace" / "env" / LEGACY_QEMU_SAFE_NAME


def remove_legacy_virt_software_gl(home: Path | None = None) -> bool:
    """Delete the old virt-only llvmpipe script copied into $HOME.

    That script forced software GL for every VM, including GPU passthrough.
    System-wide compose policy now lives in /etc/xdg/plasma-workspace/env.
    """
    path = legacy_qemu_safe_path(home)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if "systemd-detect-virt" not in text:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True
