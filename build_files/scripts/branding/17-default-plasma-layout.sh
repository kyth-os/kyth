# shellcheck shell=bash
# ── KythOS default Plasma layout preset ───────────────────────────────────────
# Applies the distinctive KythOS desktop shape: bottom taskbar, KythOS launcher,
# pinned everyday apps, system tray, clock, show-desktop target, wallpaper, and
# a restore marker. Run with --initial for fresh users and --force when the user
# explicitly clicks "Restore KythOS Layout" in System Hub.
cat >/usr/bin/kyth-apply-desktop-layout <<'LAYOUTEOF'
#!/usr/bin/env bash
set -euo pipefail

force=0
initial=0
layout_version="kyth-comfort-v4"
config_file="plasma-org.kde.plasma.desktop-appletsrc"

for arg in "$@"; do
    case "${arg}" in
        --force)
            force=1
            ;;
        --initial)
            initial=1
            ;;
        -h|--help)
            printf 'Usage: kyth-apply-desktop-layout [--initial|--force]\n'
            exit 0
            ;;
    esac
done

if [[ "${force}" != "1" ]]; then
    current=""
    legacy_current=""
    if command -v kreadconfig6 >/dev/null 2>&1; then
        current="$(kreadconfig6 --file "${config_file}" --group KythOS --key KythComfortLayout 2>/dev/null || true)"
        legacy_current="$(kreadconfig6 --file "${config_file}" --group KythOS --key WindowsFamiliarLayout 2>/dev/null || true)"
    fi
    if [[ "${current}" == "${layout_version}" || "${current}" == "kyth-comfort-v2" || "${legacy_current}" == "windows-familiar-v1" ]]; then
        exit 0
    fi
fi

if [[ "${force}" != "1" && "${initial}" != "1" ]]; then
    echo "Refusing to change an existing layout without --initial or --force." >&2
    exit 64
fi

qdbus_cmd=""
for candidate in qdbus6 qdbus-qt6 qdbus; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        qdbus_cmd="${candidate}"
        break
    fi
done
if [[ -z "${qdbus_cmd}" ]]; then
    echo "qdbus6/qdbus-qt6/qdbus is not available; Plasma layout cannot be applied." >&2
    exit 75
fi

runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
[[ -d "${runtime_dir}" ]] || runtime_dir="/tmp"
script_file="$(mktemp "${runtime_dir}/kyth-layout.XXXXXX.js")"
trap 'rm -f "${script_file}"' EXIT

cat > "${script_file}" <<'JSEOF'
var launchers = [
    "applications:kyth-welcome.desktop",
    "applications:kyth-app-store.desktop",
    "applications:steam.desktop",
    "applications:com.brave.Browser.desktop",
    "applications:org.kde.dolphin.desktop",
    "applications:org.kde.konsole.desktop"
].join(",");

var trayItems = [
    "org.kde.plasma.networkmanagement",
    "org.kde.plasma.volume",
    "org.kde.plasma.bluetooth",
    "org.kde.plasma.battery",
    "org.kde.plasma.notifications",
    "org.kde.plasma.clipboard",
    "org.kde.plasma.devicenotifier",
    "org.kde.plasma.printmanager",
    "org.kde.kdeconnect"
].join(",");

var hiddenTrayItems = [
    "org.kde.plasma.keyboardindicator",
    "org.kde.plasma.mediacontroller"
].join(",");

function safeSet(object, key, value) {
    try {
        object[key] = value;
    } catch (e) {
    }
}

function writeConfig(object, groups, values) {
    try {
        object.currentConfigGroup = groups;
        for (var key in values) {
            object.writeConfig(key, values[key]);
        }
        object.reloadConfig();
    } catch (e) {
    }
}

function removeExistingPanels() {
    var ids = [];
    for (var i = 0; i < panelIds.length; ++i) {
        ids.push(panelIds[i]);
    }
    for (var i = 0; i < ids.length; ++i) {
        var panel = panelById(ids[i]);
        if (panel) {
            panel.remove();
        }
    }
}

function uniqueScreens() {
    var seen = [];
    var desktopsArray = desktops();
    for (var i = 0; i < desktopsArray.length; ++i) {
        var screen = desktopsArray[i].screen;
        if (seen.indexOf(screen) === -1) {
            seen.push(screen);
        }
    }
    if (seen.length === 0) {
        seen.push(0);
    }
    return seen;
}

function configureDesktops() {
    var desktopsArray = desktops();
    for (var i = 0; i < desktopsArray.length; ++i) {
        var desktop = desktopsArray[i];
        desktop.wallpaperPlugin = "org.kde.image";
        writeConfig(desktop, ["Wallpaper", "org.kde.image", "General"], {
            "Image": "/usr/share/wallpapers/kyth/contents/images/1920x1080.svg"
        });
        writeConfig(desktop, ["General"], {
            "ToolBoxButtonState": "topcenter"
        });
    }
}

function addKythDefaultPanel(screen) {
    var panel = new Panel;
    safeSet(panel, "screen", screen);
    panel.location = "bottom";
    panel.height = 42;
    safeSet(panel, "alignment", "left");
    safeSet(panel, "floating", false);
    safeSet(panel, "floatingApplets", false);

    var kickoff = panel.addWidget("org.kde.plasma.kickoff");
    writeConfig(kickoff, ["General"], {
        "icon": "kyth-kickoff",
        "favoritesPortedToKAstats": true,
        "alphaSort": true,
        "showActionButtonCaptions": true
    });

    var tasks = panel.addWidget("org.kde.plasma.icontasks");
    writeConfig(tasks, ["General"], {
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
    });

    panel.addWidget("org.kde.plasma.marginsseparator");

    panel.addWidget("org.kde.plasma.panelspacer");

    var tray = panel.addWidget("org.kde.plasma.systemtray");
    writeConfig(tray, ["General"], {
        "extraItems": trayItems,
        "hiddenItems": hiddenTrayItems,
        "knownItems": trayItems + "," + hiddenTrayItems,
        "showAllItems": false
    });

    var clock = panel.addWidget("org.kde.plasma.digitalclock");
    writeConfig(clock, ["Appearance"], {
        "showDate": false,
        "dateFormat": "shortDate",
        "showSeconds": false
    });

    panel.addWidget("org.kde.plasma.showdesktop");
}

removeExistingPanels();
configureDesktops();
var screens = uniqueScreens();
for (var i = 0; i < screens.length; ++i) {
    addKythDefaultPanel(screens[i]);
}
JSEOF

"${qdbus_cmd}" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(cat "${script_file}")" >/dev/null

if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file "${config_file}" --group KythOS --key KythComfortLayout "${layout_version}" >/dev/null 2>&1 || true
fi
LAYOUTEOF
chmod +x /usr/bin/kyth-apply-desktop-layout
