import '../common.just'

# Show matched hardware profiles, capabilities, quirks, and applied state.
[group('KythOS')]
hardware-policy:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-hardware-policy status

# Export stable device identifiers used by the policy matcher.
[group('KythOS')]
hardware-inventory:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-hardware-policy inventory

# Re-evaluate and reapply device-specific policy after hardware changes.
[group('KythOS')]
hardware-policy-apply:
    #!/usr/bin/env bash
    set -euo pipefail
    sudo /usr/bin/kyth-hardware-policy apply --force

# Export Steam Flatpak game shortcuts into the host application menu.
[group('KythOS')]
export-steam-games:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-steam-game-export

# Check controller readiness.
[group('KythOS')]
controller-check:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-controller-check

# Install LACT from Flathub.
[group('KythOS')]
install-lact: (_install-flatpak "io.github.ilya_zlobintsev.LACT" "LACT")
    @echo "If you want overclocking/undervolting on AMD, review the official LACT Atomic guidance first."

# Launch CoreCtrl if available.
[group('KythOS')]
corectrl:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v corectrl >/dev/null 2>&1; then
        echo "CoreCtrl is not installed in this image." >&2; exit 1
    fi
    exec corectrl

# Install CoolerControl — GUI fan curve and thermal management.
[group('KythOS')]
install-coolercontrol:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Installing CoolerControl..."
    sudo rpm-ostree install --idempotent coolercontrol
    echo; echo "Done. Reboot to activate, then: sudo systemctl enable --now coolercontrold"

# Install Piper — GUI for gaming mice configuration.
[group('KythOS')]
install-piper: (_install-flatpak "org.freedesktop.Piper" "Piper")

# Install OpenRGB — unified RGB lighting control.
[group('KythOS')]
install-openrgb: (_install-flatpak "org.openrgb.OpenRGB" "OpenRGB")
    @flatpak override --user --device=all org.openrgb.OpenRGB
    @echo "If RGB RAM or motherboard headers are missing, load i2c kernel modules."

# Install Solaar — GUI for Logitech Unifying/Bolt receivers and mice.
[group('KythOS')]
install-solaar: (_install-flatpak "io.github.pwr_solaar.solaar" "Solaar")

# Install force-feedback wheel drivers (Thrustmaster/Logitech/Fanatec) and
# Oversteer for sim racing. Opt-in and layered at runtime, same tradeoff as
# install-asus-tools below: these are akmod sources from Terra, not baked
# into the base image, so a bad package name here fails one wheel's driver
# without breaking anyone else's build.
[group('KythOS')]
install-racing-wheel-drivers:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Racing Wheel Drivers ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    if command -v lsusb >/dev/null 2>&1; then
        lsusb_out="$(lsusb 2>/dev/null || true)"
        echo "$lsusb_out" | grep -qi '044f' && echo "  Thrustmaster device detected." || true
        echo "$lsusb_out" | grep -qi '046d' && echo "  Logitech device detected." || true
        echo "$lsusb_out" | grep -qi '0eb7' && echo "  Fanatec device detected." || true
        echo
    fi

    echo "  Adding the Terra repo (source: repos.fyralabs.com, same as Bazzite's wheel drivers)…"
    printf '%s\n' \
        '[terra-racing-wheels]' \
        'name=Terra Fyra Labs (racing wheel drivers)' \
        'baseurl=https://repos.fyralabs.com/terra$releasever' \
        'enabled=1' \
        'type=rpm' \
        'repo_gpgcheck=0' \
        'gpgcheck=0' \
        | sudo tee /etc/yum.repos.d/terra-racing-wheels.repo >/dev/null

    installed=()
    failed=()
    for pkg in akmod-hid-tmff2 akmod-new-lg4ff akmod-hid-fanatecff akmod-t150-driver; do
        echo "  → ${pkg}"
        if sudo rpm-ostree install --idempotent --allow-inactive "${pkg}" 2>&1 | tail -n 3; then
            installed+=("${pkg}")
        else
            echo "    not available — skipping"
            failed+=("${pkg}")
        fi
    done

    sudo dnf5 config-manager setopt terra-racing-wheels.enabled=0 2>/dev/null || \
        sudo rm -f /etc/yum.repos.d/terra-racing-wheels.repo

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if ((${#installed[@]} > 0)); then
        echo "  Staged: ${installed[*]}"
        echo "  Reboot for akmods to build the kernel module(s), then reconnect your wheel."
    fi
    if ((${#failed[@]} > 0)); then
        echo "  Not found in Terra right now: ${failed[*]}"
        echo "  Report at: ujust report-issue"
    fi
    echo
    echo "  Configure force feedback with Oversteer:  ujust install-oversteer"

# Install Oversteer — GUI for racing wheel force-feedback and range settings.
[group('KythOS')]
install-oversteer: (_install-flatpak "org.berarma.Oversteer" "Oversteer")

# Install ASUS ROG/TUF Linux control tools (asusctl & supergfxctl).
[group('KythOS')]
install-asus-tools:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Installing ASUS Linux hardware control tools (asusctl & supergfxctl)..."
    sudo dnf5 copr enable -y lukenukem/asus-linux
    sudo rpm-ostree install --idempotent asusctl supergfxctl
    sudo dnf5 copr disable -y lukenukem/asus-linux
    echo
    echo "Reboot required to activate asusd system service."

# Install Vesktop — Discord with native Wayland.
[group('KythOS')]
install-vesktop: (_install-flatpak "dev.vencord.Vesktop" "Vesktop")

# Fix NTFS drive mounts & symlink Proton compatdata for instant Steam game playback.
[group('KythOS')]
fix-ntfs-drives:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-ntfs-repair

