# Upgrade the OS and Flatpak apps.
# Pulls the latest KythOS image via bootc and updates all Flatpak apps.

# The OS update is staged — a reboot is required to activate it.
[group('KythOS')]
kyth-upgrade:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "━━━ KythOS upgrade ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    # ── Check for rpm-ostree layers ───────────────────────────────────────────
    # bootc upgrade fails if any packages have been layered via rpm-ostree.
    # Detect this upfront and give a clear fix rather than a cryptic error.
    # requested-packages covers repo-layered packages (e.g. 'rpm-ostree install
    # waydroid' from ujust setup-waydroid); requested-local-packages covers
    # local RPM files; layered-commit-packages covers commit-layered ones.
    layered=$(rpm-ostree status --json 2>/dev/null \
        | python3 -c "import sys,json; d=json.load(sys.stdin).get('deployments', [{}])[0]; pkgs=d.get('requested-packages', []) + d.get('requested-local-packages', []) + d.get('layered-commit-packages', []); print(' '.join(pkgs) if pkgs else '')" 2>/dev/null || true)

    if [[ -n "${layered}" ]]; then
        echo "  ERROR: rpm-ostree packages are layered:" >&2
        echo "    ${layered}" >&2
        echo >&2
        echo "  These conflict with bootc upgrades. To fix:" >&2
        echo "    rpm-ostree reset     # removes all layered packages" >&2
        echo "    ujust kyth-upgrade   # then retry" >&2
        echo >&2
        if [[ " ${layered} " == *" waydroid "* ]]; then
            echo "  NOTE: 'waydroid' was layered by 'ujust setup-waydroid'." >&2
            echo "  'rpm-ostree reset' removes the Waydroid package (your Android" >&2
            echo "  data in /var/lib/waydroid is kept). After the OS update, rerun" >&2
            echo "  'ujust setup-waydroid' to layer it again." >&2
        else
            echo "  If you still need those packages, install them via Flatpak instead." >&2
        fi
        exit 1
    fi

    # ── OS update via bootc ───────────────────────────────────────────────────
    echo "── OS (bootc) ──────────────────────────────────────────────────────"
    booted_digest=$(bootc status --format json 2>/dev/null \
        | python3 -c "import sys,json; s=json.load(sys.stdin); \
          print(s.get('status',{}).get('booted',{}).get('image',{}) \
                 .get('imageDigest','unknown'))" 2>/dev/null || echo "unknown")

    sudo bootc upgrade

    staged_digest=$(bootc status --format json 2>/dev/null \
        | python3 -c "import sys,json; s=json.load(sys.stdin); \
          print(s.get('status',{}).get('staged',{}).get('image',{}) \
                 .get('imageDigest','') or '')" 2>/dev/null || echo "")

    if [[ -n "${staged_digest}" && "${staged_digest}" != "${booted_digest}" ]]; then
        os_updated=1
        echo "  ✓ New image staged and ready."
    else
        os_updated=0
        echo "  ✓ Already up to date."
    fi
    echo

    # ── Flatpak updates ───────────────────────────────────────────────────────
    echo "── Flatpak apps ────────────────────────────────────────────────────"
    if command -v flatpak >/dev/null 2>&1; then
        flatpak update -y
    else
        echo "  flatpak not available — skipping."
    fi
    echo

    # ── Summary ───────────────────────────────────────────────────────────────
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [[ "${os_updated}" -eq 1 ]]; then
        echo "  OS update staged. Reboot when ready to apply it:"
        echo "    systemctl reboot"
    else
        echo "  Everything is up to date."
    fi

# Show the currently booted image, any staged update, and rollback availability.
[group('KythOS')]
status:
    #!/usr/bin/env bash
    set -euo pipefail
    bootc status

# Rebase to a different KythOS image.
# Usage:
#   ujust rebase kyth:stable
#   ujust rebase kyth:testing
#   ujust rebase kyth:latest
#   ujust rebase                   (defaults to kyth:latest)
#
# Short form "kyth:<tag>" is expanded to ghcr.io/mrtrick37/kyth:<tag>.
# A full image reference (containing '/') is used as-is.

