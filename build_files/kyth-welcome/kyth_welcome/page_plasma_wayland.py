import os
import shutil
import subprocess  # nosec B404 # nosemgrep

# __KYTH_GENERATED_IMPORTS__
from .core_base import _release_worker_when_finished
from .services.gaming import DataWorker
from .services.hardware import HardwareProbe
from .qt import (  # noqa: E501
    QFrame, QHBoxLayout, QLabel, QTimer, QVBoxLayout, Qt,
)
from .widgets import (  # noqa: E501
    ActionRow, CommandResultPanel, HardwareCard, Page, _make_card,
)

QDBUS_CANDIDATES = ("qdbus6", "qdbus-qt6", "qdbus")
KDE_PORTAL_UNITS = ("plasma-xdg-desktop-portal-kde.service", "xdg-desktop-portal-kde.service")


def _run_text(cmd: list[str], timeout: int = 5) -> tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)  # nosec B603 # nosemgrep
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


def _user_unit_active(unit: str) -> bool:
    code, out, _ = _run_text(["systemctl", "--user", "is-active", unit])
    return code == 0 and out == "active"


def _first_active_user_unit(units: tuple[str, ...]) -> str:
    for unit in units:
        if _user_unit_active(unit):
            return unit
    return ""


def _first_available_binary(names: tuple[str, ...]) -> str:
    for name in names:
        if shutil.which(name):
            return name
    return ""


def _user_bus_name_available(name: str) -> bool:
    code, out, _ = _run_text(["busctl", "--user", "--no-pager", "list"])
    if code != 0:
        return False
    return any(line.split(maxsplit=1)[0] == name for line in out.splitlines() if line.strip())


def _session_kind() -> str:
    return os.environ.get("XDG_SESSION_TYPE", "").strip().lower()


def _desktop_name() -> str:
    return (
        os.environ.get("XDG_CURRENT_DESKTOP", "")
        or os.environ.get("DESKTOP_SESSION", "")
        or os.environ.get("KDE_SESSION_VERSION", "")
    ).strip()


def _kread(file_name: str, group: str, key: str) -> str:
    code, out, _ = _run_text([
        "kreadconfig6", "--file", file_name, "--group", group, "--key", key,
    ])
    return out if code == 0 else ""


def _collect_wayland_probes() -> list[HardwareProbe]:
    probes: list[HardwareProbe] = []

    session = _session_kind()
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

    desktop = _desktop_name()
    is_plasma = "kde" in desktop.lower() or "plasma" in desktop.lower()
    probes.append(HardwareProbe(
        "Plasma desktop",
        "ok" if is_plasma else "dim",
        "Plasma session detected" if is_plasma else "Plasma session not detected from environment",
        f"XDG_CURRENT_DESKTOP={desktop or 'unknown'}",
    ))

    pipewire = _user_unit_active("pipewire.service") or _user_unit_active("pipewire.socket")
    wireplumber = _user_unit_active("wireplumber.service")
    probes.append(HardwareProbe(
        "PipeWire",
        "ok" if pipewire and wireplumber else "warn",
        "Audio and capture session services are active" if pipewire and wireplumber else "PipeWire or WirePlumber is not active",
        f"pipewire={'active' if pipewire else 'inactive'}, wireplumber={'active' if wireplumber else 'inactive'}",
    ))

    portal = _user_unit_active("xdg-desktop-portal.service") or _user_bus_name_available("org.freedesktop.portal.Desktop")
    portal_kde_unit = _first_active_user_unit(KDE_PORTAL_UNITS)
    portal_kde = bool(portal_kde_unit) or _user_bus_name_available("org.freedesktop.impl.portal.desktop.kde")
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
    qdbus_binary = _first_available_binary(QDBUS_CANDIDATES)
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

    color_scheme = _kread("kdeglobals", "General", "ColorScheme")
    ui_font = _kread("kdeglobals", "General", "font")
    fixed_font = _kread("kdeglobals", "General", "fixed")
    icon_theme = _kread("kdeglobals", "Icons", "Theme")
    plasma_theme = _kread("plasmarc", "Theme", "name")
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

    single_click = _kread("kdeglobals", "KDE", "SingleClick").lower()
    clip_items = _kread("klipperrc", "General", "MaxClipItems")
    probes.append(HardwareProbe(
        "Desktop comfort defaults",
        "ok" if single_click == "false" and clip_items == "25" else "dim",
        "Comfortable double-click and clipboard history defaults are configured"
        if single_click == "false" and clip_items == "25" else "Comfort defaults are not fully applied; restore them below when wanted",
        f"Single-click open: {single_click or 'unset'}\nClipboard history size: {clip_items or 'unset'}",
    ))

    layout_marker = _kread("plasma-org.kde.plasma.desktop-appletsrc", "KythOS", "KythComfortLayout")
    legacy_layout_marker = _kread("plasma-org.kde.plasma.desktop-appletsrc", "KythOS", "WindowsFamiliarLayout")
    layout_ok = layout_marker in ("kyth-comfort-v2", "kyth-comfort-v3") or legacy_layout_marker == "windows-familiar-v1"
    probes.append(HardwareProbe(
        "KythOS default layout",
        "ok" if layout_ok else "dim",
        "KythOS bottom taskbar and pinned launcher layout are active"
        if layout_ok else "Standard KythOS layout is not marked active; restore it below when wanted",
        f"KythOS layout marker: {layout_marker or 'unset'}\nLegacy layout marker: {legacy_layout_marker or 'unset'}",
    ))
    return probes



