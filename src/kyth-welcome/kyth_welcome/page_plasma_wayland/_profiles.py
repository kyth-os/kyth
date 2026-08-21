# __KYTH_GENERATED_IMPORTS__
from ..services.plasma import run_shell_script


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
    "windows": {
        "title": "Windows 11 Comfort",
        "summary": "Feels like Windows: centered taskbar, double-click to open, strong snap zones, Win+arrow halves, Win+E/D/L.",
        "zones": "Halves and quarters with 8px gaps — drag to snap to 2×2 or 3-column grid, like Windows 11 Snap Layouts.",
        "snap": 8,
        "placement": "Smart",
        "animation": 1,
        "tiling_padding": 6,
    },
}


class _ProfilesMixin:
    def _apply_desktop_profile(self, profile_key: str, *, result_attr: str = "_profile_result") -> None:
        profile = DESKTOP_PROFILES[profile_key]
        panel = getattr(self, result_attr, None) or getattr(self, "_profile_result", None)
        if panel is None:
            return
        panel.show()
        panel.set_running(f"Applying {profile['title']} mode", "Writing Plasma and KWin defaults...")
        script = self._desktop_profile_command(profile_key, profile)
        code, out, err = run_shell_script(script, timeout=20)
        details = (out or "") + (err or "")
        if code == 0:
            panel.set_result("ok", f"Applied {profile['title']} mode", details.strip() or "KWin settings refreshed.")
        else:
            panel.set_result("err", f"Failed to apply {profile['title']} mode", details.strip() or f"exit {code}")

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
            "windows": """
kwriteconfig6 --file kdeglobals --group KDE --key SingleClick false
kwriteconfig6 --file dolphinrc --group General --key ShowPreview true
kwriteconfig6 --file kdeglobals --group General --key XftHintStyle hintslight
# Familiar Meta shortcuts (best-effort; Plasma may remap some on next login)
kwriteconfig6 --file kglobalshortcutsrc --group services --key 'org.kde.dolphin.desktop' 'Meta+E,none,Dolphin'
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key 'Show Desktop' 'Meta+D,none,Show Desktop'
kwriteconfig6 --file kglobalshortcutsrc --group ksmserver --key 'Lock Session' 'Meta+L,Meta+L,Lock Session'
# Windows 11 Snap parity: strong snap + centered taskbar hint when supported
kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc --group Containments --key alignment 1
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