[group('KythOS')]
rebase image_ref="kyth:latest":
    #!/usr/bin/env bash
    set -euo pipefail
    ref="{{ image_ref }}"
    # Expand short form: "kyth:tag" or "kyth" → "ghcr.io/mrtrick37/kyth:tag"
    if [[ "$ref" != *"/"* ]]; then
        ref="ghcr.io/mrtrick37/${ref}"
    fi
    # Default to :latest if no tag was given
    if [[ "$ref" != *":"* ]]; then
        ref="${ref}:latest"
    fi
    echo "Rebasing to: ${ref}"
    echo "This will take effect on next reboot."
    sudo bootc switch "${ref}"

# Switch to a KythOS release channel.
# Channels:
#   stable   — :latest tag (main branch, recommended)
#   testing  — :testing tag (dev branch, may be unstable)
# Usage:
#   ujust switch-channel           (defaults to stable)

# ujust switch-channel testing
[group('KythOS')]
switch-channel channel="stable":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{ channel }}" in
        stable|latest) base_tag="latest" ;;
        testing)       base_tag="testing" ;;
        *)
            echo "Unknown channel: {{ channel }}" >&2
            echo "Valid channels: stable (default), testing" >&2
            exit 1
            ;;
    esac
    flavor="$(cat /usr/share/kyth/kernel-flavor 2>/dev/null || echo fedora)"
    case "${flavor}" in
        cachy) suffix="-cachy" ;;
        *) suffix="" ;;
    esac
    tag="${base_tag}${suffix}"
    echo "Switching to KythOS :${tag}..."
    sudo bootc switch "ghcr.io/mrtrick37/kyth:${tag}"
    echo "Channel switch staged. Reboot to activate."

# Switch to a kernel-flavored KythOS image.
# Default Fedora is recommended. CachyOS is an advanced variant that keeps
# rollback support by switching the whole bootc image instead of layering kernels.
# Usage:
#   ujust switch-kernel fedora
# ujust switch-kernel cachy
[group('KythOS')]
switch-kernel flavor="fedora":
    #!/usr/bin/env bash
    set -euo pipefail

    flavor="$(printf '%s' "{{ flavor }}" | tr '[:upper:]' '[:lower:]')"
    case "${flavor}" in
        fedora|stock) suffix="" ; label="Fedora" ;;
        cachy|cachyos) suffix="-cachy" ; label="CachyOS" ;;
        *)
            echo "Unknown kernel flavor: {{ flavor }}" >&2
            echo "Valid flavors: fedora, cachy" >&2
            exit 1
            ;;
    esac

    status_text="$(sudo -n bootc status 2>/dev/null || bootc status 2>/dev/null || true)"
    current_ref="$(awk '/Booted image:/ {print $NF; exit}' <<<"${status_text}")"
    current_tag=""
    if [[ "${current_ref}" == ghcr.io/mrtrick37/kyth:* ]]; then
        current_tag="${current_ref##*:}"
        current_tag="${current_tag%%@*}"
    fi
    current_tag="${current_tag:-latest}"
    case "${current_tag}" in
        testing*) channel="testing" ;;
        *) channel="latest" ;;
    esac
    if [[ "${suffix}" == "-cachy" ]]; then
        channel="testing"
    fi

    target="ghcr.io/mrtrick37/kyth:${channel}${suffix}"
    echo "Switching to ${label} kernel image: ${target}"
    echo "This stages a new deployment and keeps rollback available from the boot menu."
    if ! output="$(sudo bootc switch "${target}" 2>&1)"; then
        printf '%s\n' "${output}" >&2
        if grep -qi 'manifest unknown' <<<"${output}"; then
            echo "ERROR: ${target} is not published yet." >&2
        else
            echo "ERROR: unable to switch to ${target}." >&2
        fi
        if [[ "${channel}" == "latest" && "${suffix}" == "-cachy" ]]; then
            echo "The CachyOS kernel image may only be available on the testing channel until the stable build publishes :latest-cachy." >&2
            echo "Try: ujust switch-channel testing" >&2
            echo "Then reboot and run: ujust switch-kernel cachy" >&2
        else
            echo "Try again after the image build finishes, or check your network connection." >&2
        fi
        exit 1
    fi
    printf '%s\n' "${output}"
    echo "Kernel switch staged. Reboot to activate."

