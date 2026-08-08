# shellcheck shell=bash
# ── EXE compat checker (.exe hover) ──────────────────────────────────────
install -m 0755 /ctx/kyth-exe-compat /usr/bin/kyth-exe-compat
# mimeapps.list xdg-open interceptor hash-gated: .exe → kyth-exe-compat
if [[ -f /usr/share/applications/kyth-exe-compat.desktop ]]; then
    : # already
else
    cat > /usr/share/applications/kyth-exe-compat.desktop <<'DESKEOF'
[Desktop Entry]
Type=Application
Name=Kyth EXE Compat Check
Exec=/usr/bin/kyth-exe-compat %f
MimeType=application/x-ms-dos-executable;application/x-msdos-program;
NoDisplay=true
DESKEOF
fi
