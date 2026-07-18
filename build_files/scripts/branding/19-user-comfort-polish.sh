# shellcheck shell=bash
# ── User comfort polish ───────────────────────────────────────────────────────
# KDE stores several comfort preferences per-user. Bake a versioned, automatic
# polish pass into the image so new accounts get it from /etc/skel and existing
# accounts receive it once after an OS update.
cat >/usr/bin/kyth-user-polish <<'POLISHEOF'
#!/usr/bin/env bash
set -euo pipefail

version="v12"
stamp_dir="${HOME}/.local/share/kyth"
stamp="${stamp_dir}/user-polish-${version}"
old_autostart="${HOME}/.config/autostart/kyth-windows-friendly-defaults.desktop"
force=0
had_polish_stamp=0

for arg in "$@"; do
    case "${arg}" in
        --force)
            force=1
            ;;
        -h|--help)
            printf 'Usage: kyth-user-polish [--force]\n'
            exit 0
            ;;
    esac
done

if [[ -d "${stamp_dir}" ]] && compgen -G "${stamp_dir}/user-polish-*" >/dev/null; then
    had_polish_stamp=1
fi

if [[ -f "${stamp}" && "${force}" != "1" ]]; then
    rm -f "${old_autostart}" "${HOME}/.config/autostart/kyth-user-polish.desktop" 2>/dev/null || true
    exit 0
fi

mkdir -p "${stamp_dir}"

# Ensure common folders exist even when xdg-user-dirs did not run yet. Games is
# intentionally non-standard, but important for a gaming-first workstation where
# local launchers, save backups, mods, and exports need an obvious home.
if command -v xdg-user-dirs-update >/dev/null 2>&1; then
    xdg-user-dirs-update >/dev/null 2>&1 || true
fi
mkdir -p \
    "${HOME}/Desktop" \
    "${HOME}/Documents" \
    "${HOME}/Downloads" \
    "${HOME}/Games" \
    "${HOME}/Music" \
    "${HOME}/Pictures" \
    "${HOME}/Public" \
    "${HOME}/Screenshots" \
    "${HOME}/Templates" \
    "${HOME}/Videos"

if [[ ! -f "${HOME}/Games/.directory" ]]; then
    cat > "${HOME}/Games/.directory" <<'GAMESDIREEOF'
[Desktop Entry]
Icon=applications-games
Name=Games
GAMESDIREEOF
fi

if [[ ! -f "${HOME}/Screenshots/.directory" ]]; then
    cat > "${HOME}/Screenshots/.directory" <<'SHOTSDIREEOF'
[Desktop Entry]
Icon=folder-pictures
Name=Screenshots
SHOTSDIREEOF
fi

if [[ ! -f "${HOME}/Templates/Plain Text.txt" ]]; then
    printf '' > "${HOME}/Templates/Plain Text.txt"
fi

# File associations that make double-click behavior feel normal on day one.
# Use xdg-mime so existing user choices are updated per MIME type without
# clobbering unrelated custom associations.
mkdir -p "${HOME}/.config"

# BlueDevil persists adapter power state per-user and restores it after the
# system boot helper runs. Clear stale disabled state once so an OS update does
# not leave Bluetooth off at every login. Users can still disable it afterward.
bluedevil_config="${HOME}/.config/bluedevilglobalrc"
if [[ -f "${bluedevil_config}" ]]; then
    sed -i -E '/^[[:xdigit:]:]+_powered=false$/d' "${bluedevil_config}"
fi
if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl power on >/dev/null 2>&1 || true
fi

if command -v xdg-mime >/dev/null 2>&1; then
    while IFS='|' read -r desktop mime; do
        [[ -n "${desktop}" && -n "${mime}" ]] || continue
        xdg-mime default "${desktop}" "${mime}" >/dev/null 2>&1 || true
    done <<'MIMEDEFAULTS'
