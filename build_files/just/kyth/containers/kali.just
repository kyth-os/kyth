import '../common.just'

# Set up a Kali Linux security toolbox via distrobox.
# ujust setup-kali-box [headless|gui|everything]
[group('KythOS')]
setup-kali-box tools="headless":
    #!/usr/bin/env bash
    set -euo pipefail

    _sudo() { if [[ -t 0 ]]; then sudo "$@"; else sudo -A "$@"; fi; }

    tools="{{ tools }}"
    case "${tools}" in
        headless)   meta="kali-linux-headless"   ;;
        gui)        meta="kali-linux-default"    ;;
        everything) meta="kali-linux-everything" ;;
        *) echo "Invalid: ${tools}. Options: headless, gui, everything" >&2; exit 1 ;;
    esac

    if [[ "${tools}" == "everything" ]]; then
        echo "━━━ WARNING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Expect 15–20 GB or more of downloads."
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi

    if distrobox list --no-color 2>/dev/null | grep -q '^kali\b'; then
        echo "Found rootless container named 'kali'; replacing with rootful..."
        distrobox stop kali --yes 2>/dev/null || true
        distrobox rm --force kali 2>/dev/null || true
        podman rm -f kali 2>/dev/null || true
    fi

    _rootful_exists=0
    _sudo podman inspect kali >/dev/null 2>&1 && _rootful_exists=1 || true
    if [[ "${_rootful_exists}" -eq 1 ]]; then
        _kali_image=$(_sudo podman inspect kali --format '{{ "{{" }}.ImageName{{ "}}" }}' 2>/dev/null || true)
        _kali_privileged=$(_sudo podman inspect kali --format '{{ "{{" }}.HostConfig.Privileged{{ "}}" }}' 2>/dev/null || true)
        _kali_security_opts=$(_sudo podman inspect kali --format '{{ "{{" }}range .HostConfig.SecurityOpt{{ "}}" }}{{ "{{" }}.{{ "}}" }} {{ "{{" }}end{{ "}}" }}' 2>/dev/null || true)
        if [[ "${_kali_image}" == *kali* ]] && [[ "${_kali_privileged}" == "true" ]] && [[ "${_kali_security_opts}" == *label=disable* ]]; then
            echo "Kali box already exists with raw-socket capable rootful settings."
            echo "To enter: distrobox enter --root kali"
            exit 0
        fi
        distrobox stop --root kali --yes 2>/dev/null || true
        distrobox rm --root --force kali 2>/dev/null || true
        _sudo podman rm -f kali 2>/dev/null || true
    fi

    echo "━━━ Setting up Kali Linux toolbox ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Package: ${meta}  (rootful)"

    distrobox create --root --image kalilinux/kali-rolling --name kali --yes \
        --additional-flags "--privileged --security-opt label=disable"
    distrobox enter --root kali -- bash -c "
        export DEBIAN_FRONTEND=noninteractive
        (printf '%s\n' \
            'popularity-contest popularity-contest/particiate boolean false'
            'console-setup console-setup/charmap47 UTF-8' \
            'samba-common samba-common/dhcp boolean false' \
            'macchanger macchanger/automatically_run boolean false' \
            'wireshark-common wireshark-common/install-setuid boolean true' \
            'sslh sslh/inetd_or_standalone standalone' \
            | sudo debconf-set-selections) || true
        sudo -E apt-get install -y -o Dpkg::Options::=--force-confold '${meta}'"

    distrobox enter --root kali -- bash -c "
        echo '${USER} ALL=(root) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null
        sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd
        mkdir -p /root/.config/gtk-3.0; printf '[Settings]\ngtk-icon-theme-name = hicolor\n' > /root/.config/gtk-3.0/settings.ini
    " || true

    distrobox enter --root kali -- bash -c "
        if command -v nmap >/dev/null 2>&1; then
            printf '#!/bin/sh\nexec sudo /usr/bin/nmap \"\$@\"\n' | sudo tee /usr/local/bin/nmap > /dev/null
            sudo chmod 755 /usr/local/bin/nmap
        fi" || true

    if [[ "${tools}" == "gui" || "${tools}" == "everything" ]]; then
        echo; echo "── Exporting Kali GUI apps to application launcher ─────────────────"
        distrobox enter --root kali -- bash -c '
            exported=0
            while IFS= read -r -d "" f; do
                app=$(basename "$f" .desktop); distrobox-export --app "$app" 2>/dev/null && exported=$((exported+1)) || true
            done < <(find /usr/share/applications -name "*.desktop" -print0)
            echo "  Exported ${exported} desktop entries."'
        kyth-kali-desktop-fixup
    fi
    echo; echo "Done. Enter with: distrobox enter --root kali"

# Export Kali Linux GUI apps to the host application launcher.
[group('KythOS')]
export-kali-apps:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! distrobox list --root --no-color 2>/dev/null | grep -q '^kali\b' && ! distrobox list --no-color 2>/dev/null | grep -q '^kali\b'; then
        echo "No kali container found. Run 'ujust setup-kali-box gui' first." >&2; exit 1
    fi
    echo "━━━ Exporting Kali GUI apps ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    distrobox enter --root kali -- bash -c "
        echo '${USER} ALL=(root) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null
        sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd" 2>/dev/null || true
    distrobox enter --root kali -- bash -c '
        exported=0
        while IFS= read -r -d "" f; do
            app=$(basename "$f" .desktop)
            distrobox-export --app "$app" 2>/dev/null && exported=$((exported+1)) || true
        done < <(find /usr/share/applications -name "*.desktop" -print0)
        echo "  Exported ${exported} entries."'
    kyth-kali-desktop-fixup
    echo "Done. Kali tools should appear under 'Security' in the app launcher."
