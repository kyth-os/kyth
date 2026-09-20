import '../common.just'

# Install and configure Waydroid for Android app support.
[group('KythOS')]
setup-waydroid:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ Waydroid Setup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if ! command -v waydroid >/dev/null 2>&1; then
        echo "Waydroid is not installed. Install it first via rpm-ostree." >&2; exit 1
    fi
    if ! systemctl --user is-enabled waydroid-container.service 2>/dev/null | grep -q 'enabled'; then
        systemctl --user enable --now waydroid-container.service
    fi
    if [[ ! -f /var/lib/waydroid/images/system.img ]]; then
        echo "Initializing Waydroid (this downloads ~2 GB of Android images)..."
        sudo waydroid init -s GAPPS
    fi
    echo; echo "Waydroid is ready. Launch with: waydroid show-full-ui"
    echo "For app support: waydroid shell, then install APKs via adb or drag-and-drop."

# Remove Waydroid and its data.
[group('KythOS')]
remove-waydroid:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ Removing Waydroid ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "This permanently deletes all Waydroid data — installed Android apps,"
    echo "their storage, and settings:"
    echo "  /var/lib/waydroid"
    echo "  ${HOME}/.local/share/waydroid"
    echo "  ${HOME}/.waydroid"
    echo
    # Headless callers (Hub jobs) have no TTY: read gets EOF, the answer is
    # never "y". Fail loudly and point at the confirmed variant instead of
    # reporting "Aborted" as success.
    if [[ ! -t 0 ]]; then
        echo "Aborted: removal needs confirmation; use remove-waydroid-confirmed." >&2
        exit 2
    fi
    read -rp "Continue? [y/N] " reply
    if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
        echo "Aborted. No changes made."
        exit 1
    fi
    systemctl --user stop waydroid-container.service 2>/dev/null || true
    systemctl --user disable waydroid-container.service 2>/dev/null || true
    sudo waydroid container stop 2>/dev/null || true
    sudo waydroid session stop 2>/dev/null || true
    sudo rm -rf /var/lib/waydroid
    rm -rf "${HOME}/.local/share/waydroid" "${HOME}/.waydroid" 2>/dev/null || true
    echo "Waydroid data removed. To fully uninstall: sudo rpm-ostree uninstall waydroid"

# Confirmed Waydroid removal for the Hub (no TTY there). Hub-only: the Hub
# shows its own confirm dialog first. Same destructive body as
# remove-waydroid minus the prompt.
[group('KythOS')]
remove-waydroid-confirmed:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ Removing Waydroid (confirmed) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    systemctl --user stop waydroid-container.service 2>/dev/null || true
    systemctl --user disable waydroid-container.service 2>/dev/null || true
    sudo waydroid container stop 2>/dev/null || true
    sudo waydroid session stop 2>/dev/null || true
    sudo rm -rf /var/lib/waydroid
    rm -rf "${HOME}/.local/share/waydroid" "${HOME}/.waydroid" 2>/dev/null || true
    echo "Waydroid data removed. To fully uninstall: sudo rpm-ostree uninstall waydroid"
