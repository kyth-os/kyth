# shellcheck shell=bash
# ── Steam first-run notification ─────────────────────────────────────────────
# Wrap the Steam launcher so that on the very first launch, a passive popup
# appears telling the user setup may take a few minutes.  The flag file is
# written only after the notification attempt completes so a silent failure
# doesn't permanently suppress the message on the next launch attempt.
# To reset: rm ~/.local/share/kyth-steam-initialized
cat >/usr/bin/kyth-steam <<'STEAMEOF'
#!/bin/bash
FLAG="${HOME}/.local/share/kyth-steam-initialized"
if [[ ! -f "${FLAG}" ]]; then
    mkdir -p "$(dirname "${FLAG}")"
    (
        if command -v kdialog &>/dev/null; then
            kdialog --title "KythOS" --passivepopup \
                "Steam is setting up for the first time. This may take a few minutes — please be patient." \
                30
        elif command -v notify-send &>/dev/null; then
            notify-send --urgency=normal --expire-time=30000 \
                "Steam First Start" \
                "Steam is setting up for the first time. This may take a few minutes — please be patient."
        fi
        touch "${FLAG}"
    ) &
fi
exec /usr/bin/steam "$@"
STEAMEOF
chmod +x /usr/bin/kyth-steam

# Override the Steam .desktop Exec line to use the wrapper.
# sysconfig.sh (Layer 3) already wrote a patched copy to /usr/local/share/applications/
# to strip PrefersNonDefaultGPU/X-KDE-RunOnDiscreteGpu. XDG gives /usr/local priority,
# so that copy is what KDE and launchers actually see — patch both to ensure the
# kyth-steam wrapper takes effect regardless of which path wins.
for desktop in \
	/usr/share/applications/steam.desktop \
	/usr/local/share/applications/steam.desktop; do
	if [[ -f "${desktop}" ]]; then
		sed -i 's|^Exec=/usr/bin/steam|Exec=/usr/bin/kyth-steam|g' "${desktop}"
	fi
done