# Print a short KythOS system/kernel tuning summary.
[group('KythOS')]
kerver:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-kerver

# Print a paste-friendly system support snapshot.
[group('KythOS')]
device-info:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-device-info

# Run the daily-driver readiness smoke check.
[group('KythOS')]
smoke-check *args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-smoke-check {{ args }}

# Run the once-per-deployment post-update confidence check now.
[group('KythOS')]
post-update-check *args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-post-update-check --force {{ args }}

# Check common suspend/resume regressions: network, audio, Bluetooth, display, Vulkan.
[group('KythOS')]
resume-check:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-resume-check

# Add a 'Boot Windows' entry to Steam as a non-Steam game.
# Clicking it from within Steam reboots directly into Windows via EFI firmware.
# Requires a dual-boot setup with Windows on a separate EFI entry.
[group('KythOS')]
setup-boot-windows-steam:
    #!/usr/bin/env bash
    set -euo pipefail

    # Find the Windows EFI boot entry
    windows_entry=$(sudo efibootmgr -v 2>/dev/null \
        | grep -i "windows\|Windows Boot Manager" \
        | grep -oP '(?<=Boot)[0-9A-F]{4}' | head -n1)

    if [[ -z "${windows_entry}" ]]; then
        echo "ERROR: No Windows EFI boot entry found." >&2
        echo "Run 'sudo efibootmgr -v' to list available entries." >&2
        exit 1
    fi

    # Install the helper script
    tmpscript=$(mktemp)
    printf '#!/bin/bash\nexec sudo efibootmgr -n %s && sudo systemctl reboot\n' \
        "${windows_entry}" > "${tmpscript}"
    sudo install -Dm 0755 "${tmpscript}" /usr/local/bin/boot-windows
    rm -f "${tmpscript}"

    # Add sudo rule for boot-windows (passwordless reboot + efibootmgr)
    printf '%%wheel ALL=(root) NOPASSWD: /usr/sbin/efibootmgr -n *, /usr/bin/systemctl reboot\n' \
        | sudo tee /etc/sudoers.d/kyth-boot-windows >/dev/null
    sudo chmod 0440 /etc/sudoers.d/kyth-boot-windows

    echo "boot-windows helper installed."
    echo
    echo "Add it to Steam:"
    echo "  Steam → Add a game → Add a Non-Steam Game → Browse → /usr/local/bin/boot-windows"

# Show the current KythOS Secure Boot enrollment state.
#
# This is safe to run any time. It does not change firmware settings.
[group('KythOS')]
secureboot-status:
    #!/usr/bin/env bash
    set -euo pipefail

    CERT_PEM="/usr/share/kyth/secureboot/kyth-secureboot.cer"
    CERT_DER="/usr/share/kyth/secureboot/kyth-secureboot.der"
    FLAG="/var/lib/kyth/mok-enrolled"

    echo "━━━ KythOS Secure Boot Status ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    if [[ -f "${CERT_DER}" ]]; then
        echo "  Certificate: present at ${CERT_DER}"
    elif [[ -f "${CERT_PEM}" ]]; then
        echo "  Certificate: present as PEM at ${CERT_PEM}"
    else
        echo "  Certificate: missing — this image was built without Secure Boot support"
    fi

    if mokutil --sb-state 2>/dev/null; then
        :
    else
        echo "  Firmware state: unavailable — boot this system in UEFI mode to use MOK enrollment"
    fi

    if mokutil --list-enrolled 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS MOK: enrolled"
    else
        echo "  KythOS MOK: not enrolled"
    fi

    if mokutil --list-new 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  Pending enrollment: staged for next reboot"
    else
        echo "  Pending enrollment: none detected"
    fi

    if [[ -f "${FLAG}" ]]; then
        echo "  First-boot service marker: ${FLAG}"
    else
        echo "  First-boot service marker: not set"
    fi

