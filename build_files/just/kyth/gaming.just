# Export Steam Flatpak game shortcuts into the host application menu.
[group('KythOS')]
export-steam-games:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-steam-game-export

# Check controller readiness for Steam Input, Bluetooth, and remapping paths.
[group('KythOS')]
controller-check:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-controller-check

# Install LACT from Flathub on an immutable system.
[group('KythOS')]
install-lact: (_install-flatpak "io.github.ilya_zlobintsev.LACT" "LACT")
    @echo "If you want overclocking/undervolting on AMD, review the official LACT Atomic guidance first."

# Install GPU Screen Recorder from Flathub — near-zero overhead capture and instant replay
# using AMD/NVIDIA GPU hardware encoding. Select the GPU Screen Recorder UI or Tray from
# the app menu; configure a replay buffer key in preferences for ShadowPlay-style highlights.
[group('KythOS')]
install-gpu-screen-recorder: (_install-flatpak "com.dec05eba.gpu_screen_recorder" "GPU Screen Recorder")

# Install Vesktop from Flathub — Discord with native Wayland, better screenshare, and Vencord.
[group('KythOS')]
install-vesktop: (_install-flatpak "dev.vencord.Vesktop" "Vesktop")

# Install GOverlay from Flathub for MangoHud and vkBasalt configuration.
[group('KythOS')]
install-goverlay: (_install-flatpak "io.github.benjamimgois.goverlay" "GOverlay")

# Install MangoJuice from Flathub for lightweight MangoHud configuration.
[group('KythOS')]
install-mangojuice: (_install-flatpak "io.github.radiolamp.mangojuice" "MangoJuice")

# Launch CoreCtrl if the image includes it.
[group('KythOS')]
corectrl:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v corectrl >/dev/null 2>&1; then
        echo "CoreCtrl is not installed in this image." >&2
        echo "If Fedora packaging skipped it during build, use LACT instead: ujust install-lact" >&2
        exit 1
    fi
    exec corectrl

# Download and install the latest Proton-CachyOS to /var/lib/kyth/proton-cachyos/.
[group('KythOS')]
update-proton-cachyos:
    #!/usr/bin/env bash
    set -euo pipefail
    sudo /usr/bin/kyth-proton-cachyos-update

# Install Steam — Valve's gaming platform with Proton for Windows games.
[group('KythOS')]
install-steam:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub com.valvesoftware.Steam
    echo
    echo "Steam installed. Launch it from the app menu."

# Install Lutris — open gaming platform for Battle.net, EA App, Ubisoft Connect, and more.
[group('KythOS')]
install-lutris:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub net.lutris.Lutris
    echo
    echo "Lutris installed. Launch it from the app menu."

# Install Heroic Games Launcher — Epic Games, GOG and Amazon Games library.
[group('KythOS')]
install-heroic:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub com.heroicgameslauncher.hgl
    echo
    echo "Heroic installed. Launch it from the app menu."

