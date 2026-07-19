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

# Steam and Brave are Flatpaks installed on first boot by
# kyth-default-flatpaks.service, which races this layout pass — at first login
# their .desktop files usually do not exist yet, and in the live session they
# never will (that service is masked there). Pinning a missing .desktop leaves a
# dead taskbar icon, and the layout is version-stamped so it never self-heals.
# Pin only what exists now; kyth-refresh-taskbar-pins adds the rest once the
# Flatpaks land. Mirrors desktop_exists() in kyth-apply-role-preset.
desktop_exists() {
    local desktop="$1"
    local path
    for path in \
        "/usr/share/applications/${desktop}" \
        "/var/lib/flatpak/exports/share/applications/${desktop}" \
        "${HOME}/.local/share/applications/${desktop}" \
        "${HOME}/.local/share/flatpak/exports/share/applications/${desktop}"; do
        if [[ -f "${path}" ]]; then
            return 0
        fi
    done
    return 1
}

# Pin the first candidate that actually exists, skipping the entry entirely when
# none do. Steam is shipped as a Flatpak (com.valvesoftware.Steam.desktop); the
# bare steam.desktop is the RPM name and is only a fallback — pinning it
# unconditionally produced a permanently dead taskbar icon.
available_launchers=()
add_launcher() {
    local candidate
    for candidate in "$@"; do
        if desktop_exists "${candidate#applications:}"; then
            available_launchers+=("${candidate}")
            return 0
        fi
    done
    return 0
}

add_launcher "applications:kyth-welcome.desktop"
add_launcher "applications:kyth-app-store.desktop"
add_launcher "applications:com.valvesoftware.Steam.desktop" "applications:steam.desktop"
add_launcher "applications:com.brave.Browser.desktop" "applications:chromium-browser.desktop"
add_launcher "applications:org.kde.dolphin.desktop"
add_launcher "applications:org.kde.konsole.desktop"
launcher_csv="$(IFS=,; printf '%s' "${available_launchers[*]}")"

cat > "${script_file}" <<'JSEOF'
var launchers = "__KYTH_LAUNCHERS__";

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

# The JS heredoc is quoted so Plasma's own ${...} stays intact; substitute the
# availability-filtered pin list afterwards. The CSV never contains '|'.
sed -i "s|__KYTH_LAUNCHERS__|${launcher_csv}|" "${script_file}"

"${qdbus_cmd}" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(cat "${script_file}")" >/dev/null

if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file "${config_file}" --group KythOS --key KythComfortLayout "${layout_version}" >/dev/null 2>&1 || true
fi
LAYOUTEOF
chmod +x /usr/bin/kyth-apply-desktop-layout

# ── Taskbar pin refresh ───────────────────────────────────────────────────────
# Second half of the fix above. kyth-apply-desktop-layout pins only apps that
# exist at first login, and it is version-stamped so it never runs again — so
# without this, Steam and Brave would be missing from the taskbar forever once
# their Flatpaks finally install. This re-syncs just the icontasks pin list (it
# does NOT rebuild the panel, which would discard user customisation) and is
# driven by a .path unit watching the Flatpak exports directory.
cat >/usr/bin/kyth-refresh-taskbar-pins <<'PINREFRESHEOF'
#!/usr/bin/env bash
set -euo pipefail

config_file="plasma-org.kde.plasma.desktop-appletsrc"

# Only meaningful once the KythOS layout exists; the initial pass pins correctly
# on its own, and running before it would fight that pass.
if command -v kreadconfig6 >/dev/null 2>&1; then
    stamp="$(kreadconfig6 --file "${config_file}" --group KythOS --key KythComfortLayout 2>/dev/null || true)"
    [[ -n "${stamp}" ]] || exit 0
else
    exit 0
fi