# Manually enroll the KythOS Secure Boot key (MOK) into UEFI firmware.
#
# The default Fedora kernel path does not need this key. Run this before
# enabling Secure Boot for the advanced CachyOS kernel image, or after a
# firmware reset if the KythOS MOK was removed.
#
# After running, reboot and enter the password you chose at the MokManager screen.
[group('KythOS')]
enroll-secureboot:
    #!/usr/bin/env bash
    set -euo pipefail

    CERT_PEM="/usr/share/kyth/secureboot/kyth-secureboot.cer"
    CERT_DER="/usr/share/kyth/secureboot/kyth-secureboot.der"

    if [[ ! -f "${CERT_PEM}" && ! -f "${CERT_DER}" ]]; then
        echo "KythOS Secure Boot certificate not found." >&2
        echo "This image was built without Secure Boot support." >&2
        exit 1
    fi

    if [[ ! -f "${CERT_DER}" ]]; then
        CERT_DER="$(mktemp --tmpdir kyth-secureboot.XXXXXX.der)"
        openssl x509 -in "${CERT_PEM}" -outform DER -out "${CERT_DER}"
    fi

    echo "━━━ KythOS Secure Boot Enrollment ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    SB_STATE="$(mokutil --sb-state 2>/dev/null || true)"
    if echo "${SB_STATE}" | grep -q "SecureBoot enabled"; then
        echo "  Secure Boot is currently enabled."
    else
        echo "  Secure Boot is currently disabled or unavailable."
        echo "  That is OK — for existing installs, staging the key before enabling"
        echo "  Secure Boot is the safest path."
    fi
    echo

    if mokutil --list-enrolled 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS Secure Boot key is already enrolled. Nothing to do."
        exit 0
    fi

    if mokutil --list-new 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS Secure Boot key is already staged for enrollment."
        echo "  Reboot, complete the blue MokManager prompt, then enable Secure Boot"
        echo "  in firmware if it is not enabled already."
        exit 0
    fi

    echo "  Enrolling KythOS Secure Boot certificate."
    echo "  Choose a one-time confirmation password — you will enter it at the"
    echo "  MokManager screen on next reboot to complete enrollment."
    echo
    read -rsp "  Enrollment password: " MOK_PASS
    echo
    read -rsp "  Confirm password:    " MOK_PASS2
    echo
    if [[ "${MOK_PASS}" != "${MOK_PASS2}" ]]; then
        echo "  Passwords do not match." >&2
        exit 1
    fi

    echo "${MOK_PASS}" | sudo mokutil --import "${CERT_DER}" --stdin-passwd

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  MOK enrollment staged."
    echo "  Next steps:"
    echo "    1. Reboot."
    echo "    2. At the blue MokManager screen, choose Enroll MOK / Continue / Yes."
    echo "    3. Enter the password you just chose, then reboot."
    echo "    4. Enable Secure Boot in UEFI/BIOS if it is not enabled already."
    echo "    5. Boot KythOS and run: ujust secureboot-status"

# Fix the clock skew between KythOS and a dual-booted Windows install.
#
# Windows stores the hardware clock as local time; Linux stores it as UTC.
# After booting KythOS, Windows sees the RTC in UTC and shows the wrong time.
# This tells KythOS to treat the RTC as local time — matching Windows' expectation.
# NTP sync continues working normally; only the RTC interpretation changes.
# Run once. No reboot required.
[group('KythOS')]
fix-dualboot-clock:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Dual-Boot Clock Fix ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Setting hardware clock to local time (Windows-compatible mode)..."
    sudo timedatectl set-local-rtc 1 --adjust-system-clock
    echo
    timedatectl | grep -E "Local time|RTC time|RTC in local TZ|NTP"
    echo
    echo "  ✓ Done. Windows will now show the correct time after booting from KythOS."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

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