# Install or reinstall umu-launcher (umu-run) from the latest GitHub release.
# Run this if Lutris says "Install umu to use Proton".
[group('KythOS')]
install-umu:
    #!/usr/bin/env bash
    set -euo pipefail
    UMU_REPO_API="https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest"
    TMPDIR_UMU=$(mktemp -d)
    trap 'rm -rf "${TMPDIR_UMU}"' EXIT
    release_json="${TMPDIR_UMU}/release.json"
    echo "Fetching latest umu-launcher release info…"
    curl -fsSL "${UMU_REPO_API}" -o "${release_json}"
    UMU_URL=$(
        grep -oP 'https://[^"]+/releases/download/[^"]+umu-launcher-[^"]+-zipapp\.tar' "${release_json}" \
        | head -n1
    ) || true
    if [[ -z "${UMU_URL}" ]]; then
        UMU_URL=$(
            grep -oP 'https://[^"]+/releases/download/[^"]+\.tar(\.(gz|zst))?' "${release_json}" \
            | grep -iv 'source\|src' \
            | head -n1
        ) || true
    fi
    if [[ -z "${UMU_URL}" ]]; then
        echo "Could not find an installable release tarball. Check https://github.com/Open-Wine-Components/umu-launcher/releases" >&2
        exit 1
    fi
    UMU_TARBALL=$(basename "${UMU_URL}")
    echo "Downloading ${UMU_TARBALL}…"
    curl -fsSL "${UMU_URL}" -o "${TMPDIR_UMU}/${UMU_TARBALL}"
    tar -xf "${TMPDIR_UMU}/${UMU_TARBALL}" -C "${TMPDIR_UMU}/"
    UMU_BIN=$(find "${TMPDIR_UMU}" -name 'umu-run' -type f | head -n1)
    if [[ -z "${UMU_BIN}" ]]; then
        echo "umu-run binary not found in archive." >&2
        exit 1
    fi
    sudo install -m 0755 "${UMU_BIN}" /usr/local/bin/umu-run
    UMU_PKGDIR=$(find "${TMPDIR_UMU}" -maxdepth 3 -name 'umu' -type d | grep -v '__pycache__' | head -n1)
    if [[ "${UMU_TARBALL}" != *-zipapp.tar && -n "${UMU_PKGDIR}" ]]; then
        PY_SITEPKG=$(python3 -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
        sudo mkdir -p "${PY_SITEPKG}"
        sudo cp -r "${UMU_PKGDIR}" "${PY_SITEPKG}/"
    fi
    echo "umu-launcher installed: $(umu-run --version 2>/dev/null || echo 'ok')"

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

# Install Prism Launcher — Minecraft with modpacks and multiple instances.
[group('KythOS')]
install-prismlauncher:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub org.prismlauncher.PrismLauncher
    echo
    echo "Prism Launcher installed. Launch it from the app menu."

# Install Bottles — easiest GUI for running standalone Windows .exe/.msi apps.
[group('KythOS')]
install-bottles:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub com.usebottles.bottles
    echo
    echo "Bottles installed. Launch it from the app menu to open .exe or .msi files."

# Install Ludusavi — backup and restore game saves across launchers.
[group('KythOS')]
install-ludusavi:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub com.github.mtkennerly.ludusavi
    echo
    echo "Ludusavi installed. Launch it from the app menu before migrating or modding games."

# Toggle FSR4 upscaling globally for all Steam/Proton games.
# Writes PROTON_FSR4_UPGRADE=1 to ~/.config/environment.d/ so every game
# launched through Steam inherits it. Run again to remove the override.
# Requires RDNA3+ (RX 7000 series) for native FSR4; on RDNA2 it falls back
# to FSR3.1.
[group('KythOS')]
toggle-fsr4:
    #!/usr/bin/env bash
    set -euo pipefail
    conf="${HOME}/.config/environment.d/99-kyth-fsr4.conf"
    mkdir -p "${HOME}/.config/environment.d"
    if [[ -f "${conf}" ]]; then
        rm -f "${conf}"
        echo "FSR4 global override removed. Restart Steam to apply."
    else
        printf 'PROTON_FSR4_UPGRADE=1\n' > "${conf}"
        echo "FSR4 global override enabled — applies to all Steam/Proton games on next launch."
        echo "Run again to disable."
    fi

# Toggle DLSS/NVAPI globally for all Steam/Proton games.
# Writes PROTON_ENABLE_NVAPI=1 + DXVK_ENABLE_NVAPI=1 to environment.d so
# every game inherits NVAPI (required for DLSS on NVIDIA, and for DLSS-to-FSR
# translation via OptiScaler on AMD/Intel). Run again to remove.
[group('KythOS')]
toggle-nvapi:
    #!/usr/bin/env bash
    set -euo pipefail
    conf="${HOME}/.config/environment.d/99-kyth-nvapi.conf"
    mkdir -p "${HOME}/.config/environment.d"
    if [[ -f "${conf}" ]]; then
        rm -f "${conf}"
        echo "NVAPI global override removed. Restart Steam to apply."
    else
        printf 'PROTON_ENABLE_NVAPI=1\nDXVK_ENABLE_NVAPI=1\n' > "${conf}"
        echo "NVAPI global override enabled — DLSS and NVIDIA Reflex will work in all Steam games."
        echo "Run again to disable."
    fi

# Install lsfg-vk (Lossless Scaling Frame Generation for Vulkan) — software
# frame interpolation as a Vulkan implicit layer. Works with any game regardless
# of engine, doubling the rendered frame count from the GPU's perspective.
# Different from OptiScaler (which replaces DLSS/XeSS with FSR) — lsfg-vk works
# on top of any renderer output without per-game deployment.
#
# After install, enable per-game via Steam launch options:
# ENABLE_LSFG=1 %command%
[group('KythOS')]
install-lsfg-vk:
    #!/usr/bin/env bash
    set -euo pipefail

    LSFG_REPO="https://api.github.com/repos/Juniorkl/lsfg-vk/releases/latest"
    INSTALL_DIR="${HOME}/.local/lib"
    LAYER_JSON_DIR="${HOME}/.local/share/vulkan/implicit_layer.d"

    echo "Fetching latest lsfg-vk release..."
    release_json=$(curl -fsSL "${LSFG_REPO}")
    tarball_url=$(printf '%s' "${release_json}" \
        | python3 -c "import sys,json; data=json.load(sys.stdin); \
          print(next(a['browser_download_url'] for a in data['assets'] \
          if a['name'].endswith('.tar.gz')))")

    tarball_name="${tarball_url##*/}"
    tmpdir=$(mktemp -d)
    trap 'rm -rf "${tmpdir}"' EXIT

    echo "Downloading ${tarball_name}..."
    curl -fsSL -o "${tmpdir}/${tarball_name}" "${tarball_url}"

    mkdir -p "${INSTALL_DIR}" "${LAYER_JSON_DIR}"
    tar -xzf "${tmpdir}/${tarball_name}" -C "${tmpdir}"

    so_file=$(find "${tmpdir}" -name 'liblsfg-vk.so' | head -n1)
    json_file=$(find "${tmpdir}" -name '*.json' | head -n1)

    if [[ -z "${so_file}" ]]; then
        echo "ERROR: liblsfg-vk.so not found in archive." >&2
        exit 1
    fi

    install -Dm 0755 "${so_file}" "${INSTALL_DIR}/liblsfg-vk.so"
    if [[ -n "${json_file}" ]]; then
        sed "s|\"library_path\":.*|\"library_path\": \"${INSTALL_DIR}/liblsfg-vk.so\"|" \
            "${json_file}" > "${LAYER_JSON_DIR}/lsfg-vk.json"
    fi

    echo
    echo "lsfg-vk installed to ${INSTALL_DIR}/liblsfg-vk.so"
    echo
    echo "Enable per game in Steam launch options:"
    echo "  ENABLE_LSFG=1 %command%"
    echo
    echo "Or enable globally (all Vulkan games):"
    echo "  DISABLE_LSFG_VK=0 in ~/.config/environment.d/99-kyth-lsfg.conf"

# Install CoolerControl — GUI fan curve and thermal management.
# More flexible than CoreCtrl: supports PWM fan curves per temperature source,
# lighting, and per-profile automation.
[group('KythOS')]
install-coolercontrol:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Installing CoolerControl..."
    sudo rpm-ostree install --idempotent coolercontrol
    echo
    echo "Done. Reboot to activate, then enable the service:"
    echo "  sudo systemctl enable --now coolercontrold"
    echo "  systemctl --user enable --now coolercontrol-liqctld.service"

# Deploy OptiScaler to a game directory — enables FSR2/3, XeSS, and
# DLSS-translation for any DirectX 11/12 game through Proton's DLL override.
#
# OptiScaler hooks into the game by replacing nvngx.dll.  After deploying, set
# the Steam launch option:
#   WINEDLLOVERRIDES="nvngx=n,b" %command%
#
# Usage:
#   ujust deploy-opticscaler /path/to/game/dir
#
# The game directory is the folder containing the game's main .exe.
# For Steam games: ~/.local/share/Steam/steamapps/common/<game>
#
# OptiScaler adds upscaling even to games that ship without it:
#   • FSR2 / FSR3 — AMD FidelityFX Super Resolution (works on all GPUs)
#   • XeSS        — Intel Xe Super Sampling (works on all GPUs)
#   • DLSS→FSR    — translates DLSS API calls to FSR on AMD/Intel
#
# Docs: https://github.com/cdozdil/OptiScaler
[group('KythOS')]
deploy-opticscaler gamedir="":
    #!/usr/bin/env bash
    set -euo pipefail

    GAMEDIR="${gamedir}"
    BAKED_DIR="/usr/share/kyth/opticscaler"

    if [[ -z "${GAMEDIR}" ]]; then
        echo "Usage: ujust deploy-opticscaler /path/to/game/dir" >&2
        echo
        echo "Example (Steam):"
        echo "  ujust deploy-opticscaler ~/.local/share/Steam/steamapps/common/MyGame"
        exit 1
    fi

    if [[ ! -d "${GAMEDIR}" ]]; then
        echo "ERROR: directory not found: ${GAMEDIR}" >&2
        exit 1
    fi

    echo "━━━ KythOS OptiScaler Deploy ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    # ── Source: baked image or live download ─────────────────────────────────
    TMPDIR_OS=""
    SRC_DIR="${BAKED_DIR}"

    if [[ ! -d "${BAKED_DIR}" ]] || [[ -z "$(ls -A "${BAKED_DIR}" 2>/dev/null)" ]]; then
        echo "  Baked OptiScaler not found — downloading latest release from GitHub…"
        echo
        TMPDIR_OS=$(mktemp -d)
        trap 'rm -rf "${TMPDIR_OS}"' EXIT
        release_json="${TMPDIR_OS}/release.json"
        OS_REPO_API="https://api.github.com/repos/cdozdil/OptiScaler/releases/latest"

        if ! curl -fsSL "${OS_REPO_API}" -o "${release_json}"; then
            echo "ERROR: failed to fetch OptiScaler release info from GitHub." >&2
            exit 1
        fi

        OS_URL=$(
            grep -oP 'https://[^"]+\.zip' "${release_json}" |
                grep -iv 'source\|symbols\|pdb\|debug' |
                grep -iv '\bwin32\b\|_x86[^_]' |
                head -n1
        ) || true

        if [[ -z "${OS_URL}" ]]; then
            echo "ERROR: no suitable zip found in the latest OptiScaler release." >&2
            echo "  Check https://github.com/cdozdil/OptiScaler/releases" >&2
            exit 1
        fi

        OS_ZIP=$(basename "${OS_URL}")
        echo "  Downloading ${OS_ZIP}…"
        curl -fsSL "${OS_URL}" -o "${TMPDIR_OS}/${OS_ZIP}"
        mkdir -p "${TMPDIR_OS}/extracted"
        unzip -q "${TMPDIR_OS}/${OS_ZIP}" -d "${TMPDIR_OS}/extracted/"
        SRC_DIR="${TMPDIR_OS}/extracted"
    else
        echo "  Using baked OptiScaler from ${BAKED_DIR}"
    fi

    # ── Copy DLLs and config to the game directory ───────────────────────────
    echo
    echo "  Copying OptiScaler files to:"
    echo "    ${GAMEDIR}"
    echo
    cp -r "${SRC_DIR}/." "${GAMEDIR}/"
    dll_count=$(find "${GAMEDIR}" -maxdepth 2 -iname '*.dll' | wc -l)
    echo "  Copied ${dll_count} file(s)."

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  OptiScaler deployed."
    echo
    echo "  Set this Steam launch option for the game:"
    echo "    WINEDLLOVERRIDES=\"nvngx=n,b\" %command%"
    echo
    echo "  Right-click the game → Properties → Launch Options → paste the above."
    echo
    echo "  Upscaling modes (configure in-game or via OptiScaler.ini):"
    echo "    FSR2 / FSR3 — works on all GPUs"
    echo "    XeSS        — works on all GPUs (Intel tuned)"
    echo "    DLSS        — NVIDIA only (requires RTX)"
    echo
    echo "  To remove: delete nvngx.dll / OptiScaler.dll from the game folder."

# Install OBS Studio — screen recording and live streaming.
[group('KythOS')]
install-obs: (_install-flatpak "com.obsproject.Studio" "OBS Studio")
    @flatpak override --user --env=OBS_VKCAPTURE=1 com.obsproject.Studio || true
    @echo "obs-vkcapture is enabled for Vulkan/OpenGL game capture."

# Enable OBS game capture (obs-vkcapture) system-wide for the current user.
# Use this if you run OBS outside Flatpak (e.g. a native build).
# Flatpak OBS users don't need this — install-obs already sets it per-app.
[group('KythOS')]
enable-obs-capture:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "${HOME}/.config/environment.d"
    printf 'OBS_VKCAPTURE=1\n' > "${HOME}/.config/environment.d/obs-vkcapture.conf"
    echo "OBS_VKCAPTURE=1 written to ~/.config/environment.d/obs-vkcapture.conf"
    echo "Log out and back in (or reboot) to apply."
    echo
    echo "To disable:  rm ~/.config/environment.d/obs-vkcapture.conf"

# Install the Itch.io desktop app — indie game store and library manager.
[group('KythOS')]
install-itch: (_install-flatpak "io.itch.itch" "Itch.io")

# Install RetroArch — multi-system emulator frontend (NES, SNES, PS1, N64, ...).
[group('KythOS')]
install-retroarch: (_install-flatpak "org.libretro.RetroArch" "RetroArch")
    @echo "Tip: download cores from inside RetroArch: Main Menu → Load Core → Download a Core."

# Install Piper — GUI for configuring gaming mice (DPI, buttons, LEDs).

# Uses the Flatpak which bundles ratbagd — no rpm-ostree layering required.
[group('KythOS')]
install-piper: (_install-flatpak "org.freedesktop.Piper" "Piper")

# Install OpenRGB — unified RGB lighting control for motherboards, RAM, GPUs,
# fans and peripherals. Uses the Flatpak with --device=all for hardware access.
# Note: SMBus/i2c access (RAM RGB, some motherboard headers) may need the i2c
# kernel modules loaded. If devices are missing, run:

# sudo modprobe i2c-dev i2c-piix4    (or the appropriate module for your board)
[group('KythOS')]
install-openrgb: (_install-flatpak "org.openrgb.OpenRGB" "OpenRGB")
    @flatpak override --user --device=all org.openrgb.OpenRGB
    @echo "If RGB RAM or motherboard headers are missing, load i2c kernel modules:"
    @echo "  sudo modprobe i2c-dev i2c-piix4"
