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
    # SECURITY: installs a Vulkan *implicit layer* .so (auto-loaded into every
    # Vulkan process, incl. Steam). Mirrors install-umu: the release asset digest
    # is verified before extraction, the tarball is extracted with a traversal
    # filter, and the install is refused when no checksum is available.
    # Upstream moved from the dead Juniorkl/lsfg-vk fork to PancakeTAS/lsfg-vk;
    # the tag is pinned (bump deliberately, not via `latest`).
    LSFG_REPO="PancakeTAS/lsfg-vk"
    LSFG_TAG="v1.0.0"  # pinned; bump deliberately after reviewing the release
    LSFG_API="https://api.github.com/repos/${LSFG_REPO}/releases/tags/${LSFG_TAG}"
    INSTALL_DIR="${HOME}/.local/lib"
    LAYER_JSON_DIR="${HOME}/.local/share/vulkan/implicit_layer.d"
    echo "Fetching lsfg-vk ${LSFG_TAG} release info..."
    tmpdir=$(mktemp -d); trap 'rm -rf "${tmpdir}"' EXIT
    release_json="${tmpdir}/release.json"
    curl -fsSL "${LSFG_API}" -o "${release_json}"
    tarball_url=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next((a["browser_download_url"] for a in d.get("assets",[]) if a.get("name","").endswith(".tar.zst")), ""))' "${release_json}")
    if [[ -z "${tarball_url}" ]]; then
        echo "ERROR: no .tar.zst asset in ${LSFG_REPO} ${LSFG_TAG}." >&2
        exit 1
    fi
    tarball_name="${tarball_url##*/}"
    echo "Downloading ${tarball_name}..."
    curl -fsSL -o "${tmpdir}/${tarball_name}" "${tarball_url}"
    # Checksum: prefer the GitHub release asset digest, refuse unverified.
    LSFG_DIGEST=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next((a.get("digest","") for a in d.get("assets",[]) if a.get("name")==sys.argv[2]),""))' "${release_json}" "${tarball_name}") || true
    if [[ "${LSFG_DIGEST}" =~ ^sha256:[0-9a-fA-F]{64}$ ]]; then
        echo "${LSFG_DIGEST#sha256:}  ${tmpdir}/${tarball_name}" | sha256sum -c - \
            || { echo "SHA256 mismatch for ${tarball_name}; refusing to install." >&2; exit 1; }
        echo "${tarball_name}: SHA256 verified OK (release asset digest)"
    else
        echo "No checksum available for ${tarball_name} (no release asset digest); refusing to install." >&2
        exit 1
    fi
    mkdir -p "${INSTALL_DIR}" "${LAYER_JSON_DIR}" "${tmpdir}/extracted"
    # Traversal filter: reject absolute paths and `..` members before extract.
    if tar --list -f "${tmpdir}/${tarball_name}" 2>/dev/null | grep -Eq '(^|/)\.\.(/|$)|^/'; then
        echo "ERROR: tarball contains absolute paths or parent-directory traversal; refusing." >&2
        exit 1
    fi
    tar -xf "${tmpdir}/${tarball_name}" -C "${tmpdir}/extracted"
    so_file=$(find "${tmpdir}/extracted" -name 'liblsfg-vk.so' | head -n1)
    json_file=$(find "${tmpdir}/extracted" -name '*.json' | head -n1)
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
        # Checksum: verify the release asset digest before unzip; refuse
        # unverified DLLs — they are loaded by Proton into the game process.
        OS_DIGEST=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next((a.get("digest","") for a in d.get("assets",[]) if a.get("name")==sys.argv[2]),""))' "${release_json}" "${OS_ZIP}") || true
        if [[ "${OS_DIGEST}" =~ ^sha256:[0-9a-fA-F]{64}$ ]]; then
            echo "${OS_DIGEST#sha256:}  ${TMPDIR_OS}/${OS_ZIP}" | sha256sum -c - \
                || { echo "  SHA256 mismatch for ${OS_ZIP}; refusing to deploy." >&2; exit 1; }
            echo "  ${OS_ZIP}: SHA256 verified OK (release asset digest)"
        else
            echo "  No checksum available for ${OS_ZIP} (no release asset digest); refusing to deploy." >&2
            exit 1
        fi
        mkdir -p "${TMPDIR_OS}/extracted"
        # Zip traversal guard: reject absolute paths and `..` entries.
        if unzip -l "${TMPDIR_OS}/${OS_ZIP}" | awk '{print $4}' | grep -Eq '(^|/)\.\.(/|$)|^/'; then
            echo "  ERROR: zip contains absolute paths or parent-directory traversal; refusing." >&2
            exit 1
        fi
        unzip -q "${TMPDIR_OS}/${OS_ZIP}" -d "${TMPDIR_OS}/extracted/"
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
