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
    printf '%%wheel ALL=(root) NOPASSWD: /usr/sbin/efibootmgr -n %s, /usr/bin/systemctl reboot\n' \
        "${windows_entry}" | sudo tee /etc/sudoers.d/kyth-boot-windows >/dev/null
    sudo chmod 0440 /etc/sudoers.d/kyth-boot-windows

    echo "boot-windows helper installed."
    echo
    echo "Add it to Steam:"
    echo "  Steam → Add a game → Add a Non-Steam Game → Browse → /usr/local/bin/boot-windows"

# Show dual-boot status and reclaim help — the 30-day "try with Windows" win.
# Keeps Windows boot entry while you evaluate; when ready, reclaim its space.
[group('KythOS')]
dualboot-status:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Dual-Boot Status ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if sudo efibootmgr -v 2>/dev/null | grep -qi "windows"; then
        echo "  Windows EFI entry: found (dual-boot active — safe to keep or reclaim)"
        sudo efibootmgr -v | grep -i windows || true
    else
        echo "  Windows EFI entry: not found (single-boot)"
    fi
    echo
    echo "  Space: use System Hub → Gaming Migration to copy files, then"
    echo "         'just reclaim-windows' when you're ready to grow KythOS."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Reclaim Windows space after 30-day try — guided, needs confirmation.
[group('KythOS')]
reclaim-windows:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ Reclaim Windows Space — guided —━━━"
    echo "  This will list the Windows NTFS partitions for removal."
    echo "  You must confirm with 'yes' to proceed. No data is touched until you confirm."
    sudo lsblk -o NAME,FSTYPE,LABEL,SIZE,MOUNTPOINT | grep -i ntfs || echo "  No NTFS partitions found."
    echo
    read -p "  Type 'yes' to open System Hub → Disks to reclaim (or 'no' to cancel): " ans
    if [[ "$ans" == "yes" ]]; then
        echo "  Opening System Hub — use Disks to delete the Windows partition and grow KythOS."
        nohup /usr/bin/kyth-welcome-launch --page "This PC" >/dev/null 2>&1 &
    else
        echo "  Cancelled — your Windows install is untouched. Run 'just dualboot-status' anytime."
    fi

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
