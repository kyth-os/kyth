# Open KDE Autostart settings — manage apps that launch at login.
# Equivalent to Task Manager → Startup tab on Windows.
[group('KythOS')]
startup-apps:
    #!/usr/bin/env bash
    set -euo pipefail
    kcmshell6 autostart 2>/dev/null \
        || systemsettings 2>/dev/null \
        || { echo "Open System Settings → Autostart to manage login apps."; exit 1; }

# Install Microsoft core fonts into ~/.local/share/fonts.
# Fixes font substitution in LibreOffice when opening Word/Excel/PowerPoint files.
# Installs: Times New Roman, Arial, Courier New, Verdana, Georgia, Impact, and more.
# Uses p7zip to extract — no cabextract or rpm-ostree layer required.
[group('KythOS')]
install-ms-fonts:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Microsoft Fonts ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Installing Microsoft core fonts to ~/.local/share/fonts/msttcorefonts"
    echo "  (Times New Roman, Arial, Courier New, Verdana, Georgia, Impact, ...)"
    echo
    fonts_dir="${HOME}/.local/share/fonts/msttcorefonts"
    mkdir -p "${fonts_dir}"
    tmp=$(mktemp -d)
    trap 'rm -rf "${tmp}"' EXIT
    base_url="https://sourceforge.net/projects/corefonts/files/the%20fonts/final"
    fonts=(
        andale32.exe arial32.exe arialb32.exe comic32.exe courie32.exe
        georgi32.exe impact32.exe times32.exe trebuc32.exe verdan32.exe
        webdin32.exe
    )
    ok=0; failed=0
    for font in "${fonts[@]}"; do
        dest="${tmp}/${font}"
        printf "  %-20s " "${font}"
        if curl -fsSL --retry 2 -o "${dest}" "${base_url}/${font}/download" 2>/dev/null; then
            extracted=$(7z e "${dest}" -o"${tmp}/extracted_${font}" '*.ttf' '*.TTF' -r -y \
                2>/dev/null | grep -c "Extracting" || true)
            find "${tmp}/extracted_${font}" \( -name '*.ttf' -o -name '*.TTF' \) \
                -exec cp -n {} "${fonts_dir}/" \; 2>/dev/null || true
            actual=$(find "${tmp}/extracted_${font}" \( -name '*.ttf' -o -name '*.TTF' \) \
                2>/dev/null | wc -l)
            if [[ "${actual}" -gt 0 ]]; then
                echo "✓ (${actual} font(s))"
                ok=$((ok+1))
            else
                echo "skip (no .ttf found)"
                failed=$((failed+1))
            fi
        else
            echo "skip (download failed)"
            failed=$((failed+1))
        fi
    done
    fc-cache -f "${fonts_dir}" 2>/dev/null || true
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [[ "${ok}" -gt 0 ]]; then
        echo "  ✓ Installed fonts from ${ok} package(s). Restart LibreOffice to apply."
        if [[ "${failed}" -gt 0 ]]; then
            echo "  ⚠ ${failed} package(s) skipped."
        fi
    else
        echo "  ✗ No fonts installed. Check your network connection and try again." >&2
        exit 1
    fi

# Set up a printer — enables CUPS and opens KDE Printer Settings.
# Most USB and network printers are detected automatically.
# If your printer is not listed, connect it via USB or use Add Printer → Network.
# For stubborn printers, the CUPS web interface is at http://localhost:631
[group('KythOS')]
setup-printer:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Printer Setup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Enabling CUPS print service..."
    sudo systemctl enable --now cups
    echo "  ✓ CUPS is running."
    echo
    echo "  Opening KDE Printer Settings..."
    echo "  Tip: if your printer is not listed, click Add Printer."
    echo "  For network printers, choose Enter URI and type its IP address."
    echo
    echo "  Advanced: CUPS web interface → http://localhost:631"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kcmshell6 kcm_printer_manager 2>/dev/null \
        || systemsettings 2>/dev/null &

# Check for and apply firmware updates via fwupd.
[group('KythOS')]
firmware-update:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Refreshing firmware metadata..."
    fwupdmgr refresh --force
    echo
    echo "Checking for firmware updates..."
    fwupdmgr get-updates || true
    echo
    echo "Applying available firmware updates..."
    fwupdmgr update