org.kde.okular.desktop|application/pdf
org.kde.okular.desktop|application/epub+zip
org.kde.gwenview.desktop|image/jpeg
org.kde.gwenview.desktop|image/png
org.kde.gwenview.desktop|image/gif
org.kde.gwenview.desktop|image/webp
org.videolan.VLC.desktop|video/mp4
org.videolan.VLC.desktop|video/x-matroska
org.videolan.VLC.desktop|video/x-msvideo
org.videolan.VLC.desktop|audio/mpeg
org.videolan.VLC.desktop|audio/flac
org.kde.kwrite.desktop|text/plain
org.kde.kwrite.desktop|text/markdown
org.kde.ark.desktop|application/zip
org.kde.ark.desktop|application/x-7z-compressed
org.kde.ark.desktop|application/x-rar
org.kde.ark.desktop|application/x-tar
kyth-exe-handler.desktop|application/x-ms-dos-executable
kyth-exe-handler.desktop|application/x-msdos-program
kyth-exe-handler.desktop|application/x-dosexec
kyth-exe-handler.desktop|application/x-msi
kyth-exe-handler.desktop|application/x-msdownload
kyth-exe-handler.desktop|application/vnd.microsoft.portable-executable
kyth-exe-handler.desktop|application/x-rpm
kyth-exe-handler.desktop|application/x-redhat-package-manager
com.brave.Browser.desktop|x-scheme-handler/http
com.brave.Browser.desktop|x-scheme-handler/https
com.getmailspring.Mailspring.desktop|x-scheme-handler/mailto
org.kde.dolphin.desktop|inode/directory
MIMEDEFAULTS
fi

# Dolphin Places sidebar: seed a comfortable everyday set without depending on
# fragile GUI state. Preserve existing customized places; add missing essentials.
mkdir -p "${HOME}/.local/share"
places_file="${HOME}/.local/share/user-places.xbel"
ensure_place() {
    local href=$1
    local title=$2
    local icon=$3
    grep -Fq "href=\"${href}\"" "${places_file}" 2>/dev/null && return 0
    local tmp_places="${places_file}.kyth-tmp"
    awk -v href="${href}" -v title="${title}" -v icon="${icon}" '
        /<\/xbel>/ && !done {
            print " <bookmark href=\"" href "\">"
            print "  <title>" title "</title>"
            print "  <info><metadata owner=\"http://freedesktop.org\"><bookmark:icon name=\"" icon "\" xmlns:bookmark=\"http://www.freedesktop.org/standards/desktop-bookmarks\"/></metadata></info>"
            print " </bookmark>"
            done=1
        }
        { print }
    ' "${places_file}" > "${tmp_places}" && mv "${tmp_places}" "${places_file}"
}
if [[ ! -f "${places_file}" ]]; then
    cat > "${places_file}" <<PLACESXBELEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xbel>
<xbel version="1.0">
 <bookmark href="file://${HOME}">
  <title>Home</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="user-home" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Desktop">
  <title>Desktop</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="user-desktop" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Documents">
  <title>Documents</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-documents" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Downloads">
  <title>Downloads</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-download" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Games">
  <title>Games</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="applications-games" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Music">
  <title>Music</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-music" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Pictures">
  <title>Pictures</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-pictures" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Screenshots">
  <title>Screenshots</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-pictures" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Public">
  <title>Public</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-publicshare" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Templates">
  <title>Templates</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-templates" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Videos">
  <title>Videos</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-videos" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="trash:/">
  <title>Trash</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="user-trash" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="network:/">
  <title>Network</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="network-workgroup" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
</xbel>
PLACESXBELEOF
fi
ensure_place "file://${HOME}" "Home" "user-home"
ensure_place "file://${HOME}/Desktop" "Desktop" "user-desktop"
ensure_place "file://${HOME}/Documents" "Documents" "folder-documents"
ensure_place "file://${HOME}/Downloads" "Downloads" "folder-download"
ensure_place "file://${HOME}/Games" "Games" "applications-games"
ensure_place "file://${HOME}/Music" "Music" "folder-music"
ensure_place "file://${HOME}/Pictures" "Pictures" "folder-pictures"
ensure_place "file://${HOME}/Screenshots" "Screenshots" "folder-pictures"
ensure_place "file://${HOME}/Public" "Public" "folder-publicshare"
ensure_place "file://${HOME}/Templates" "Templates" "folder-templates"
ensure_place "file://${HOME}/Videos" "Videos" "folder-videos"
ensure_place "trash:/" "Trash" "user-trash"
ensure_place "network:/" "Network" "network-workgroup"

