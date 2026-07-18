# shellcheck shell=bash
# ── KythOS role presets ───────────────────────────────────────────────────────
# Lightweight, user-controlled presets for the home page focus picker. These
# alter prominence and pins only; they never remove apps or hide tools from
# search.
cat >/usr/bin/kyth-apply-role-preset <<'ROLEPRESETEOF'
#!/usr/bin/env bash
set -euo pipefail

profile="${1:-everyday}"
case "${profile}" in
    work|both|everyday)
        profile="everyday"
        launchers=(
            "applications:kyth-welcome.desktop"
            "applications:kyth-app-store.desktop"
            "applications:com.brave.Browser.desktop"
            "applications:org.kde.dolphin.desktop"
            "applications:org.libreoffice.LibreOffice.desktop"
            "applications:eu.betterbird.Betterbird.desktop"
            "applications:org.kde.konsole.desktop"
        )
        favorites=(
            "applications:kyth-welcome.desktop"
            "applications:kyth-app-store.desktop"
            "applications:com.brave.Browser.desktop"
            "applications:org.kde.dolphin.desktop"
            "applications:org.libreoffice.LibreOffice.desktop"
            "applications:eu.betterbird.Betterbird.desktop"
            "applications:org.kde.konsole.desktop"
        )
        ;;
    gaming)
        launchers=(
            "applications:kyth-welcome.desktop"
            "applications:kyth-app-store.desktop"
            "applications:steam.desktop"
            "applications:com.brave.Browser.desktop"
            "applications:dev.vencord.Vesktop.desktop"
            "applications:org.kde.dolphin.desktop"
            "applications:org.kde.konsole.desktop"
        )
        favorites=(
            "applications:kyth-welcome.desktop"
            "applications:kyth-app-store.desktop"
            "applications:steam.desktop"
            "applications:com.brave.Browser.desktop"
            "applications:dev.vencord.Vesktop.desktop"
            "applications:org.kde.dolphin.desktop"
            "applications:org.kde.konsole.desktop"
        )
        ;;
    *)
        echo "Usage: kyth-apply-role-preset [everyday|gaming]" >&2
        exit 64
        ;;
esac

profile_dir="${HOME}/.local/share/kyth"
mkdir -p "${profile_dir}"
printf '%s\n' "${profile}" > "${profile_dir}/profile"

join_by_comma() {
    local IFS=,
    printf '%s' "$*"
}

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

append_if_available() {
    local -n target_ref=$1
    local launcher="$2"
    local desktop="${launcher#applications:}"
    if desktop_exists "${desktop}"; then
        target_ref+=("${launcher}")
    fi
}

filtered_launchers=()
for launcher in "${launchers[@]}"; do
    append_if_available filtered_launchers "${launcher}"
done
launchers=("${filtered_launchers[@]}")

filtered_favorites=()
for launcher in "${favorites[@]}"; do
    append_if_available filtered_favorites "${launcher}"
done
favorites=("${filtered_favorites[@]}")

launcher_csv="$(join_by_comma "${launchers[@]}")"
favorite_csv="$(join_by_comma "${favorites[@]}")"
tray_csv="org.kde.plasma.networkmanagement,org.kde.plasma.volume,org.kde.plasma.bluetooth,org.kde.plasma.battery,org.kde.plasma.notifications,org.kde.plasma.clipboard,org.kde.plasma.devicenotifier,org.kde.plasma.printmanager,org.kde.kdeconnect"
hidden_tray_csv="org.kde.plasma.keyboardindicator,org.kde.plasma.mediacontroller"

if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file kickoffrc --group Favorites --key FavoriteURLs "${favorite_csv}"
    kwriteconfig6 --file plasma-discoverrc --group UpdatesNotifier --key UseNotifications --type bool false
fi

qdbus_cmd=""
for candidate in qdbus6 qdbus-qt6 qdbus; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        qdbus_cmd="${candidate}"
        break
    fi
done

if [[ -n "${qdbus_cmd}" ]]; then
    runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
    [[ -d "${runtime_dir}" ]] || runtime_dir="/tmp"
    script_file="$(mktemp "${runtime_dir}/kyth-role-preset.XXXXXX.js")"
    trap 'rm -f "${script_file}"' EXIT
    cat > "${script_file}" <<JSEOF
var launchers = "${launcher_csv}";
var trayItems = "${tray_csv}";
var hiddenTrayItems = "${hidden_tray_csv}";

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

for (var p = 0; p < panelIds.length; ++p) {
    var panel = panelById(panelIds[p]);
    if (!panel || !panel.widgets) {
        continue;
    }
    var widgets = panel.widgets();
    for (var i = 0; i < widgets.length; ++i) {
        var widget = widgets[i];
        if (widget.type === "org.kde.plasma.icontasks") {
            writeConfig(widget, ["General"], {
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
        } else if (widget.type === "org.kde.plasma.systemtray") {
            writeConfig(widget, ["General"], {
                "extraItems": trayItems,
                "hiddenItems": hiddenTrayItems,
                "knownItems": trayItems + "," + hiddenTrayItems,
                "showAllItems": false
            });
        } else if (widget.type === "org.kde.plasma.digitalclock") {
            writeConfig(widget, ["Appearance"], {
                "showDate": false,
                "dateFormat": "shortDate",
                "showSeconds": false
            });
        }
    }
}
JSEOF
    "${qdbus_cmd}" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(cat "${script_file}")" >/dev/null 2>&1 || true
fi

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

echo "Applied ${profile} preset."
ROLEPRESETEOF
chmod +x /usr/bin/kyth-apply-role-preset
