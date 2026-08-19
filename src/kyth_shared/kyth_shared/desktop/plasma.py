"""Shared KDE Plasma & Desktop configuration helper module.

Ported from bash helpers (kyth-apply-desktop-layout, kyth-refresh-taskbar-pins, kyth-apply-role-preset).
"""
from __future__ import annotations
import logging
import subprocess

import shutil

from ..commands import run as run_command
from pathlib import Path

logger = logging.getLogger(__name__)

LAYOUT_VERSION = "kyth-comfort-v4"
CONFIG_FILE = "plasma-org.kde.plasma.desktop-appletsrc"

TRAY_ITEMS = [
    "org.kde.plasma.networkmanagement",
    "org.kde.plasma.volume",
    "org.kde.plasma.bluetooth",
    "org.kde.plasma.battery",
    "org.kde.plasma.notifications",
    "org.kde.plasma.clipboard",
    "org.kde.plasma.devicenotifier",
    "org.kde.plasma.printmanager",
    "org.kde.kdeconnect",
]

HIDDEN_TRAY_ITEMS = [
    "org.kde.plasma.keyboardindicator",
    "org.kde.plasma.mediacontroller",
]


def desktop_exists(desktop: str) -> bool:
    """Check if a desktop launcher exists in system or user paths."""
    if desktop.startswith("applications:"):
        desktop = desktop[len("applications:") :]
    paths = [
        Path("/usr/share/applications") / desktop,
        Path("/var/lib/flatpak/exports/share/applications") / desktop,
        Path.home() / ".local/share/applications" / desktop,
        Path.home() / ".local/share/flatpak/exports/share/applications" / desktop,
    ]
    return any(p.is_file() for p in paths)


def filter_available_launchers(launchers_config: list[list[str] | str]) -> list[str]:
    """Filter candidate launcher definitions down to the first installed options."""
    res: list[str] = []
    for item in launchers_config:
        candidates = [item] if isinstance(item, str) else item
        for candidate in candidates:
            desktop = candidate
            if desktop.startswith("applications:"):
                desktop = desktop[len("applications:") :]
            if desktop_exists(desktop):
                res.append(candidate)
                break
    return res


def get_qdbus_command() -> str | None:
    """Return the absolute path of the first available qdbus executable."""
    for candidate in ("qdbus6", "qdbus-qt6", "qdbus"):
        cmd = shutil.which(candidate)
        if cmd:
            return cmd
    return None


