# shellcheck shell=bash
# ── Kickoff plasmoid defaults ─────────────────────────────────────────────────
# Patch Kickoff's KConfig XML so every new widget instance defaults to
# kyth-kickoff and quiet newly-installed app badges before any per-user config
# file or first-login script exists.
# The empty <default></default> is the upstream fallback that causes Kickoff
# to use start-here-kde-plasma from the icon theme; we replace it with the
# named icon so the plasmoid's own default wins unconditionally.
_kickoff_cfg=/usr/share/plasma/plasmoids/org.kde.plasma.kickoff/contents/config/main.xml
if [[ -f "${_kickoff_cfg}" ]]; then
	sed -i \
		'/<entry name="icon" type="String">/,/<\/entry>/ {
            s|<default></default>|<default>kyth-kickoff</default>|
        }' \
		"${_kickoff_cfg}"
	sed -i \
		'/<entry name="highlightNewlyInstalledApps" type="Bool">/,/<\/entry>/ {
            s|<default>true</default>|<default>false</default>|
        }' \
		"${_kickoff_cfg}"
fi
