import '../common.just'

# Download and install the latest Proton-CachyOS.
[group('KythOS')]
update-proton-cachyos:
    #!/usr/bin/env bash
    set -euo pipefail
    sudo /usr/bin/kyth-proton-cachyos-update

# Install or reinstall umu-launcher (umu-run) from the latest GitHub release.
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
    UMU_URL=$(grep -oP 'https://[^"]+/releases/download/[^"]+umu-launcher-[^"]+-zipapp\.tar' "${release_json}" | head -n1) || true
    if [[ -z "${UMU_URL}" ]]; then
        UMU_URL=$(grep -oP 'https://[^"]+/releases/download/[^"]+\.tar(\.(gz|zst))?' "${release_json}" | grep -iv 'source\|src' | head -n1) || true
    fi
    if [[ -z "${UMU_URL}" ]]; then
        echo "Could not find an installable release tarball." >&2; exit 1
    fi
    UMU_TARBALL=$(basename "${UMU_URL}")
    echo "Downloading ${UMU_TARBALL}…"
    curl -fsSL "${UMU_URL}" -o "${TMPDIR_UMU}/${UMU_TARBALL}"
    tar -xf "${TMPDIR_UMU}/${UMU_TARBALL}" -C "${TMPDIR_UMU}/"
    UMU_BIN=$(find "${TMPDIR_UMU}" -name 'umu-run' -type f | head -n1)
    if [[ -z "${UMU_BIN}" ]]; then echo "umu-run not found." >&2; exit 1; fi
    sudo install -m 0755 "${UMU_BIN}" /usr/local/bin/umu-run
    UMU_PKGDIR=$(find "${TMPDIR_UMU}" -maxdepth 3 -name 'umu' -type d | grep -v '__pycache__' | head -n1)
    if [[ "${UMU_TARBALL}" != *-zipapp.tar && -n "${UMU_PKGDIR}" ]]; then
        PY_SITEPKG=$(python3 -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
        sudo mkdir -p "${PY_SITEPKG}"; sudo cp -r "${UMU_PKGDIR}" "${PY_SITEPKG}/"
    fi
    echo "umu-launcher installed: $(umu-run --version 2>/dev/null || echo 'ok')"

# Toggle FSR4 upscaling globally for all Steam/Proton games.
[group('KythOS')]
toggle-fsr4:
    #!/usr/bin/env bash
    set -euo pipefail
    conf="${HOME}/.config/environment.d/99-kyth-fsr4.conf"
    mkdir -p "${HOME}/.config/environment.d"
    if [[ -f "${conf}" ]]; then
        rm -f "${conf}"; echo "FSR4 global override removed. Restart Steam to apply."
    else
        printf 'PROTON_FSR4_UPGRADE=1\n' > "${conf}"
        echo "FSR4 global override enabled. Run again to disable."
    fi

# Toggle DLSS/NVAPI globally for all Steam/Proton games.
[group('KythOS')]
toggle-nvapi:
    #!/usr/bin/env bash
    set -euo pipefail
    conf="${HOME}/.config/environment.d/99-kyth-nvapi.conf"
    mkdir -p "${HOME}/.config/environment.d"
    if [[ -f "${conf}" ]]; then
        rm -f "${conf}"; echo "NVAPI global override removed. Restart Steam to apply."
    else
        printf 'PROTON_ENABLE_NVAPI=1\nDXVK_ENABLE_NVAPI=1\n' > "${conf}"
        echo "NVAPI global override enabled. Run again to disable."
    fi
