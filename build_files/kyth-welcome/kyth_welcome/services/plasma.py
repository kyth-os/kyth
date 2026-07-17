"""Plasma / Wayland session probes and kconfig helpers.

Pure stdlib — used by the Plasma & Wayland Hub page and CLI checks.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from .hardware.types import HardwareProbe

QDBUS_CANDIDATES = ("qdbus6", "qdbus-qt6", "qdbus")
KDE_PORTAL_UNITS = ("plasma-xdg-desktop-portal-kde.service", "xdg-desktop-portal-kde.service")


def run_text(cmd: list[str], timeout: int = 5) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


_run_text = run_text


def user_unit_active(unit: str) -> bool:
    code, out, _ = run_text(["systemctl", "--user", "is-active", unit])
    return code == 0 and out == "active"


_user_unit_active = user_unit_active


def first_active_user_unit(units: tuple[str, ...]) -> str:
    for unit in units:
        if user_unit_active(unit):
            return unit
    return ""


_first_active_user_unit = first_active_user_unit


def first_available_binary(names: tuple[str, ...]) -> str:
    for name in names:
        if shutil.which(name):
            return name
    return ""


_first_available_binary = first_available_binary


def user_bus_name_available(name: str) -> bool:
    code, out, _ = run_text(["busctl", "--user", "--no-pager", "list"])
    if code != 0:
        return False
    return any(line.split(maxsplit=1)[0] == name for line in out.splitlines() if line.strip())


_user_bus_name_available = user_bus_name_available


def session_kind() -> str:
    return os.environ.get("XDG_SESSION_TYPE", "").strip().lower()


_session_kind = session_kind


def desktop_name() -> str:
    return (
        os.environ.get("XDG_CURRENT_DESKTOP", "")
        or os.environ.get("DESKTOP_SESSION", "")
        or os.environ.get("KDE_SESSION_VERSION", "")
    ).strip()


_desktop_name = desktop_name


def kread(file_name: str, group: str, key: str) -> str:
    code, out, _ = run_text([
        "kreadconfig6", "--file", file_name, "--group", group, "--key", key,
    ])
    return out if code == 0 else ""


_kread = kread


def collect_wayland_probes() -> list[HardwareProbe]:
    probes: list[HardwareProbe] = []

    session = session_kind()
    session_status = "ok" if session == "wayland" else ("dim" if session == "x11" else "warn")
    session_summary = (
        "Wayland session active" if session == "wayland"
        else "X11 session active (VM detected — Wayland enabled automatically on bare metal)"
        if session == "x11"
        else "Session type could not be identified"
    )
    probes.append(HardwareProbe(
        "Session",
        session_status,
        session_summary,
        f"XDG_SESSION_TYPE={session or 'unknown'}",
    ))

    desktop = desktop_name()
    is_plasma = "kde" in desktop.lower() or "plasma" in desktop.lower()
    probes.append(HardwareProbe(
        "Plasma desktop",
        "ok" if is_plasma else "dim",
        "Plasma session detected" if is_plasma else "Plasma session not detected from environment",
        f"XDG_CURRENT_DESKTOP={desktop or 'unknown'}",
    ))

    pipewire = user_unit_active("pipewire.service") or user_unit_active("pipewire.socket")
    wireplumber = user_unit_active("wireplumber.service")
    probes.append(HardwareProbe(
        "PipeWire",
        "ok" if pipewire and wireplumber else "warn",
        "Audio and capture session services are active" if pipewire and wireplumber else "PipeWire or WirePlumber is not active",
        f"pipewire={'active' if pipewire else 'inactive'}, wireplumber={'active' if wireplumber else 'inactive'}",
    ))

    portal = user_unit_active("xdg-desktop-portal.service") or user_bus_name_available("org.freedesktop.portal.Desktop")
    portal_kde_unit = first_active_user_unit(KDE_PORTAL_UNITS)
    portal_kde = bool(portal_kde_unit) or user_bus_name_available("org.freedesktop.impl.portal.desktop.kde")
    portal_details = [
        f"Desktop portal: {'active' if portal else 'not running'}",
        f"KDE backend: {'active' if portal_kde else 'not running'}",
    ]
    if portal_kde_unit:
        portal_details.append(f"KDE backend unit: {portal_kde_unit}")
    probes.append(HardwareProbe(
        "Desktop portals",
        "ok" if portal and portal_kde else "warn",
        "KDE portal services are ready for file pickers, permissions, and screen sharing"
        if portal and portal_kde else "Restart the capture stack if screen sharing or file pickers misbehave",
        "\n".join(portal_details),
    ))

    has_busctl = bool(shutil.which("busctl"))
    qdbus_binary = first_available_binary(QDBUS_CANDIDATES)
    has_qdbus = bool(qdbus_binary)
    probes.append(HardwareProbe(
        "Portal diagnostics",
        "ok" if has_busctl or has_qdbus else "dim",
        "Portal diagnostic tools are available" if has_busctl or has_qdbus else "Portal diagnostic tools are not installed",
        f"busctl: {'available' if has_busctl else 'not found'}\nqdbus: {qdbus_binary or 'not found'}",
    ))

    vrr = os.environ.get("KWIN_DRM_ALLOW_VRR", "").strip()
    probes.append(HardwareProbe(
        "Display tuning",
        "dim" if not vrr else "ok",
        "Display Settings controls VRR, HDR, scale, refresh rate, and monitor layout",
        f"KWin VRR environment policy: {vrr or 'not set; using Plasma defaults'}",
    ))

    color_scheme = kread("kdeglobals", "General", "ColorScheme")
    ui_font = kread("kdeglobals", "General", "font")
    fixed_font = kread("kdeglobals", "General", "fixed")
    icon_theme = kread("kdeglobals", "Icons", "Theme")
    plasma_theme = kread("plasmarc", "Theme", "name")
    visual_ok = (
        color_scheme == "KythDark"
        and plasma_theme == "kyth-dark"
        and icon_theme == "Papirus-Dark"
        and ui_font.startswith("Inter,")
        and fixed_font.startswith("Cascadia Code,")
    )
    probes.append(HardwareProbe(
        "KythOS theme layer",
        "ok" if visual_ok else "dim",
        "KythOS color, icon, font, and panel theme are active"
        if visual_ok else "KythOS visual polish is not fully applied; restore it below when wanted",
        "\n".join((
            f"Color scheme: {color_scheme or 'unset'}",
            f"Plasma theme: {plasma_theme or 'unset'}",
            f"Icon theme: {icon_theme or 'unset'}",
            f"UI font: {ui_font or 'unset'}",
            f"Fixed font: {fixed_font or 'unset'}",
        )),
    ))

    single_click = kread("kdeglobals", "KDE", "SingleClick").lower()
    clip_items = kread("klipperrc", "General", "MaxClipItems")
    probes.append(HardwareProbe(
        "Desktop comfort defaults",
        "ok" if single_click == "false" and clip_items == "25" else "dim",
        "Comfortable double-click and clipboard history defaults are configured"
        if single_click == "false" and clip_items == "25" else "Comfort defaults are not fully applied; restore them below when wanted",
        f"Single-click open: {single_click or 'unset'}\nClipboard history size: {clip_items or 'unset'}",
    ))

    layout_marker = kread("plasma-org.kde.plasma.desktop-appletsrc", "KythOS", "KythComfortLayout")
    legacy_layout_marker = kread("plasma-org.kde.plasma.desktop-appletsrc", "KythOS", "WindowsFamiliarLayout")
    layout_ok = layout_marker in ("kyth-comfort-v2", "kyth-comfort-v3") or legacy_layout_marker == "windows-familiar-v1"
    probes.append(HardwareProbe(
        "KythOS default layout",
        "ok" if layout_ok else "dim",
        "KythOS bottom taskbar and pinned launcher layout are active"
        if layout_ok else "Standard KythOS layout is not marked active; restore it below when wanted",
        f"KythOS layout marker: {layout_marker or 'unset'}\nLegacy layout marker: {legacy_layout_marker or 'unset'}",
    ))
    return probes


_collect_wayland_probes = collect_wayland_probes


# Windows-familiar shortcuts (kglobalshortcutsrc). Value format is
# "active,default,description" for non-service entries.
WINDOWS_SHORTCUT_KEYS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("services", "org.kde.dolphin.desktop"), "_launch", "Meta+E"),
    (("org.kde.spectacle.desktop",), "RectangularRegionScreenShot",
     "Meta+Shift+S,Meta+Shift+S,Capture Rectangular Region"),
    (("klipper",), "show-on-mouse-pos",
     "Meta+V,Meta+V,Show Clipboard Items at Mouse Position"),
)


def kwriteconfig_command(file_name: str, groups: tuple[str, ...], key: str, value: str | None = None, *, delete: bool = False) -> list[str]:
    cmd = ["kwriteconfig6", "--file", file_name]
    for group in groups:
        cmd += ["--group", group]
    cmd += ["--key", key]
    if delete:
        cmd += ["--delete"]
    elif value is not None:
        cmd.append(value)
    return cmd


def apply_windows_shortcuts(*, delete: bool = False) -> tuple[bool, str]:
    """Write or remove Win+E / Win+Shift+S / Win+V shortcuts. Restarts kglobalaccel."""
    import shutil

    if not shutil.which("kwriteconfig6"):
        return False, "kwriteconfig6 not found — is this a KDE session?"
    ok = True
    for groups, key, value in WINDOWS_SHORTCUT_KEYS:
        code, _, _ = run_text(
            kwriteconfig_command(
                "kglobalshortcutsrc", groups, key, value, delete=delete,
            ),
            timeout=10,
        )
        ok = ok and code == 0
    run_text(
        ["systemctl", "--user", "restart", "plasma-kglobalaccel.service"],
        timeout=10,
    )
    return ok, ""


_apply_windows_shortcuts = apply_windows_shortcuts


def run_shell_script(script: str, *, timeout: int = 20) -> tuple[int, str, str]:
    """Run a multi-line shell script via bash -lc. Returns (code, stdout, stderr)."""
    return run_text(["bash", "-lc", script], timeout=timeout)


def gpu_lspci_summary() -> str:
    code, out, _ = run_shell_script("lspci | grep -Ei 'vga|3d|display' | head -2", timeout=4)
    return out if code == 0 else ""


def kscreen_doctor_output(max_lines: int = 40) -> str:
    code, out, _ = run_shell_script(
        f"kscreen-doctor -o 2>/dev/null | head -{int(max_lines)}",
        timeout=4,
    )
    return out if code == 0 else ""