DESKTOP_PROFILES = {
    "gaming": {
        "title": "Gaming",
        "summary": "Fullscreen-first, quiet notifications, launcher/chat side space.",
        "zones": "Primary game focus; secondary display keeps chat, browser, and monitoring visible.",
        "snap": 12,
        "placement": "Centered",
        "animation": 1,
        "tiling_padding": 6,
    },
    "dev": {
        "title": "Development",
        "summary": "Keyboard-driven thirds for editor, terminal, and docs.",
        "zones": "25% terminal | 50% editor | 25% docs on wide screens; 70/30 on laptops.",
        "snap": 10,
        "placement": "Smart",
        "animation": 1,
        "tiling_padding": 4,
    },
    "creator": {
        "title": "Creator",
        "summary": "Large canvas with predictable asset/tool side panes.",
        "zones": "70% canvas/editor | 30% assets/tools, with capture-friendly notifications.",
        "snap": 10,
        "placement": "Centered",
        "animation": 2,
        "tiling_padding": 8,
    },
    "laptop": {
        "title": "Laptop",
        "summary": "Compact panel, gesture-first flow, simple two-column snapping.",
        "zones": "Full-screen focus or 60% main | 40% reference; avoids cramped thirds.",
        "snap": 14,
        "placement": "Smart",
        "animation": 2,
        "tiling_padding": 5,
    },
    "ultrawide": {
        "title": "Ultrawide",
        "summary": "Prevents huge empty windows and makes thirds feel native.",
        "zones": "25% side | 50% main | 25% side with centered dialogs.",
        "snap": 8,
        "placement": "Centered",
        "animation": 1,
        "tiling_padding": 8,
    },
    "balanced": {
        "title": "Balanced",
        "summary": "Clean default for browsing, files, settings, and everyday multitasking.",
        "zones": "Halves and quarters with normal notifications and moderate density.",
        "snap": 12,
        "placement": "Smart",
        "animation": 2,
        "tiling_padding": 6,
    },
}