desktop_exists() {
    local desktop="$1"
    local path
    for path in \
        "/usr/share/applications/${desktop}" \
        "/var/lib/flatpak/exports/share/applications/${desktop}" \
        "${HOME}/.local/share/applications/${desktop}" \
        "${HOME}/.local/share/flatpak/exports/share/applications/${desktop}"; do
        if [[ -f "${path}" ]]; then
            return 0
        fi
    done
    return 1
}

# Keep this candidate list in sync with kyth-apply-desktop-layout.
available_launchers=()
add_launcher() {
    local candidate
    for candidate in "$@"; do
        if desktop_exists "${candidate#applications:}"; then
            available_launchers+=("${candidate}")
            return 0
        fi
    done
    return 0
}

add_launcher "applications:kyth-welcome.desktop"
add_launcher "applications:kyth-app-store.desktop"
add_launcher "applications:com.valvesoftware.Steam.desktop" "applications:steam.desktop"
add_launcher "applications:com.brave.Browser.desktop" "applications:chromium-browser.desktop"
add_launcher "applications:org.kde.dolphin.desktop"
add_launcher "applications:org.kde.konsole.desktop"
launcher_csv="$(IFS=,; printf '%s' "${available_launchers[*]}")"
[[ -n "${launcher_csv}" ]] || exit 0

# No-op when nothing changed, so the .path unit firing repeatedly during a long
# Flatpak install does not churn the panel config.
state_dir="${HOME}/.local/share/kyth"
state_file="${state_dir}/taskbar-pins"
if [[ -f "${state_file}" && "$(cat "${state_file}" 2>/dev/null)" == "${launcher_csv}" ]]; then
    exit 0
fi

qdbus_cmd=""
for candidate in qdbus6 qdbus-qt6 qdbus; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        qdbus_cmd="${candidate}"
        break
    fi
done
[[ -n "${qdbus_cmd}" ]] || exit 0

runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
[[ -d "${runtime_dir}" ]] || runtime_dir="/tmp"
script_file="$(mktemp "${runtime_dir}/kyth-pins.XXXXXX.js")"
trap 'rm -f "${script_file}"' EXIT

cat > "${script_file}" <<'PINJSEOF'
var launchers = "__KYTH_LAUNCHERS__";
for (var i = 0; i < panelIds.length; ++i) {
    var panel = panelById(panelIds[i]);
    if (!panel) {
        continue;
    }
    var ids = panel.widgetIds;
    for (var j = 0; j < ids.length; ++j) {
        var widget = panel.widgetById(ids[j]);
        if (widget && widget.type === "org.kde.plasma.icontasks") {
            try {
                widget.currentConfigGroup = ["General"];
                widget.writeConfig("launchers", launchers);
                widget.reloadConfig();
            } catch (e) {
            }
        }
    }
}
PINJSEOF

sed -i "s|__KYTH_LAUNCHERS__|${launcher_csv}|" "${script_file}"

if "${qdbus_cmd}" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(cat "${script_file}")" >/dev/null 2>&1; then
    mkdir -p "${state_dir}"
    printf '%s\n' "${launcher_csv}" > "${state_file}"
fi
PINREFRESHEOF
chmod +x /usr/bin/kyth-refresh-taskbar-pins

mkdir -p /etc/systemd/user/default.target.wants
cat >/etc/systemd/user/kyth-refresh-taskbar-pins.service <<'PINSERVICEEOF'
[Unit]
Description=Re-sync KythOS taskbar pins with installed applications

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-refresh-taskbar-pins
PINSERVICEEOF

cat >/etc/systemd/user/kyth-refresh-taskbar-pins.path <<'PINPATHEOF'
[Unit]
Description=Watch for newly installed Flatpak launchers

[Path]
PathChanged=/var/lib/flatpak/exports/share/applications
Unit=kyth-refresh-taskbar-pins.service

[Install]
WantedBy=default.target
PINPATHEOF
ln -sf /etc/systemd/user/kyth-refresh-taskbar-pins.path \
	/etc/systemd/user/default.target.wants/kyth-refresh-taskbar-pins.path
