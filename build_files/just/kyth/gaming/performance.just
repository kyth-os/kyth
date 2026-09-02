import '../common.just'

# Install GPU Screen Recorder.
[group('KythOS')]
install-gpu-screen-recorder: (_install-flatpak "com.dec05eba.gpu_screen_recorder" "GPU Screen Recorder")

# Install GOverlay for MangoHud and vkBasalt configuration.
[group('KythOS')]
install-goverlay: (_install-flatpak "io.github.benjamimgois.goverlay" "GOverlay")

# Install MangoJuice for lightweight MangoHud configuration.
[group('KythOS')]
install-mangojuice: (_install-flatpak "io.github.radiolamp.mangojuice" "MangoJuice")

# Install OBS Studio.
[group('KythOS')]
install-obs: (_install-flatpak "com.obsproject.Studio" "OBS Studio")
    @flatpak override --user --env=OBS_VKCAPTURE=1 com.obsproject.Studio || true
    @echo "obs-vkcapture is enabled for Vulkan/OpenGL game capture."

# Enable OBS game capture (obs-vkcapture) system-wide.
[group('KythOS')]
enable-obs-capture:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "${HOME}/.config/environment.d"
    printf 'OBS_VKCAPTURE=1\n' > "${HOME}/.config/environment.d/obs-vkcapture.conf"
    echo "OBS_VKCAPTURE=1 written."
    echo "Log out and back in (or reboot) to apply."

# Install lsfg-vk (Lossless Scaling Frame Generation for Vulkan).
[group('KythOS')]
install-lsfg-vk:
    #!/usr/bin/env bash
    set -euo pipefail
    LSFG_REPO="https://api.github.com/repos/Juniorkl/lsfg-vk/releases/latest"
    INSTALL_DIR="${HOME}/.local/lib"
    LAYER_JSON_DIR="${HOME}/.local/share/vulkan/implicit_layer.d"
    echo "Fetching latest lsfg-vk release..."
    release_json=$(curl -fsSL "${LSFG_REPO}")
    tarball_url=$(printf '%s' "${release_json}" | jq -r '[.assets[]? | select(.name | endswith(".tar.gz")) | .browser_download_url][0] // empty')
    if [[ -z "${tarball_url}" ]]; then
        echo "ERROR: no LSFG-VK tarball was published in the latest release." >&2
        exit 1
    fi
    tarball_name="${tarball_url##*/}"
    tmpdir=$(mktemp -d); trap 'rm -rf "${tmpdir}"' EXIT
    echo "Downloading ${tarball_name}..."
    curl -fsSL -o "${tmpdir}/${tarball_name}" "${tarball_url}"
    mkdir -p "${INSTALL_DIR}" "${LAYER_JSON_DIR}"
    tar -xzf "${tmpdir}/${tarball_name}" -C "${tmpdir}"
    so_file=$(find "${tmpdir}" -name 'liblsfg-vk.so' | head -n1)
    json_file=$(find "${tmpdir}" -name '*.json' | head -n1)
    if [[ -z "${so_file}" ]]; then echo "ERROR: liblsfg-vk.so not found." >&2; exit 1; fi
    install -Dm 0755 "${so_file}" "${INSTALL_DIR}/liblsfg-vk.so"
    if [[ -n "${json_file}" ]]; then
        sed "s|\"library_path\":.*|\"library_path\": \"${INSTALL_DIR}/liblsfg-vk.so\"|" "${json_file}" > "${LAYER_JSON_DIR}/lsfg-vk.json"
    fi
    echo; echo "lsfg-vk installed. Enable per-game: ENABLE_LSFG=1 %command%"

# Deploy OptiScaler to a game directory.
[group('KythOS')]
deploy-opticscaler gamedir="":
    #!/usr/bin/env bash
    set -euo pipefail
    GAMEDIR="${gamedir}"
    BAKED_DIR="/usr/share/kyth/opticscaler"
    if [[ -z "${GAMEDIR}" ]]; then
        echo "Usage: ujust deploy-opticscaler /path/to/game/dir" >&2; exit 1
    fi
    if [[ ! -d "${GAMEDIR}" ]]; then echo "ERROR: directory not found: ${GAMEDIR}" >&2; exit 1; fi
    echo "━━━ KythOS OptiScaler Deploy ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    TMPDIR_OS=""; SRC_DIR="${BAKED_DIR}"
    if [[ ! -d "${BAKED_DIR}" ]] || [[ -z "$(ls -A "${BAKED_DIR}" 2>/dev/null)" ]]; then
        echo "  Baked OptiScaler not found — downloading latest release…"
        TMPDIR_OS=$(mktemp -d); trap 'rm -rf "${TMPDIR_OS}"' EXIT
        release_json="${TMPDIR_OS}/release.json"
        OS_REPO_API="https://api.github.com/repos/cdozdil/OptiScaler/releases/latest"
        curl -fsSL "${OS_REPO_API}" -o "${release_json}" || { echo "ERROR: fetch failed." >&2; exit 1; }
        OS_URL=$(grep -oP 'https://[^"]+\.zip' "${release_json}" | grep -iv 'source\|symbols\|pdb\|debug' | grep -iv '\bwin32\b\|_x86[^_]' | head -n1) || true
        [[ -z "${OS_URL}" ]] && { echo "ERROR: no suitable zip found." >&2; exit 1; }
        OS_ZIP=$(basename "${OS_URL}")
        echo "  Downloading ${OS_ZIP}…"
        curl -fsSL "${OS_URL}" -o "${TMPDIR_OS}/${OS_ZIP}"
        mkdir -p "${TMPDIR_OS}/extracted"; unzip -q "${TMPDIR_OS}/${OS_ZIP}" -d "${TMPDIR_OS}/extracted/"
        SRC_DIR="${TMPDIR_OS}/extracted"
    else
        echo "  Using baked OptiScaler from ${BAKED_DIR}"
    fi
    cp -r "${SRC_DIR}/." "${GAMEDIR}/"
    dll_count=$(find "${GAMEDIR}" -maxdepth 2 -iname '*.dll' | wc -l)
    echo "  Copied ${dll_count} file(s)."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  OptiScaler deployed. Set Steam launch option: WINEDLLOVERRIDES=\"nvngx=n,b\" %command%"

# Show KythOS Adaptive Game & Performance Governor status.
[group('KythOS')]
game-boost:
    @/usr/bin/kyth-game-boost

# Pre-compile Vulkan & Mesa shaders to eliminate in-game stutter.
[group('KythOS')]
preheat-shaders:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-shader-preheat

# Run end-to-end subsystem health and low-latency diagnostics.
[group('KythOS')]
health-check:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-health-check