class PlasmaWaylandPage(Page):
    def __init__(self):
        super().__init__()
        self._initial_refresh_started = False
        self._worker = None
        self._page_header(
            "System",
            "Plasma & Wayland",
            "Session readiness, screen sharing, display tuning, shortcuts, and Plasma repair tools.",
        )

        overview_card, overview_layout = _make_card("card-accent-ok")
        title = QLabel("Wayland readiness")
        title.setObjectName("card-title")
        overview_layout.addWidget(title)
        body = QLabel(
            "KythOS keeps a stable Plasma desktop today while preparing a stronger Wayland-first path. "
            "These checks focus on the pieces users notice first: portals, PipeWire capture, display "
            "behavior, visual polish, and session repair."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        overview_layout.addWidget(body)

        self._refresh_actions = ActionRow("Ready to check this Plasma session.", "idle")
        self._refresh_btn = self._refresh_actions.add_button("Refresh Readiness", self.refresh, primary=True)
        self._refresh_actions.finish()
        overview_layout.addWidget(self._refresh_actions)

        self._probe_rows = QVBoxLayout()
        self._probe_rows.setSpacing(8)
        overview_layout.addLayout(self._probe_rows)
        self._add(overview_card)

        self._add(self._make_settings_card())
        self._add(self._make_polish_card())
        self._add(self._make_repair_card())
        self._add(self._make_presets_card())
        self._add(self._make_desktop_modes_card())
        self._add(self._make_snap_grid_card())
        self._add(self._make_wayland_readiness_card())

        self._stretch()

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        QTimer.singleShot(0, self.refresh)

    def _make_settings_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Plasma settings shortcuts")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Jump directly to the places that matter for a polished Wayland desktop: "
            "display layout, global shortcuts, window rules, screen edges, and notifications."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        actions = ActionRow("", "idle")
        actions.status.hide()
        actions.add_button("Display", lambda _=False: self._open_kcm("Display Settings", "kcm_kscreen"))
        actions.add_button("Shortcuts", lambda _=False: self._open_kcm("Shortcuts", "kcm_keys"))
        actions.add_button("Window Rules", lambda _=False: self._open_kcm("Window Rules", "kcm_kwinrules"))
        actions.add_button("Screen Edges", lambda _=False: self._open_kcm("Screen Edges", "kcm_kwinscreenedges"))
        actions.add_button("Notifications", lambda _=False: self._open_kcm("Notifications", "kcm_notifications"))
        actions.finish()
        layout.addWidget(actions)
        return card

    def _make_polish_card(self) -> QFrame:
        card, layout = _make_card("card-accent-ok")
        title = QLabel("KythOS Plasma polish")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Restore the standard KythOS desktop preset in one pass."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        for name, summary in (
            ("Desktop", "bottom taskbar, KythOS launcher, pinned apps, tray, and clock"),
            ("Comfort", "Meta shortcuts, clipboard history, Screenshots folder, and Dolphin defaults"),
            ("Look", "KythDark colors, wallpaper, panel theme, fonts, icons, and titlebar buttons"),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(name)
            label.setObjectName("card-summary")
            label.setMinimumWidth(90)
            row.addWidget(label)
            copy = QLabel(summary)
            copy.setObjectName("card-copy")
            copy.setWordWrap(True)
            row.addWidget(copy, 1)
            layout.addLayout(row)

        actions = ActionRow("", "idle")
        actions.status.hide()
        actions.add_button("Restore KythOS Layout", self._apply_plasma_polish, primary=True)
        actions.add_button("Open Desktop Theme", lambda _=False: self._open_kcm("Desktop Theme", "kcm_desktoptheme"))
        actions.add_button("Open Colors", lambda _=False: self._open_kcm("Colors", "kcm_colors"))
        actions.finish()
        layout.addWidget(actions)

        self._polish_result = CommandResultPanel()
        self._polish_result.hide()
        layout.addWidget(self._polish_result)
        return card

    def _make_repair_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Screen sharing and shell repair")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Wayland screen sharing depends on PipeWire and desktop portals. Restart the stack "
            "when captures are blank, or test the portal before opening an issue."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        actions = ActionRow("", "idle")
        actions.status.hide()
        actions.add_button("Restart Capture Stack", self._restart_capture_stack, primary=True)
        actions.add_button("Test Desktop Portal", self._test_desktop_portal)
        actions.add_button("Restart Plasma Shell", self._restart_plasma_shell)
        actions.finish()
        layout.addWidget(actions)

        self._repair_result = CommandResultPanel()
        self._repair_result.hide()
        layout.addWidget(self._repair_result)
        return card

    def _make_presets_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("KythOS preset direction")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Next layer: console, creator, developer, laptop, and docked Plasma presets. "
            "This page is the control surface where those profile toggles can land."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        for name, summary in (
            ("Console Mode", "larger panel targets, Steam-first workflow, game session shortcuts"),
            ("Creator Mode", "capture portals, OBS readiness, color/display settings surfaced"),
            ("Developer Mode", "terminal and file workflows, virtual desktops, clipboard history"),
            ("Laptop Mode", "battery-aware sleep, touchpad gestures, dock/undock behavior"),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(name)
            label.setObjectName("card-summary")
            label.setMinimumWidth(120)
            row.addWidget(label)
            copy = QLabel(summary)
            copy.setObjectName("card-copy")
            copy.setWordWrap(True)
            row.addWidget(copy, 1)
            layout.addLayout(row)
        return card


    def _make_desktop_modes_card(self) -> QFrame:
        card, body = _make_card("card-accent-ok")
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)
        title = QLabel("Kyth Desktop Modes")
        title.setObjectName("card-title")
        copy = QLabel("Apply opinionated Plasma and KWin defaults for the way you use the machine. Each mode tunes snapping, placement, animation speed, tiling gaps, and stores a Kyth layout marker for future automation.")
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        body.addWidget(title)
        body.addWidget(copy)
        for key, profile in DESKTOP_PROFILES.items():
            row = ActionRow(f"{profile['title']}: {profile['summary']}")
            row.add_button("Apply", lambda _checked=False, profile_key=key: self._apply_desktop_profile(profile_key))
            detail = QLabel(profile["zones"])
            detail.setObjectName("card-copy")
            detail.setWordWrap(True)
            body.addWidget(row)
            body.addWidget(detail)
        self._profile_result = CommandResultPanel()
        body.addWidget(self._profile_result)
        return card

    def _make_snap_grid_card(self) -> QFrame:
        card, body = _make_card()
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(10)
        title = QLabel("Snap, Grid, and Flow Defaults")
        title.setObjectName("card-title")
        copy = QLabel("Kyth defaults favor fast halves, quarters, and thirds, visible snap previews, centered transient windows, and compact gaps. Use Plasma's tiling editor for exact per-monitor layouts, then save the mode that matches your workflow.")
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        body.addWidget(title)
        body.addWidget(copy)
        shortcuts = QLabel("Super+Arrow: halves/maximize • Super+Alt+Arrow: thirds/rows target • Super+Ctrl+Arrow: move between desktops • Super+Alt+L: layout selector target")
        shortcuts.setObjectName("card-copy")
        shortcuts.setWordWrap(True)
        body.addWidget(shortcuts)
        row = ActionRow("Open Plasma tools for detailed tuning")
        row.add_button("Edit Tiles", lambda: self._open_kcm("Desktop Effects", "kcm_kwin_effects"))
        row.add_button("Shortcuts", lambda: self._open_kcm("Shortcuts", "kcm_keys"))
        row.add_button("Window Rules", lambda: self._open_kcm("Window Rules", "kcm_kwinrules"))
        body.addWidget(row)
        return card

    def _make_wayland_readiness_card(self) -> QFrame:
        card, body = _make_card("card-accent-ok")
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(10)
        title = QLabel("Wayland Readiness")
        title.setObjectName("card-title")
        copy = QLabel("A quick signal check for the modern desktop path: session type, GPU stack, portals, screen sharing, VRR, and HDR readiness.")
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        body.addWidget(title)
        body.addWidget(copy)
        rows = [
            ("Session", self._session_status()),
            ("GPU", self._gpu_status()),
            ("Portals", self._portal_status()),
            ("Screen sharing", self._screen_share_status()),
            ("VRR", self._kscreen_status("vrr")),
            ("HDR", self._kscreen_status("hdr")),
        ]
        for name, value in rows:
            line = QLabel(f"<b>{name}</b><br><span style='color:#95a6b4'>{value}</span>")
            line.setTextFormat(Qt.TextFormat.RichText)
            line.setStyleSheet("QLabel { background:#101820; border:1px solid #2d3a48; border-radius:8px; padding:9px 11px; color:#eef5f7; }")
            body.addWidget(line)
        return card

    def _apply_desktop_profile(self, profile_key: str) -> None:
        profile = DESKTOP_PROFILES[profile_key]
        self._profile_result.set_running(f"Applying {profile['title']} mode", "Writing Plasma and KWin defaults...")
        script = self._desktop_profile_command(profile_key, profile)
        try:
            result = subprocess.run(["bash", "-lc", script], capture_output=True, text=True, timeout=20)  # nosec B603 # nosemgrep
        except Exception as exc:
            self._profile_result.set_result("error", f"Could not apply {profile['title']} mode", str(exc))
            return
        details = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0:
            self._profile_result.set_result("ok", f"Applied {profile['title']} mode", details.strip() or "KWin settings refreshed.")
        else:
            self._profile_result.set_result("error", f"Failed to apply {profile['title']} mode", details.strip())

    def _desktop_profile_command(self, profile_key: str, profile: dict[str, object]) -> str:
        snap = int(profile["snap"])
        padding = int(profile["tiling_padding"])
        animation = int(profile["animation"])
        placement = str(profile["placement"])
        mode_notes = {
            "gaming": """
kwriteconfig6 --file kwinrc --group KythOS --key GamingMode true
kwriteconfig6 --file kwinrc --group KythOS --key FullscreenNotifications quiet
kwriteconfig6 --file kwinrc --group Windows --key FocusPolicy ClickToFocus
""",
            "dev": """
kwriteconfig6 --file kwinrc --group KythOS --key DeveloperMode true
kwriteconfig6 --file kwinrc --group KythOS --key PreferredColumns 3
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key 'Window One Desktop to the Left' 'Meta+Ctrl+Left,Meta+Ctrl+Left,Window One Desktop to the Left'
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key 'Window One Desktop to the Right' 'Meta+Ctrl+Right,Meta+Ctrl+Right,Window One Desktop to the Right'
""",
            "creator": """
kwriteconfig6 --file kwinrc --group KythOS --key CreatorMode true
kwriteconfig6 --file kwinrc --group KythOS --key CaptureNotifications quiet
kwriteconfig6 --file kwinrc --group Windows --key Placement Centered
""",
            "laptop": """
kwriteconfig6 --file kwinrc --group KythOS --key LaptopMode true
kwriteconfig6 --file kwinrc --group KythOS --key PreferredColumns 2
""",
            "ultrawide": """
kwriteconfig6 --file kwinrc --group KythOS --key UltrawideMode true
kwriteconfig6 --file kwinrc --group KythOS --key PreferredColumns 3
kwriteconfig6 --file kwinrc --group KythOS --key CenteredDialogs true
""",
        }.get(profile_key, "")
        return f"""
set -e
kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc --group KythOS --key DesktopMode {profile_key}
kwriteconfig6 --file kwinrc --group Windows --key Placement {placement}
kwriteconfig6 --file kwinrc --group Windows --key BorderSnapZone {snap}
kwriteconfig6 --file kwinrc --group Windows --key WindowSnapZone {snap}
kwriteconfig6 --file kwinrc --group Windows --key CenterSnapZone 0
kwriteconfig6 --file kwinrc --group Tiling --key Padding {padding}
kwriteconfig6 --file kwinrc --group Compositing --key AnimationSpeed {animation}
kwriteconfig6 --file kwinrc --group Plugins --key overviewEnabled true
kwriteconfig6 --file kwinrc --group Plugins --key presentwindowsEnabled true
{mode_notes}
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key 'Window Quick Tile Left' 'Meta+Left,Meta+Left,Quick Tile Window to the Left'
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key 'Window Quick Tile Right' 'Meta+Right,Meta+Right,Quick Tile Window to the Right'
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key 'Window Quick Tile Top' 'Meta+Up,Meta+Up,Quick Tile Window to the Top'
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key 'Window Quick Tile Bottom' 'Meta+Down,Meta+Down,Quick Tile Window to the Bottom'
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key 'Overview' 'Meta,Meta,Toggle Overview'
qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || qdbus-qt6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
"""

    def _session_status(self) -> str:
        session = os.environ.get("XDG_SESSION_TYPE") or "unknown"
        display = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY") or "no display variable"
        return f"{session} session, {display}"

    def _gpu_status(self) -> str:
        try:
            out = subprocess.run(["bash", "-lc", "lspci | grep -Ei 'vga|3d|display' | head -2"], capture_output=True, text=True, timeout=4).stdout.strip()  # nosec B603 # nosemgrep
        except Exception:
            out = ""
        return out or "GPU probe unavailable"

    def _portal_status(self) -> str:
        checks = [
            ("portal", "systemctl --user is-active xdg-desktop-portal.service"),
            ("kde", "systemctl --user is-active xdg-desktop-portal-kde.service"),
            ("pipewire", "systemctl --user is-active pipewire.service"),
        ]
        states = []
        for name, cmd in checks:
            result = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=3)  # nosec B603 # nosemgrep
            states.append(f"{name}:{(result.stdout or 'inactive').strip()}")
        return ", ".join(states)

    def _screen_share_status(self) -> str:
        return "Ready when PipeWire and xdg-desktop-portal-kde are active"

    def _kscreen_status(self, feature: str) -> str:
        try:
            out = subprocess.run(["bash", "-lc", "kscreen-doctor -o 2>/dev/null | head -40"], capture_output=True, text=True, timeout=4).stdout.lower()  # nosec B603 # nosemgrep
        except Exception:
            out = ""
        if not out:
            return "Install/run kscreen-doctor to probe display capabilities"
        if feature in out:
            return "Capability appears in display probe"
        return "Not advertised by current display probe"

    @staticmethod
    def _plasma_polish_command() -> list[str]:
        script = r"""
set -euo pipefail
if [ -x /usr/bin/kyth-user-polish ]; then
  /usr/bin/kyth-user-polish --force
  exit 0
fi
command -v kwriteconfig6 >/dev/null
mkdir -p "${HOME}/Screenshots"

kwriteconfig6 --file kdeglobals --group General --key ColorScheme KythDark
kwriteconfig6 --file kdeglobals --group General --key font 'Inter,10,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group General --key fixed 'Cascadia Code,10,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group General --key smallestReadableFont 'Inter,8,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group General --key toolBarFont 'Inter,9,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group General --key menuFont 'Inter,10,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group Icons --key Theme Papirus-Dark
kwriteconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage org.kde.breezedark.desktop
kwriteconfig6 --file kdeglobals --group KDE --key SingleClick --type bool false
kwriteconfig6 --file plasmarc --group Theme --key name kyth-dark
kwriteconfig6 --file kickoffrc --group Favorites --key FavoriteURLs 'applications:kyth-welcome.desktop,applications:kyth-app-store.desktop,applications:steam.desktop,applications:com.brave.Browser.desktop,applications:com.discordapp.Discord.desktop,applications:org.kde.konsole.desktop'
kwriteconfig6 --file kickoffrc --group General --key highlightNewlyInstalledApps --type bool false

kwriteconfig6 --file klipperrc --group General --key KeepClipboardContents --type bool true
kwriteconfig6 --file klipperrc --group General --key MaxClipItems 25
kwriteconfig6 --file kglobalshortcutsrc --group org.kde.klipper.desktop --key show_clipboard_history 'Meta+V,Ctrl+Alt+V,Show Clipboard History'
kwriteconfig6 --file kglobalshortcutsrc --group services --group org.kde.dolphin.desktop --key _launch 'Meta+E'
kwriteconfig6 --file kglobalshortcutsrc --group org.kde.spectacle.desktop --key RectangularRegionScreenShot 'Meta+Shift+S,Meta+Shift+S,Capture Rectangular Region'
kwriteconfig6 --file spectaclerc --group General --key defaultSaveLocation "file://${HOME}/Screenshots"
kwriteconfig6 --file spectaclerc --group General --key lastSaveAsLocation "file://${HOME}/Screenshots"
kwriteconfig6 --file spectaclerc --group General --key useReleaseToCapture --type bool true
kwriteconfig6 --file spectaclerc --group ImageSave --key translatedScreenshotsFolder "${HOME}/Screenshots"

kwriteconfig6 --file kwinrc --group TabBox --key LayoutName thumbnail_grid
kwriteconfig6 --file kwinrc --group TabBox --key ShowDesktop --type bool false
kwriteconfig6 --file kwinrc --group TabBoxAlternative --key LayoutName thumbnail_grid
kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnLeft ''
kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnRight IAX
kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key library org.kde.breeze
kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme Breeze
kwriteconfig6 --file kwinrc --group Plugins --key desktopchangeosdEnabled --type bool false
kwriteconfig6 --file kwinrc --group Compositing --key LatencyPolicy extreme
kwriteconfig6 --file kwinrc --group Compositing --key AllowTearing --type bool false

kwriteconfig6 --file plasma-discoverrc --group UpdatesNotifier --key UseNotifications --type bool false
kwriteconfig6 --file dolphinrc --group General --key RememberOpenedTabs --type bool true
kwriteconfig6 --file dolphinrc --group General --key ShowFullPath --type bool true
kwriteconfig6 --file dolphinrc --group General --key UseTabForSplitViewSwitch --type bool true
kwriteconfig6 --file dolphinrc --group General --key ShowSpaceInfo --type bool true
kwriteconfig6 --file dolphinrc --group DetailsMode --key PreviewSize 32
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock --type bool true
kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockGracePeriod 5
kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockOnResume --type bool true
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Timeout 15
kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.image --group General --key Image /usr/share/wallpapers/kyth/contents/images/1920x1080.svg

if [ -r /usr/share/wallpapers/kyth/contents/images/1920x1080.svg ]; then
  kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc \
    --group Containments --group 1 --group Wallpaper --group org.kde.image --group General \
    --key Image /usr/share/wallpapers/kyth/contents/images/1920x1080.svg
fi

qdbus_cmd=""
for candidate in qdbus6 qdbus-qt6 qdbus; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    qdbus_cmd="${candidate}"
    break
  fi
done
if [ -n "${qdbus_cmd}" ]; then
  "${qdbus_cmd}" org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
fi
"""
        return ["bash", "-lc", script]

    def _apply_plasma_polish(self):
        cmd = self._plasma_polish_command()
        self._polish_result.set_running("Restoring the KythOS default layout...", self._command_details(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)  # nosec B603 # nosemgrep
        except Exception as exc:
            self._polish_result.set_result("err", f"Could not apply KythOS polish: {exc}", self._command_details(cmd, exc=exc))
            return
        if result.returncode == 0:
            self._polish_result.set_result(
                "ok",
                "KythOS default layout restored. Some panel, shell theme, or wallpaper changes may appear after restarting Plasma Shell or signing in again.",
                self._command_details(cmd, result),
            )
            self.refresh()
        else:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            self._polish_result.set_result("err", f"Could not apply KythOS polish: {detail}", self._command_details(cmd, result))

    def refresh(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._refresh_actions.status.set_state("running", "Checking Plasma and Wayland readiness...")
        self._clear_probe_rows()
        self._worker = DataWorker("plasma-wayland", _collect_wayland_probes)
        self._worker.result.connect(self._on_refresh_done)
        self._worker.failed.connect(self._on_refresh_failed)
        _release_worker_when_finished(self, "_worker", self._worker)
        self._worker.start()

    def _on_refresh_done(self, _key: str, probes: list[HardwareProbe]):
        self._refresh_btn.setEnabled(True)
        for probe in probes:
            self._probe_rows.addWidget(HardwareCard(probe))
        states = {probe.status for probe in probes}
        if "err" in states:
            self._refresh_actions.status.set_state("err", "Session checks found issues.")
        elif "warn" in states:
            self._refresh_actions.status.set_state("warn", "Some Wayland pieces may need attention.")
        else:
            self._refresh_actions.status.set_state("ok", "Plasma and Wayland checks look ready.")

    def _on_refresh_failed(self, _key: str, message: str):
        self._refresh_btn.setEnabled(True)
        self._refresh_actions.status.set_state("err", f"Could not check session: {message}")

    def _clear_probe_rows(self):
        while self._probe_rows.count():
            item = self._probe_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

    def _open_kcm(self, label: str, module: str):
        for cmd in (["kcmshell6", module], ["systemsettings", module], ["systemsettings"]):
            if not shutil.which(cmd[0]):
                continue
            try:
                subprocess.Popen(cmd)  # nosec B603 # nosemgrep
                return
            except OSError:
                continue
        self._repair_result.set_result("err", f"Could not open {label}.", f"Tried: kcmshell6 {module}, systemsettings {module}")

    @staticmethod
    def _command_details(cmd: list[str], result=None, exc: Exception | None = None) -> str:
        lines = ["Command:", "  " + " ".join(cmd)]
        if exc is not None:
            lines.extend(["", "Error:", str(exc)])
            return "\n".join(lines)
        if result is None:
            return "\n".join(lines)
        lines.extend(["", f"Exit code: {result.returncode}"])
        if result.stdout:
            lines.extend(["", "stdout:", result.stdout.strip()])
        if result.stderr:
            lines.extend(["", "stderr:", result.stderr.strip()])
        return "\n".join(lines)

    def _run_repair_command(self, label: str, success: str, cmd: list[str]):
        self._repair_result.set_running(label, self._command_details(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)  # nosec B603 # nosemgrep
        except Exception as exc:
            self._repair_result.set_result("err", f"{label} failed: {exc}", self._command_details(cmd, exc=exc))
            return
        if result.returncode == 0:
            self._repair_result.set_result("ok", success, self._command_details(cmd, result))
            self.refresh()
        else:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            self._repair_result.set_result("err", f"{label} failed: {detail}", self._command_details(cmd, result))

    def _restart_capture_stack(self):
        self._run_repair_command(
            "Restarting PipeWire and desktop portals",
            "Capture stack restarted. Try screen sharing again.",
            [
                "bash", "-lc",
                "systemctl --user restart pipewire wireplumber xdg-desktop-portal; "
                "if systemctl --user list-unit-files plasma-xdg-desktop-portal-kde.service --no-legend | grep -q '^plasma-xdg-desktop-portal-kde\\.service'; then "
                "systemctl --user restart plasma-xdg-desktop-portal-kde.service; "
                "else systemctl --user restart xdg-desktop-portal-kde.service; fi",
            ],
        )

    def _test_desktop_portal(self):
        self._run_repair_command(
            "Testing the desktop portal",
            "Desktop portal responded.",
            [
                "bash", "-lc",
                "busctl --user call org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop org.freedesktop.DBus.Peer Ping "
                "|| { qdbus_cmd=''; for candidate in qdbus6 qdbus-qt6 qdbus; do command -v \"$candidate\" >/dev/null 2>&1 && qdbus_cmd=\"$candidate\" && break; done; "
                "[ -n \"$qdbus_cmd\" ] && \"$qdbus_cmd\" org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop org.freedesktop.DBus.Peer.Ping; }",
            ],
        )

    def _restart_plasma_shell(self):
        self._run_repair_command(
            "Restarting Plasma Shell",
            "Plasma Shell restart requested.",
            ["bash", "-lc", "kquitapp6 plasmashell; kstart6 plasmashell"],
        )