if command -v kwriteconfig6 >/dev/null 2>&1; then
    # Ensure KDE apps (Discover, System Settings, etc.) always display English.
    # KDE's locale stack reads plasma-localerc before falling back to LANG; without
    # an explicit entry some builds pick the first AppStream translation in the XML.
    kwriteconfig6 --file plasma-localerc --group Translations --key LANGUAGE "en_US"
    kwriteconfig6 --file plasma-localerc --group Formats --key LC_TIME "en_US.UTF-8"

    # KWallet should be opened by kwallet-pam with the login password, then stay
    # open for the session so browsers and editors do not ask again after boot.
    kwriteconfig6 --file kwalletrc --group Wallet --key Enabled --type bool true
    kwriteconfig6 --file kwalletrc --group Wallet --key "Default Wallet" kdewallet
    kwriteconfig6 --file kwalletrc --group Wallet --key "Local Wallet" kdewallet
    kwriteconfig6 --file kwalletrc --group Wallet --key "Use One Wallet" --type bool true
    kwriteconfig6 --file kwalletrc --group Wallet --key "Close When Idle" --type bool false
    kwriteconfig6 --file kwalletrc --group Wallet --key "Close on Screensaver" --type bool false
    kwriteconfig6 --file kwalletrc --group Wallet --key "Leave Open" --type bool true

    # KythOS visual identity. New users receive this from /etc/skel; this
    # keeps older or manually-created accounts aligned without repeatedly
    # clobbering a user's custom theme. The System Hub polish button passes
    # --force when the user explicitly asks to re-apply the KythOS look.
    current_color=""
    current_plasma_theme=""
    current_favorites=""
    if command -v kreadconfig6 >/dev/null 2>&1; then
        current_color="$(kreadconfig6 --file kdeglobals --group General --key ColorScheme 2>/dev/null || true)"
        current_plasma_theme="$(kreadconfig6 --file plasmarc --group Theme --key name 2>/dev/null || true)"
        current_favorites="$(kreadconfig6 --file kickoffrc --group Favorites --key FavoriteURLs 2>/dev/null || true)"
    fi
    apply_kyth_visuals=0
    if [[ "${force}" == "1" || ( -z "${current_color}" && -z "${current_plasma_theme}" ) ]]; then
        apply_kyth_visuals=1
    fi
    if [[ "${apply_kyth_visuals}" == "1" ]]; then
        kwriteconfig6 --file kdeglobals --group General --key ColorScheme KythDark
        kwriteconfig6 --file kdeglobals --group General --key font 'Inter,10,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group General --key fixed 'Cascadia Code,10,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group General --key smallestReadableFont 'Inter,8,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group General --key toolBarFont 'Inter,9,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group General --key menuFont 'Inter,10,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group Icons --key Theme Papirus-Dark
        kwriteconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage org.kde.breezedark.desktop
        kwriteconfig6 --file plasmarc --group Theme --key name kyth-dark
        if [[ -r /usr/share/wallpapers/kyth/contents/images/1920x1080.svg ]]; then
            kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc \
                --group Containments --group 1 --group Wallpaper --group org.kde.image --group General \
                --key Image /usr/share/wallpapers/kyth/contents/images/1920x1080.svg
        fi
    fi
    if [[ "${force}" == "1" || -z "${current_favorites}" ]]; then
        kwriteconfig6 --file kickoffrc --group Favorites --key FavoriteURLs \
            'applications:kyth-welcome.desktop,applications:kyth-app-store.desktop,applications:com.valvesoftware.Steam.desktop,applications:com.brave.Browser.desktop,applications:chromium-browser.desktop,applications:dev.vencord.Vesktop.desktop,applications:org.kde.konsole.desktop'
    fi

    # Ctrl+Shift+Esc opens Mission Center when installed, with KDE System
    # Monitor as the always-available fallback.
    if flatpak info io.missioncenter.MissionCenter >/dev/null 2>&1; then
        kwriteconfig6 --file kglobalshortcutsrc \
            --group services --group io.missioncenter.MissionCenter.desktop \
            --key _launch 'Ctrl+Shift+Esc'
        kwriteconfig6 --file kglobalshortcutsrc \
            --group org.kde.plasma-systemmonitor.desktop \
            --key _launch 'none,none,System Monitor'
    else
        kwriteconfig6 --file kglobalshortcutsrc \
            --group org.kde.plasma-systemmonitor.desktop \
            --key _launch 'Ctrl+Shift+Esc,none,System Monitor'
    fi

    # Double-click to open files: predictable across Dolphin, desktop icons, and
    # file dialogs for people arriving from pointer-first desktops.
    kwriteconfig6 --file kdeglobals --group KDE --key SingleClick --type bool false

    # Keep Kickoff categories quiet after first-boot Flatpak/app installs.
    kwriteconfig6 --file kickoffrc \
        --group General \
        --key highlightNewlyInstalledApps \
        --type bool false

    # Clipboard history on Meta+V.
    # Klipper ships enabled but history is off by default; turn it on with a
    # 25-item buffer so paste history stays useful without turning into a log.
    kwriteconfig6 --file klipperrc --group General --key KeepClipboardContents --type bool true
    kwriteconfig6 --file klipperrc --group General --key MaxClipItems 25
    kwriteconfig6 --file kglobalshortcutsrc \
        --group org.kde.klipper.desktop \
        --key show_clipboard_history \
        'Meta+V,Ctrl+Alt+V,Show Clipboard History'

    # Meta+E opens the file manager and Meta+Shift+S starts a rectangular
    # screenshot. The Move From Windows page applies the same migration shortcuts;
    # its "Restore KDE Defaults" button remains the opt-out.
    kwriteconfig6 --file kglobalshortcutsrc \
        --group services --group org.kde.dolphin.desktop \
        --key _launch 'Meta+E'
    kwriteconfig6 --file kglobalshortcutsrc \
        --group org.kde.spectacle.desktop \
        --key RectangularRegionScreenShot \
        'Meta+Shift+S,Meta+Shift+S,Capture Rectangular Region'
    kwriteconfig6 --file spectaclerc --group General --key defaultSaveLocation "file://${HOME}/Screenshots"
    kwriteconfig6 --file spectaclerc --group General --key lastSaveAsLocation "file://${HOME}/Screenshots"
    kwriteconfig6 --file spectaclerc --group General --key useReleaseToCapture --type bool true
    kwriteconfig6 --file spectaclerc --group ImageSave --key translatedScreenshotsFolder "${HOME}/Screenshots"

    # Screen lock: keep the KythOS default calmer than upstream Plasma's stock
    # five-minute lock while still locking on resume.
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock --type bool true
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockGracePeriod 5
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockOnResume --type bool true
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key Timeout 15
    kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.image --group General \
        --key Image /usr/share/wallpapers/kyth/contents/images/1920x1080.svg

    # Alt+Tab window switcher: Thumbnail Grid gives a modern, scannable overview.
    # KWin ships it built in and made it the default in Plasma 6.4, but configs
    # carried over from earlier installs (or kyth's previous "thumbnails" strip
    # override) can still select an older layout — pin the grid explicitly.
    # TabBoxAlternative* sets the same layout for the reverse direction (Alt+Shift+Tab).
    kwriteconfig6 --file kwinrc --group TabBox --key LayoutName thumbnail_grid
    kwriteconfig6 --file kwinrc --group TabBox --key ShowDesktop --type bool false
    kwriteconfig6 --file kwinrc --group TabBoxAlternative --key LayoutName thumbnail_grid

    # Keep upgraded users on the same underscore, box, and X titlebar controls.
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnLeft ""
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnRight IAX
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key library org.kde.breeze
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme Breeze
    qdbus_cmd=""
    for candidate in qdbus6 qdbus-qt6 qdbus; do
        if command -v "${candidate}" >/dev/null 2>&1; then
            qdbus_cmd="${candidate}"
            break
        fi
    done
    if [[ -n "${qdbus_cmd}" ]]; then
        "${qdbus_cmd}" org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
    fi

    # Desktop right-click menu: keep wallpaper/display personalization easy to
    # discover. KDE's default context menu puts display settings behind two clicks.
    kwriteconfig6 --file kwinrc --group Plugins --key desktopchangeosdEnabled --type bool false

    # Mixed refresh rate — compositor latency policy.
    # KWin Plasma 6 renders each output at its own refresh rate independently, but
    # defaults to "medium" latency which can cause visible tearing and flicker when
    # a window is dragged between a 144 Hz and 60 Hz display. "extreme" eliminates
    # the per-frame delay that causes the jitter without increasing CPU usage.
    kwriteconfig6 --file kwinrc --group Compositing --key LatencyPolicy extreme
    # Disable adaptive sync on secondary displays by default to prevent frame-rate
    # lock-step when the primary is in VRR mode and the secondary is fixed-refresh.
    kwriteconfig6 --file kwinrc --group Compositing --key AllowTearing --type bool false

    # KDE Discover update notifications — disabled in favour of kyth-update-notifier.
    # Having two independent "update available" badges (Discover + kyth tray) confuses
    # users who don't know which one covers what. The kyth tray handles both OS image
    # updates and Flatpak app updates; Discover's badge is redundant and contradictory.
    kwriteconfig6 --file plasma-discoverrc --group UpdatesNotifier --key UseNotifications --type bool false

    # Dolphin/File Explorer comfort: remember view properties per folder, keep
    # previews available, and use a visible location bar instead of breadcrumbs
    # for easier path copy/paste during support and migration.
    kwriteconfig6 --file dolphinrc --group General --key RememberOpenedTabs --type bool true
    kwriteconfig6 --file dolphinrc --group General --key ShowFullPath --type bool true
    kwriteconfig6 --file dolphinrc --group General --key UseTabForSplitViewSwitch --type bool true
    kwriteconfig6 --file dolphinrc --group General --key ShowSpaceInfo --type bool true
    kwriteconfig6 --file dolphinrc --group General --key BrowseThroughArchives --type bool true
    kwriteconfig6 --file dolphinrc --group General --key ShowToolTips --type bool true
    kwriteconfig6 --file dolphinrc --group DetailsMode --key PreviewSize 32
    kwriteconfig6 --file dolphinrc --group PreviewSettings --key Plugins \
        'audiothumbnail,comicbookthumbnail,cursorthumbnail,djvuthumbnail,ebookthumbnail,exrthumbnail,ffmpegthumbs,imagethumbnail,jpegthumbnail,kraorathumbnail,windowsexethumbnail'