def evaluate_plasma_script(script: str) -> bool:
    """Execute a script via org.kde.PlasmaShell.evaluateScript."""
    qdbus = get_qdbus_command()
    if not qdbus:
        return False
    try:
        res = run_command(
            [
                qdbus,
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return res.returncode == 0
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        logger.debug("handled expected exception", exc_info=True)
        return False


def kreadconfig(file: str, group: str, key: str) -> str | None:
    """Read a KDE configuration key."""
    cmd = shutil.which("kreadconfig6") or shutil.which("kreadconfig")
    if not cmd:
        return None
    try:
        res = run_command(
            [cmd, "--file", file, "--group", group, "--key", key],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        logger.debug("handled expected exception", exc_info=True)
        pass
    return None


def kwriteconfig(file: str, group: str | list[str], key: str, value: str, value_type: str | None = None) -> bool:
    """Write a KDE configuration key. ``group`` may be a nested group path, e.g. ``["Containments", "1", "General"]``."""
    cmd = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig")
    if not cmd:
        return False
    groups = [group] if isinstance(group, str) else group
    args = [cmd, "--file", file]
    for g in groups:
        args.extend(["--group", g])
    args.extend(["--key", key])
    if value_type:
        args.extend(["--type", value_type])
    args.append(value)
    try:
        res = run_command(
            args,
            capture_output=True,
            timeout=5,
            check=False,
        )
        return res.returncode == 0
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        logger.debug("handled expected exception", exc_info=True)
        return False


def get_default_launchers() -> list[list[str] | str]:
    return [
        "applications:kyth-welcome.desktop",
        "applications:kyth-app-store.desktop",
        ["applications:com.valvesoftware.Steam.desktop", "applications:steam.desktop"],
        ["applications:com.brave.Browser.desktop", "applications:chromium-browser.desktop"],
        "applications:org.kde.dolphin.desktop",
        "applications:org.kde.konsole.desktop",
    ]


def apply_desktop_layout(*, force: bool = False, initial: bool = False) -> int:
    """Python implementation of kyth-apply-desktop-layout."""
    if not force:
        current = kreadconfig(CONFIG_FILE, "KythOS", "KythComfortLayout")
        legacy_current = kreadconfig(CONFIG_FILE, "KythOS", "WindowsFamiliarLayout")
        if current in (LAYOUT_VERSION, "kyth-comfort-v2") or legacy_current == "windows-familiar-v1":
            return 0

    if not force and not initial:
        return 64

    qdbus = get_qdbus_command()
    if not qdbus:
        return 75

    available = filter_available_launchers(get_default_launchers())
    launcher_csv = ",".join(available)

    js_template = """var launchers = "{launchers}";
var trayItems = "{tray_items}";
var hiddenTrayItems = "{hidden_tray_items}";

function safeSet(object, key, value) {{
    try {{
        object[key] = value;
    }} catch (e) {{
    }}
}}

function writeConfig(object, groups, values) {{
    try {{
        object.currentConfigGroup = groups;
        for (var key in values) {{
            object.writeConfig(key, values[key]);
        }}
        object.reloadConfig();
    }} catch (e) {{
    }}
}}

function removeExistingPanels() {{
    var ids = [];
    for (var i = 0; i < panelIds.length; ++i) {{
        ids.push(panelIds[i]);
    }}
    for (var i = 0; i < ids.length; ++i) {{
        var panel = panelById(ids[i]);
        if (panel) {{
            panel.remove();
        }}
    }}
}}

function uniqueScreens() {{
    var seen = [];
    var desktopsArray = desktops();
    for (var i = 0; i < desktopsArray.length; ++i) {{
        var screen = desktopsArray[i].screen;
        if (seen.indexOf(screen) === -1) {{
            seen.push(screen);
        }}
    }}
    if (seen.length === 0) {{
        seen.push(0);
    }}
    return seen;
}}

function configureDesktops() {{
    var desktopsArray = desktops();
    for (var i = 0; i < desktopsArray.length; ++i) {{
        var desktop = desktopsArray[i];
        desktop.wallpaperPlugin = "org.kde.image";
        writeConfig(desktop, ["Wallpaper", "org.kde.image", "General"], {{
            "Image": "/usr/share/wallpapers/kyth/contents/images/1920x1080.svg"
        }});
        writeConfig(desktop, ["General"], {{
            "ToolBoxButtonState": "topcenter"
        }});
    }}
}}

function addKythDefaultPanel(screen) {{
    var panel = new Panel;
    safeSet(panel, "screen", screen);
    panel.location = "bottom";
    panel.height = 42;
    safeSet(panel, "alignment", "left");
    safeSet(panel, "floating", false);
    safeSet(panel, "floatingApplets", false);

    var kickoff = panel.addWidget("org.kde.plasma.kickoff");
    writeConfig(kickoff, ["General"], {{
        "icon": "kyth-kickoff",
        "favoritesPortedToKAstats": true,
        "alphaSort": true,
        "showActionButtonCaptions": true
    }});

    var tasks = panel.addWidget("org.kde.plasma.icontasks");
    writeConfig(tasks, ["General"], {{
        "launchers": launchers,
        "showOnlyCurrentDesktop": false,
        "showOnlyCurrentScreen": false,
        "showOnlyCurrentActivity": false,
        "groupingStrategy": 1,
        "maxStripes": 1,
        "showToolTips": true,
        "wheelEnabled": "AllTask",
        "indicateAudioStreams": true,
        "highlightWindows": true,
        "middleClickAction": "NewInstance"
    }});

    panel.addWidget("org.kde.plasma.marginsseparator");
    panel.addWidget("org.kde.plasma.panelspacer");

    var tray = panel.addWidget("org.kde.plasma.systemtray");
    writeConfig(tray, ["General"], {{
        "extraItems": trayItems,
        "hiddenItems": hiddenTrayItems,
        "knownItems": trayItems + "," + hiddenTrayItems,
        "showAllItems": false
    }});

    var clock = panel.addWidget("org.kde.plasma.digitalclock");
    writeConfig(clock, ["Appearance"], {{
        "showDate": false,
        "dateFormat": "shortDate",
        "showSeconds": false
    }});

    panel.addWidget("org.kde.plasma.showdesktop");
}}

removeExistingPanels();
configureDesktops();
var screens = uniqueScreens();
for (var i = 0; i < screens.length; ++i) {{
    addKythDefaultPanel(screens[i]);
}}
"""
    script = js_template.format(
        launchers=launcher_csv,
        tray_items=",".join(TRAY_ITEMS),
        hidden_tray_items=",".join(HIDDEN_TRAY_ITEMS),
    )

    if evaluate_plasma_script(script):
        kwriteconfig(CONFIG_FILE, "KythOS", "KythComfortLayout", LAYOUT_VERSION)
        return 0
    return 1


def refresh_taskbar_pins() -> int:
    """Python implementation of kyth-refresh-taskbar-pins."""
    stamp = kreadconfig(CONFIG_FILE, "KythOS", "KythComfortLayout")
    if not stamp:
        return 0

    available = filter_available_launchers(get_default_launchers())
    launcher_csv = ",".join(available)
    if not launcher_csv:
        return 0

    state_dir = Path.home() / ".local" / "share" / "kyth"
    state_file = state_dir / "taskbar-pins"
    try:
        if state_file.is_file() and state_file.read_text(encoding="utf-8").strip() == launcher_csv:
            return 0
    except (OSError, ValueError, UnicodeError):
        logger.debug("handled expected exception", exc_info=True)
        pass

    qdbus = get_qdbus_command()
    if not qdbus:
        return 0

    js_script = f"""var launchers = "{launcher_csv}";
for (var i = 0; i < panelIds.length; ++i) {{
    var panel = panelById(panelIds[i]);
    if (!panel) {{
        continue;
    }}
    var ids = panel.widgetIds;
    for (var j = 0; j < ids.length; ++j) {{
        var widget = panel.widgetById(ids[j]);
        if (widget && widget.type === "org.kde.plasma.icontasks") {{
            try {{
                widget.currentConfigGroup = ["General"];
                widget.writeConfig("launchers", launchers);
                widget.reloadConfig();
            }} catch (e) {{
            }}
        }}
    }}
}}
"""
    if evaluate_plasma_script(js_script):
        try:
            state_dir.mkdir(parents=True, exist_ok=True)
            state_file.write_text(launcher_csv + "\n", encoding="utf-8")
        except (OSError, ValueError, UnicodeError):
            logger.debug("handled expected exception", exc_info=True)
            pass
        return 0
    return 1


def apply_role_preset(profile: str) -> int:
    """Python implementation of kyth-apply-role-preset."""
    if profile in ("work", "both", "everyday"):
        profile = "everyday"
        launchers = [
            "applications:kyth-welcome.desktop",
            "applications:kyth-app-store.desktop",
            "applications:com.brave.Browser.desktop",
            "applications:org.kde.dolphin.desktop",
            "applications:org.libreoffice.LibreOffice.desktop",
            "applications:eu.betterbird.Betterbird.desktop",
            "applications:org.kde.konsole.desktop",
        ]
    elif profile == "gaming":
        launchers = [
            "applications:kyth-welcome.desktop",
            "applications:kyth-app-store.desktop",
            "applications:com.valvesoftware.Steam.desktop",
            "applications:com.brave.Browser.desktop",
            "applications:dev.vencord.Vesktop.desktop",
            "applications:org.kde.dolphin.desktop",
            "applications:org.kde.konsole.desktop",
        ]
    else:
        return 64

    profile_dir = Path.home() / ".local" / "share" / "kyth"
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "profile").write_text(profile + "\n", encoding="utf-8")
    except (OSError, ValueError, UnicodeError):
        logger.debug("handled expected exception", exc_info=True)
        pass

    available_launchers = filter_available_launchers(launchers)
    launcher_csv = ",".join(available_launchers)
    favorite_csv = launcher_csv  # same set for favorites

    kwriteconfig("kickoffrc", "Favorites", "FavoriteURLs", favorite_csv)
    kwriteconfig("plasma-discoverrc", "UpdatesNotifier", "UseNotifications", "false", "bool")

    qdbus = get_qdbus_command()
    if qdbus:
        js_script = f"""var launchers = "{launcher_csv}";
var trayItems = "{','.join(TRAY_ITEMS)}";
var hiddenTrayItems = "{','.join(HIDDEN_TRAY_ITEMS)}";

function writeConfig(object, groups, values) {{
    try {{
        object.currentConfigGroup = groups;
        for (var key in values) {{
            object.writeConfig(key, values[key]);
        }}
        object.reloadConfig();
    }} catch (e) {{
    }}
}}

for (var p = 0; p < panelIds.length; ++p) {{
    var panel = panelById(panelIds[p]);
    if (!panel || !panel.widgets) {{
        continue;
    }}
    var widgets = panel.widgets();
    for (var i = 0; i < widgets.length; ++i) {{
        var widget = widgets[i];
        if (widget.type === "org.kde.plasma.icontasks") {{
            writeConfig(widget, ["General"], {{
                "launchers": launchers,
                "showOnlyCurrentDesktop": false,
                "showOnlyCurrentScreen": false,
                "showOnlyCurrentActivity": false,
                "groupingStrategy": 1,
                "maxStripes": 1,
                "showToolTips": true,
                "wheelEnabled": "AllTask",
                "indicateAudioStreams": true,
                "highlightWindows": true,
                "middleClickAction": "NewInstance"
            }});
        }} else if (widget.type === "org.kde.plasma.systemtray") {{
            writeConfig(widget, ["General"], {{
                "extraItems": trayItems,
                "hiddenItems": hiddenTrayItems,
                "knownItems": trayItems + "," + hiddenTrayItems,
                "showAllItems": false
            }});
        }} else if (widget.type === "org.kde.plasma.digitalclock") {{
            writeConfig(widget, ["Appearance"], {{
                "showDate": false,
                "dateFormat": "shortDate",
                "showSeconds": false
            }});
        }}
    }}
}}
"""
        evaluate_plasma_script(js_script)

    kbuildsycoca = shutil.which("kbuildsycoca6") or shutil.which("kbuildsycoca")
    if kbuildsycoca:
        try:
            run_command([kbuildsycoca, "--noincremental"], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            logger.debug("handled expected exception", exc_info=True)
            pass

    return 0
