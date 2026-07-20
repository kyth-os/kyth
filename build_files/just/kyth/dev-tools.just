# Create a Fedora development container for KythOS work.
#
# This is intentionally self-contained so it does not depend on any imported
# justfiles that may not exist on end-user systems.
#
# It also installs VS Code from Flatpak when missing, since the RPM is no
# longer baked into KythOS images.
[group('KythOS')]
setup-kyth-dev-box:
    #!/usr/bin/env bash
    set -euo pipefail
    exec kyth-ai-dev setup

# Configure VS Code and Brave to avoid KWallet prompts.
[group('KythOS')]
install-vscode:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-vscode-wallet
    echo
    echo "VS Code and Headroom are baked into the image."
    echo "Launch VS Code from the app menu or run: code"
    echo "Run Headroom with: headroom"

# Set up Waydroid (Android in a container) on KythOS.
#
# First run:  installs the waydroid package via rpm-ostree, then prompts for a reboot.
# Second run: downloads the Android system image and starts the container service.
#
# Usage:
#   ujust setup-waydroid            # vanilla AOSP (no Google Play)

# Install JetBrains Toolbox — manages all JetBrains IDEs (IntelliJ, PyCharm,
# CLion, Rider, etc.) with one-click install, update, and rollback.
[group('KythOS')]
install-jetbrains-toolbox:
    #!/usr/bin/env bash
    set -euo pipefail

    TOOLBOX_REPO="https://data.services.jetbrains.com/products/releases?code=TBA&latest=true&type=release"
    INSTALL_DIR="${HOME}/.local/bin"
    APPIMAGE_DIR="${HOME}/.local/share/JetBrains/Toolbox"

    echo "Fetching latest JetBrains Toolbox release..."
    download_url=$(curl -fsSL "${TOOLBOX_REPO}" \
        | python3 -c "import sys,json; d=json.load(sys.stdin); \
          print(d['TBA'][0]['downloads']['linux']['link'])")

    tarball="${download_url##*/}"
    tmpdir=$(mktemp -d)
    trap 'rm -rf "${tmpdir}"' EXIT

    echo "Downloading ${tarball}..."
    curl -fsSL -o "${tmpdir}/${tarball}" "${download_url}"

    mkdir -p "${APPIMAGE_DIR}" "${INSTALL_DIR}"
    tar -xzf "${tmpdir}/${tarball}" -C "${tmpdir}"
    appimage=$(find "${tmpdir}" -name 'jetbrains-toolbox' | head -n1)
    install -Dm 0755 "${appimage}" "${APPIMAGE_DIR}/jetbrains-toolbox"

    # Symlink to PATH
    ln -sf "${APPIMAGE_DIR}/jetbrains-toolbox" "${INSTALL_DIR}/jetbrains-toolbox"

    echo
    echo "JetBrains Toolbox installed to ${APPIMAGE_DIR}/jetbrains-toolbox"
    echo "Run it once to complete setup and install your IDEs:"
    echo "  jetbrains-toolbox"