fi

brave_desktop_src=""
for candidate in \
    /var/lib/flatpak/exports/share/applications/com.brave.Browser.desktop \
    /usr/share/applications/com.brave.Browser.desktop \
    /usr/local/share/applications/com.brave.Browser.desktop; do
    if [[ -f "${candidate}" ]]; then
        brave_desktop_src="${candidate}"
        break
    fi
done

if [[ -n "${brave_desktop_src}" ]]; then
    brave_desktop_dst="${HOME}/.local/share/applications/com.brave.Browser.desktop"
    mkdir -p "$(dirname "${brave_desktop_dst}")"
    cp "${brave_desktop_src}" "${brave_desktop_dst}"
    if ! grep -q -- '--password-store=basic' "${brave_desktop_dst}"; then
        sed -i -E '/^Exec=/ s#(com\.brave\.Browser)( |$)#\1 --password-store=basic\2#' "${brave_desktop_dst}"
        if ! grep -q '^Exec=.*flatpak run ' "${brave_desktop_dst}"; then
            sed -i -E '/^Exec=/ s#(brave-browser|brave)( |$)#\1 --password-store=basic\2#' "${brave_desktop_dst}"
        fi
    fi
fi

if command -v /usr/bin/kyth-set-kickoff-icon >/dev/null 2>&1; then
    /usr/bin/kyth-set-kickoff-icon >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-apply-desktop-layout >/dev/null 2>&1; then
    if [[ "${force}" == "1" ]]; then
        /usr/bin/kyth-apply-desktop-layout --force
    elif [[ "${had_polish_stamp}" == "0" ]]; then
        /usr/bin/kyth-apply-desktop-layout --initial >/dev/null 2>&1 || true
    fi
