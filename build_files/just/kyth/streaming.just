# Set up Sunshine game streaming server.
# Sunshine lets you stream your desktop to any Moonlight client (phone, TV,
# Shield, another PC). Uses the hardware encoder on AMD/Intel/NVIDIA GPUs.
# After setup, open https://localhost:47990 in a browser to configure.
[group('KythOS')]
setup-sunshine:
    #!/usr/bin/env bash
    set -euo pipefail

    if ! flatpak info dev.lizardbyte.app.Sunshine >/dev/null 2>&1; then
        echo "Installing Sunshine game streaming server via Flatpak..."
        flatpak install -y flathub dev.lizardbyte.app.Sunshine
    fi

    # Grant necessary host uinput/display permissions for Flatpak game streaming
    flatpak override --user --filesystem=host dev.lizardbyte.app.Sunshine 2>/dev/null || true

    echo "Starting Sunshine via Flatpak..."
    flatpak run dev.lizardbyte.app.Sunshine &

    # Open the web UI
    echo
    echo "Sunshine is running. Open https://localhost:47990 in your browser to configure."
    echo "Default credentials: admin / admin (change immediately)"
    echo
    echo "Firewall: Sunshine listens on TCP 47984-47990 and UDP 47998-48010."
    echo "If remote streaming does not work, open those ports:"
    echo "  sudo firewall-cmd --permanent --add-port=47984-47990/tcp"
    echo "  sudo firewall-cmd --permanent --add-port=47998-48010/udp"
    echo "  sudo firewall-cmd --reload"

# Setup WiVRn VR streaming — opens firewall ports and ensures Avahi/mDNS discovery is active.
[group('KythOS')]
setup-vr:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Configuring host system for WiVRn VR streaming..."

    # 1. Enable and start Avahi daemon (for headset mDNS discovery)
    echo "→ Enabling mDNS discovery (avahi-daemon)..."
    sudo systemctl enable --now avahi-daemon.service

    # 2. Open firewall ports (WiVRn: 9757 UDP/TCP, mDNS: 5353 UDP)
    if systemctl is-active --quiet firewalld; then
        echo "→ Opening firewall ports for WiVRn (9757) and mDNS (5353)..."
        sudo firewall-cmd --permanent --add-port=9757/udp --add-port=9757/tcp
        sudo firewall-cmd --permanent --add-port=5353/udp
        sudo firewall-cmd --reload
    else
        echo "→ firewalld is not active; skipping firewall port rules."
    fi

    # 3. Apply user-level Flatpak overrides for Steam as a fallback
    echo "→ Ensuring Steam Flatpak has OpenXR filesystem overrides..."
    flatpak override --user \
        --filesystem=xdg-run/wivrn:ro \
        --filesystem=xdg-config/openxr:ro \
        --filesystem=xdg-config/openvr:ro \
        com.valvesoftware.Steam || true

    echo
    echo "WiVRn VR configuration setup completed successfully!"
    echo "Start the WiVRn app, connect your standalone headset, and launch Steam!"

# Set up Tailscale zero-config WireGuard mesh VPN.
# Tailscale makes your devices available on a private network with no port
# forwarding — great for LAN party gaming over the internet, remote desktop,
# and Moonlight streaming through NAT.
[group('KythOS')]
setup-tailscale:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Enabling tailscaled service..."
    sudo systemctl enable --now tailscaled.service
    echo
    echo "Starting Tailscale — a browser window will open to authenticate:"
    sudo tailscale up --accept-routes
    echo
    echo "Done. Check your Tailscale network at https://login.tailscale.com/admin/machines"
