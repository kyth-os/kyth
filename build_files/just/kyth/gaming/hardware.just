import '../common.just'

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

# Install Vesktop — Discord with native Wayland.
[group('KythOS')]
install-vesktop: (_install-flatpak "dev.vencord.Vesktop" "Vesktop")