fi

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-steam-game-export >/dev/null 2>&1; then
    /usr/bin/kyth-steam-game-export >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-web-app-categorize >/dev/null 2>&1; then
    /usr/bin/kyth-web-app-categorize >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-vscode-wallet >/dev/null 2>&1; then
    /usr/bin/kyth-vscode-wallet >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-apply-role-preset >/dev/null 2>&1 \
    && [[ "${force}" == "1" || "${had_polish_stamp}" == "0" ]]; then
    role_profile="everyday"
    if [[ -r "${HOME}/.local/share/kyth/profile" ]]; then
        role_profile="$(head -n 1 "${HOME}/.local/share/kyth/profile" 2>/dev/null || printf 'everyday')"
    fi
    /usr/bin/kyth-apply-role-preset "${role_profile}" >/dev/null 2>&1 || true
fi

if [[ -d "${HOME}/Desktop" && ( "${force}" == "1" || "${had_polish_stamp}" == "0" ) ]] \
    && [[ -f /usr/share/applications/kyth-welcome.desktop ]]; then
    cp /usr/share/applications/kyth-welcome.desktop "${HOME}/Desktop/kyth-welcome.desktop" || true
    chmod 0755 "${HOME}/Desktop/kyth-welcome.desktop" 2>/dev/null || true
