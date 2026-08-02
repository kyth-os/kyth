# Check NVIDIA hardware, akmod build, loaded module, and reboot-needed state.
[group('KythOS')]
nvidia-status:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-nvidia-status

# Install NVIDIA proprietary drivers on KythOS.
#
# Runs in two phases — just re-run after each reboot prompt:
#
#   Phase 1: Layers akmod-nvidia via rpm-ostree (requires a reboot).
#   Phase 2: Compiles the kernel module via akmods (requires a final reboot).
#
# Usage:
# ujust install-nvidia-driver          # run once, reboot when prompted, repeat
[group('KythOS')]
install-nvidia-driver:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "━━━ KythOS NVIDIA Driver Wizard ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    # ── GPU detection ─────────────────────────────────────────────────────────
    if ! lspci | grep -qi nvidia; then
        echo "  No NVIDIA GPU detected. Nothing to install."
        exit 0
    fi
    echo "  NVIDIA GPU detected."
    echo

    # ── Already active ────────────────────────────────────────────────────────
    if modinfo nvidia &>/dev/null && lsmod | grep -q "^nvidia "; then
        echo "  NVIDIA driver is already active. Nothing to do."
        exit 0
    fi

    # ── Phase 1: layer the source package ────────────────────────────────────
    if ! rpm -q akmod-nvidia &>/dev/null; then
        echo "  Phase 1/2 — Layering akmod-nvidia via rpm-ostree."
        echo "  A reboot is required after this step."
        echo
        sudo rpm-ostree install --idempotent akmod-nvidia
        echo
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  akmod-nvidia has been staged."
        echo
        echo "  Next steps:"
        echo "    1. Reboot:             systemctl reboot"
        echo "    2. After reboot, run:  ujust install-nvidia-driver"
        exit 0
    fi

    # ── Module already built — reboot to activate ─────────────────────────────
    if modinfo nvidia &>/dev/null; then
        KARGS="rd.driver.blacklist=nouveau,nova_core modprobe.blacklist=nouveau,nova_core nvidia-drm.modeset=1"
        sudo grubby --update-kernel=ALL --args="${KARGS}" 2>/dev/null || \
            echo "  (grubby: non-fatal — kargs.d applies on next deployment)"
        echo "  Kernel module is already built. Reboot to activate the driver."
        echo "    systemctl reboot"
        exit 0
    fi

    # ── Phase 2: compile the kernel module ───────────────────────────────────
    echo "  Phase 2/2 — Compiling kernel module via akmods."
    echo "  This may take 5–15 minutes on first compile…"
    echo

    # The policy engine owns module compilation, kernel arguments, suspend
    # services, and durable setup state so the UI and boot service agree.
    sudo /usr/bin/kyth-hardware-policy apply --force

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  NVIDIA driver compiled successfully."
    echo "  Reboot to activate:"
    echo "    systemctl reboot"

# Install DisplayLink USB display adapter driver (evdi kernel module + daemon).
#
# Required for USB-C/USB-A docking stations from Dell WD, HP, Lenovo, and most
# "works with DisplayLink" hubs. The evdi kernel module is built by akmods on
# first boot, then the DisplayLink daemon handles display mux and output routing.
#
# Usage:
#   ujust install-displaylink            # installs and enables the driver
#
# After setup: plug in your dock/adapter and it should appear in display settings.
# If outputs are missing after a kernel upgrade, rerun to rebuild the akmod.
[group('KythOS')]
install-displaylink:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "━━━ KythOS DisplayLink Driver ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    # ── Already installed ─────────────────────────────────────────────────────
    if modinfo evdi &>/dev/null 2>&1; then
        echo "  evdi kernel module is already installed."
        if systemctl is-enabled displaylink.service &>/dev/null 2>&1; then
            echo "  DisplayLink daemon is enabled."
        else
            echo "  Basic USB display support is active via the evdi module."
            echo "  For the full Synaptics daemon (advanced multi-monitor):"
            echo "    https://www.synaptics.com/products/displaylink-graphics/downloads/fedora"
        fi
        exit 0
    fi

    # ── Layer evdi via rpm-ostree (RPM Fusion nonfree) ────────────────────────
    # akmod-evdi is in RPM Fusion nonfree, which is pre-configured in this image.
    # rpm-ostree layers it into the next deployment; the akmod build runs at
    # first boot after the reboot (same mechanism as akmod-nvidia).
    echo "  Installing evdi kernel module from RPM Fusion nonfree..."
    sudo rpm-ostree install --idempotent akmod-evdi evdi

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  evdi staged. Reboot to build and activate the kernel module:"
    echo "    systemctl reboot"
    echo
    echo "  After rebooting, plug in your USB dock — outputs appear in"
    echo "  System Settings → Display and Monitor."
    echo
    echo "  For the full Synaptics DisplayLink daemon (USB 3.0 adapters, audio"
    echo "  over dock, advanced multi-monitor), download the RPM and then:"
    echo "    https://www.synaptics.com/products/displaylink-graphics/downloads/fedora"
    echo "    sudo rpm-ostree install --idempotent /path/to/displaylink-*.rpm"
