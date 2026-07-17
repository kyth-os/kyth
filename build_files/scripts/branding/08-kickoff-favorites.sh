# shellcheck shell=bash
# ── Kickoff favorites ─────────────────────────────────────────────────────────
# Pre-populate the Kickoff launcher favorites for new users.
# Brave and Discord are listed here even though they install via
# kyth-default-flatpaks.service at first boot — KDE silently omits entries
# whose desktop files don't exist yet and shows them automatically once the
# flatpak finishes installing.
cat >/etc/skel/.config/kickoffrc <<'KICKOFFEOF'
[Favorites]
FavoriteURLs=applications:kyth-welcome.desktop,applications:kyth-app-store.desktop,applications:steam.desktop,applications:com.brave.Browser.desktop,applications:com.discordapp.Discord.desktop,applications:org.kde.konsole.desktop

[General]
highlightNewlyInstalledApps=false
KICKOFFEOF
mkdir -p /etc/xdg
install -m 0644 /etc/skel/.config/kickoffrc /etc/xdg/kickoffrc