fi

# Recycle Bin on the desktop for existing accounts. Seeded once per polish
# version — deleting it afterwards is respected until the next version bump.
if [[ -d "${HOME}/Desktop" && ! -e "${HOME}/Desktop/kyth-recycle-bin.desktop" ]] \
    && [[ -f /usr/share/kyth/kyth-recycle-bin.desktop ]]; then
    cp /usr/share/kyth/kyth-recycle-bin.desktop "${HOME}/Desktop/kyth-recycle-bin.desktop" || true
fi

touch "${stamp}"
rm -f "${old_autostart}" "${HOME}/.config/autostart/kyth-user-polish.desktop" 2>/dev/null || true
POLISHEOF
chmod +x /usr/bin/kyth-user-polish

# Backward-compatible command name used by existing docs, support notes, and
# old smoke-check output. It now runs the same build-integrated polish pass.
cat >/usr/bin/kyth-windows-friendly-defaults <<'WINDEFAULTEOF'
#!/usr/bin/env bash
exec /usr/bin/kyth-user-polish "$@"
WINDEFAULTEOF
chmod +x /usr/bin/kyth-windows-friendly-defaults

cat >/etc/skel/.config/autostart/kyth-user-polish.desktop <<'POLISHDESKTOPEOF'
[Desktop Entry]
Type=Application
Name=KythOS: User Comfort Polish
Exec=/usr/bin/kyth-user-polish
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
POLISHDESKTOPEOF

# Global autostart means existing users receive new polish migrations after an
# OS update too; the version stamp above prevents repeated preference churn.
install -m 0644 /etc/skel/.config/autostart/kyth-user-polish.desktop \
	/etc/xdg/autostart/kyth-user-polish.desktop
