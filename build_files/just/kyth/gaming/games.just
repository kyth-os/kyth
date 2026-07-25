import '../common.just'

# Open the Lutris one-click installer for Battle.net.
[group('KythOS')]
install-battlenet:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v lutris >/dev/null 2>&1; then
        echo "Lutris is not installed on this system." >&2
        exit 1
    fi
    nohup lutris "lutris:install/battlenet" >/dev/null 2>&1 &
    echo
    echo "Opened the Battle.net installer in Lutris."

# Open the Lutris one-click installer for the Epic Games Launcher.
[group('KythOS')]
install-epic-launcher:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v lutris >/dev/null 2>&1; then
        echo "Lutris is not installed on this system." >&2
        exit 1
    fi
    prefix="$HOME/Games/epic-games-store"
    cache="$HOME/.cache/lutris/installer/epic-games-store"
    timestamp="$(date +%Y%m%d-%H%M%S)"
    for path in "$prefix" "$cache"; do
        if [[ -e "$path" ]]; then
            backup="${path}.bak-${timestamp}"
            mv "$path" "$backup"
            echo "Moved previous Epic installer state to: $backup"
        fi
    done
    nohup lutris "lutris:install/epic-games-store" >/dev/null 2>&1 &
    echo
    echo "Opened the Epic Games Launcher installer in Lutris."

# Open the Lutris one-click installer for the EA App.
[group('KythOS')]
install-ea-app:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v lutris >/dev/null 2>&1; then
        echo "Lutris is not installed on this system." >&2
        exit 1
    fi
    nohup lutris "lutris:ea-app-standard" >/dev/null 2>&1 &
    echo
    echo "Opened the EA App installer in Lutris."

# Open the Lutris one-click installer for Ubisoft Connect.
[group('KythOS')]
install-ubisoft-connect:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v lutris >/dev/null 2>&1; then
        echo "Lutris is not installed on this system." >&2
        exit 1
    fi
    nohup lutris "lutris:ubisoft-connect-latest" >/dev/null 2>&1 &
    echo
    echo "Opened the Ubisoft Connect installer in Lutris."

# Install Steam.
[group('KythOS')]
install-steam: (_install-flatpak "com.valvesoftware.Steam" "Steam")

# Install Lutris.
[group('KythOS')]
install-lutris: (_install-flatpak "net.lutris.Lutris" "Lutris")

# Install Heroic Games Launcher.
[group('KythOS')]
install-heroic: (_install-flatpak "com.heroicgameslauncher.hgl" "Heroic")

# Install Bottles.
[group('KythOS')]
install-bottles: (_install-flatpak "com.usebottles.bottles" "Bottles")

# Install Prism Launcher — Minecraft.
[group('KythOS')]
install-prismlauncher: (_install-flatpak "org.prismlauncher.PrismLauncher" "Prism Launcher")

# Install Itch.io desktop app.
[group('KythOS')]
install-itch: (_install-flatpak "io.itch.itch" "Itch.io")

# Install RetroArch.
[group('KythOS')]
install-retroarch: (_install-flatpak "org.libretro.RetroArch" "RetroArch")

# Install Ludusavi — backup and restore game saves.
[group('KythOS')]
install-ludusavi: (_install-flatpak "com.github.mtkennerly.ludusavi" "Ludusavi")
