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
    # Pinned SHA256 per font package (SourceForge corefonts, "final").
    # A hash mismatch skips that font rather than installing unverified bytes.
    declare -A font_sha256=(
        [andale32.exe]="0524fe42951adc3a7eb870e32f0920313c71f170c859b5f770d82b4ee111e970"
        [arial32.exe]="85297a4d146e9c87ac6f74822734bdee5f4b2a722d7eaa584b7f2cbf76f478f6"
        [arialb32.exe]="a425f0ffb6a1a5ede5b979ed6177f4f4f4fdef6ae7c302a7b7720ef332fec0a8"
        [comic32.exe]="9c6df3feefde26d4e41d4a4fe5db2a89f9123a772594d7f59afd062625cd204e"
        [courie32.exe]="bb511d861655dde879ae552eb86b134d6fae67cb58502e6ff73ec5d9151f3384"
        [georgi32.exe]="2c2c7dcda6606ea5cf08918fb7cd3f3359e9e84338dc690013f20cd42e930301"
        [impact32.exe]="6061ef3b7401d9642f5dfdb5f2b376aa14663f6275e60a51207ad4facf2fccfb"
        [times32.exe]="db56595ec6ef5d3de5c24994f001f03b2a13e37cee27bc25c58f6f43e8f807ab"
        [trebuc32.exe]="5a690d9bb8510be1b8b4fe49f1f2319651fe51bbe54775ddddd8ef0bd07fdac9"
        [verdan32.exe]="c1cb61255e363166794e47664e2f21af8e3a26cb6346eb8d2ae2fa85dd5aad96"
        [webdin32.exe]="64595b5abc1080fba8610c5c34fab5863408e806aafe84653ca8575bed17d75a"
    )
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
            want="${font_sha256[${font}]}"
            got="$(sha256sum "${dest}" | cut -d' ' -f1)"
            if [[ "${got}" != "${want}" ]]; then
                echo "skip (SHA256 mismatch; refusing unverified font)"
                failed=$((failed+1))
                continue
            fi
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
# Network printers (driverless IPP Everywhere over Avahi) are detected
# automatically. USB printers are NOT supported in this image: ipp-usb and
# sane-airscan (packages + units) do not ship, so a USB-connected printer
# will not appear no matter which setup UI is opened.
# For stubborn network printers, the CUPS web interface is at http://localhost:631
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
    echo "  Tip: network (IPP Everywhere) printers are found automatically —"
    echo "  if yours is not listed, click Add Printer and enter its IP address."
    echo "  Note: USB printers are not supported (ipp-usb is not installed)."
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

# Windows verify — parity + PWA check
[group('KythOS')]
windows-verify:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-windows-verify
