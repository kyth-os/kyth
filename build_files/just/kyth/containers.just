# Shared helpers (e.g. _install-flatpak). `just` deduplicates repeated imports,
# so this stays valid both standalone and when pulled in via kyth.just.
import 'common.just'

# Install BoxBuddy (distrobox GUI) from Flathub.
[group('KythOS')]
install-boxbuddy: (_install-flatpak "io.github.dvlv.boxbuddyrs" "BoxBuddy")
    @echo "Use it to manage your distrobox containers."

# Set up a Kali Linux security toolbox via distrobox.
#
# The container is created rootful (distrobox create --root) so that root inside
# has real CAP_NET_RAW/CAP_NET_ADMIN in the initial user namespace.  Rootless
# containers cannot open AF_PACKET/SOCK_RAW sockets against host interfaces
# even with --privileged, which breaks nmap, wireshark, and similar tools.
#
# Usage:
#   ujust setup-kali-box              # headless CLI tools only (kali-linux-headless)
#   ujust setup-kali-box gui          # headless + GUI tools (kali-linux-default)
#   ujust setup-kali-box everything   # every available Kali tool (WARNING: 15-20 GB+)
#
# After setup: distrobox enter --root kali
[group('KythOS')]
setup-kali-box tools="headless":
    #!/usr/bin/env bash
    set -euo pipefail

    _sudo() {
        if [[ -t 0 ]]; then
            sudo "$@"
        else
            sudo -A "$@"
        fi
    }

    tools="{{ tools }}"
    case "${tools}" in
        headless)   meta="kali-linux-headless"   ;;
        gui)        meta="kali-linux-default"    ;;
        everything) meta="kali-linux-everything" ;;
        *)
            echo "Unknown tools option: ${tools}" >&2
            echo "Valid options: headless (default), gui, everything" >&2
            exit 1
            ;;
    esac

    if [[ "${tools}" == "everything" ]]; then
        echo "━━━ WARNING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  kali-linux-everything installs every available Kali tool."
        echo "  Expect 15–20 GB or more of downloads and a very long install time."
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo
    fi

    # Verify the existing "kali" container is the socket-capable rootful Kali box.
    # Rootless containers and older rootful containers without label=disable can
    # exist under the same name but still fail nmap/zenmap raw socket scans.
    if distrobox list --no-color 2>/dev/null | grep -q '^kali\b'; then
        echo "Found a rootless container named 'kali'; replacing it with the rootful security toolbox..."
        distrobox stop kali --yes 2>/dev/null || distrobox stop kali 2>/dev/null || true
        distrobox rm --force kali 2>/dev/null || distrobox rm kali --yes 2>/dev/null || true
        podman rm -f kali 2>/dev/null || true
    fi

    _rootful_exists=0
    _sudo podman inspect kali >/dev/null 2>&1 && _rootful_exists=1 || true
    if [[ "${_rootful_exists}" -eq 1 ]]; then
        _kali_image=$(_sudo podman inspect kali --format '{{ "{{" }}.ImageName{{ "}}" }}' 2>/dev/null || true)
        _kali_privileged=$(_sudo podman inspect kali --format '{{ "{{" }}.HostConfig.Privileged{{ "}}" }}' 2>/dev/null || true)
        _kali_security_opts=$(_sudo podman inspect kali --format '{{ "{{" }}range .HostConfig.SecurityOpt{{ "}}" }}{{ "{{" }}.{{ "}}" }} {{ "{{" }}end{{ "}}" }}' 2>/dev/null || true)
        if [[ "${_kali_image}" == *kali* ]] \
            && [[ "${_kali_privileged}" == "true" ]] \
            && [[ "${_kali_security_opts}" == *label=disable* ]]; then
            echo "Kali box already exists with raw-socket capable rootful settings."
            echo "To enter it: distrobox enter --root kali"
            exit 0
        fi

        echo "Found an existing 'kali' container that cannot be trusted for raw socket scans."
        echo "  Image:       ${_kali_image:-unknown}"
        echo "  Privileged:  ${_kali_privileged:-unknown}"
        echo "  SELinux opt: ${_kali_security_opts:-none}"
        echo "Recreating it with privileged rootful networking and SELinux label disabled..."
        distrobox stop --root kali --yes 2>/dev/null || distrobox stop --root kali 2>/dev/null || true
        distrobox rm --root --force kali 2>/dev/null || distrobox rm --root kali --yes 2>/dev/null || true
        _sudo podman rm -f kali 2>/dev/null || true
    fi

    echo "━━━ Setting up Kali Linux toolbox ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Image:    kalilinux/kali-rolling"
    echo "  Package:  ${meta}"
    echo "  Mode:     rootful (required for nmap/wireshark raw socket access)"
    echo

    # Create as a rootful container so security tools (nmap, wireshark, etc.)
    # get real CAP_NET_RAW.  --privileged grants the Linux capabilities, but
    # SELinux on Fedora still enforces its own type-enforcement policy on the
    # container_t domain even for privileged containers.  label=disable runs
    # the container as spc_t (super-privileged container), which is the kernel
    # SELinux type that is unconditionally allowed to open raw/packet sockets.
    distrobox create --root --image kalilinux/kali-rolling --name kali --yes \
        --additional-flags "--privileged --security-opt label=disable"
    distrobox enter --root kali -- bash -c "
        export DEBIAN_FRONTEND=noninteractive
        (
            printf '%s\n' \
                'popularity-contest popularity-contest/participate boolean false' \
                'encfs encfs/security-information boolean true' \
                'encfs encfs/security-information seen true' \
                'console-setup console-setup/charmap47 select UTF-8' \
                'samba-common samba-common/dhcp boolean false' \
                'macchanger macchanger/automatically_run boolean false' \
                'kismet-capture-common kismet-capture-common/install-users string' \
                'kismet-capture-common kismet-capture-common/install-setuid boolean true' \
                'wireshark-common wireshark-common/install-setuid boolean true' \
                'sslh sslh/inetd_or_standalone select standalone' \
                | sudo debconf-set-selections
        ) || true
        sudo -E apt-get install -y \
            -o Dpkg::Options::=--force-confdef \
            -o Dpkg::Options::=--force-confold \
            '${meta}'
    "

    # Grant passwordless sudo inside the container so root-requiring tools
    # (nmap, wireshark, aircrack-ng, etc.) launch from the app menu without a
    # polkit dialog that can not reach the host agent from inside distrobox.
    distrobox enter --root kali -- bash -c "
        echo '${USER} ALL=(root) NOPASSWD: ALL' \
            | sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null
        sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd
        # GTK3 reads the icon theme from the user config dir. When running as
        # root via sudo -E, HOME is preserved as the invoking user but we
        # reset it to /root in kyth-distrobox-root-launch. Pre-create a
        # settings file so GTK uses hicolor (PNG-only) and skips breeze-dark
        # SVG icons that crash via glycin/bwrap inside a container.
        mkdir -p /root/.config/gtk-3.0
        printf '[Settings]\ngtk-icon-theme-name = hicolor\n' \
            > /root/.config/gtk-3.0/settings.ini
    " && echo "  Configured passwordless sudo and GTK icon theme for kali root." || true

    # setcap does not survive overlayfs containers reliably — the kernel strips
    # file capabilities on exec inside user-namespaced containers.  Instead,
    # place a sudo wrapper at /usr/local/bin/nmap (ahead of /usr/bin in PATH)
    # so any user gets CAP_NET_RAW via the already-configured passwordless sudo.
    distrobox enter --root kali -- bash -c "
        if command -v nmap >/dev/null 2>&1; then
            printf '#!/bin/sh\nexec sudo /usr/bin/nmap \"\$@\"\n' \
                | sudo tee /usr/local/bin/nmap > /dev/null
            sudo chmod 755 /usr/local/bin/nmap
            echo '  Installed sudo nmap wrapper at /usr/local/bin/nmap'
        fi
    " || true

    if [[ "${tools}" == "gui" || "${tools}" == "everything" ]]; then
        echo
        echo "── Exporting Kali GUI apps to application launcher ─────────────────"

        # Export every .desktop file found in the kali container.
        # distrobox-export is run from *inside* the container; it writes
        # host-side .desktop wrappers to ~/.local/share/applications/.
        distrobox enter --root kali -- bash -c '
            exported=0
            while IFS= read -r -d "" f; do
                [[ -f "$f" ]] || continue
                app=$(basename "$f" .desktop)
                distrobox-export --app "$app" 2>/dev/null && exported=$((exported+1)) || true
            done < <(find /usr/share/applications -name "*.desktop" -print0)
            echo "  Exported ${exported} desktop entries."
        '

        # Patch the exported wrappers so KDE groups them under "Security Tools".
        # Identify kali-exported entries by the "--name kali" distrobox argument
        # that distrobox-export injects into each Exec= line.
        _appdir="${HOME}/.local/share/applications"
        _patched=0
        for _f in "${_appdir}/"*.desktop; do
            [[ -f "${_f}" ]] || continue
            if grep -qE '\-\-name[[:space:]]+kali|-n[[:space:]]+kali' "${_f}" 2>/dev/null; then
                if grep -q '^Categories=' "${_f}"; then
                    sed -i 's|^Categories=.*|Categories=X-KythSecurity;|' "${_f}"
                else
                    printf '\nCategories=X-KythSecurity;\n' >> "${_f}"
                fi
                _patched=$((_patched+1))
            fi
        done
        echo "  Set Categories=X-KythSecurity; on ${_patched} entries."
        # Strip visibility guards so entries appear in the KDE launcher.
        for _f in "${_appdir}/"*.desktop; do
            [[ -f "${_f}" ]] || continue
            grep -qE '\-\-name[[:space:]]+kali|-n[[:space:]]+kali' "${_f}" 2>/dev/null || continue
            sed -i '/^NoDisplay[[:space:]]*=[[:space:]]*true/Id' "${_f}"
            sed -i '/^OnlyShowIn[[:space:]]*=/d' "${_f}"
            sed -i '/^NotShowIn[[:space:]]*=/d' "${_f}"
        done
        # Replace pkexec/kdesu/gksu with sudo -E for all exported kali apps.
        # polkit agents are unreachable from inside the container on Wayland;
        # passwordless sudo (configured above) is the correct mechanism here.
        _fixed_priv=0
        for _f in "${_appdir}/"*.desktop; do
            [[ -f "${_f}" ]] || continue
            grep -qE '\-\-name[[:space:]]+kali|-n[[:space:]]+kali' "${_f}" 2>/dev/null || continue
            if grep -qE 'pkexec|kdesu|gksu|gksudo' "${_f}" 2>/dev/null; then
                sed -i -E 's/(pkexec|kdesu|gksu|gksudo)[[:space:]]+/sudo -E /g' "${_f}"
                _fixed_priv=$((_fixed_priv+1))
            fi
        done
        if [[ "${_fixed_priv}" -gt 0 ]]; then
            echo "  Replaced pkexec/kdesu with sudo -E on ${_fixed_priv} entries."
        fi

        # zenmap requires root for raw-socket scans and cannot re-elevate via polkit
        # inside the container.  Route every exported zenmap launcher unconditionally
        # through kyth-distrobox-root-launch so it always runs as root.
        # Match by distrobox Exec pattern OR by kali* filename prefix so this
        # re-run is idempotent even after a previous partial patch.
        for _f in "${_appdir}/"*zenmap*.desktop; do
            [[ -f "${_f}" ]] || continue
            grep -qE '\-\-name[[:space:]]+kali|-n[[:space:]]+kali|kyth-distrobox-root-launch' "${_f}" 2>/dev/null \
                || [[ "${_f##*/}" == kali* ]] || continue
            sed -i -E 's|^Exec=.*$|Exec=kyth-distrobox-root-launch --root kali /usr/bin/zenmap|' "${_f}"
            sed -i -E 's|^TryExec=.*$|TryExec=kyth-distrobox-root-launch|' "${_f}"
            echo "  Routed ${_f##*/} → kyth-distrobox-root-launch --root kali /usr/bin/zenmap"
        done

        update-desktop-database "${_appdir}" 2>/dev/null || true
        # Rebuild KDE's application-launcher cache (update-desktop-database alone
        # is not enough — KDE maintains its own ksycoca index).
        kbuildsycoca6 --noincremental 2>/dev/null || true

        echo "  Done — Kali tools should appear under 'Security Tools' in the app launcher."
    fi

    echo
    echo "━━━ Done ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Kali box ready. Enter it with: distrobox enter --root kali"

# Export Kali Linux GUI apps to the host application launcher.
#
# Re-run this any time you install new GUI tools inside the kali container or
# if the launchers are missing after a fresh setup.  All exported apps are
# placed under the "Security" category so KDE groups them together.
[group('KythOS')]
export-kali-apps:
    #!/usr/bin/env bash
    set -euo pipefail

    if ! distrobox list --root --no-color 2>/dev/null | grep -q '^kali\b' \
        && ! distrobox list --no-color 2>/dev/null | grep -q '^kali\b'; then
        echo "No kali container found." >&2
        echo "Run 'ujust setup-kali-box gui' first." >&2
        exit 1
    fi

    echo "━━━ Exporting Kali GUI apps ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Ensure passwordless sudo is configured inside the container so root-requiring
    # tools launched from the app menu don't silently fail on a polkit prompt.
    distrobox enter --root kali -- bash -c "
        echo '${USER} ALL=(root) NOPASSWD: ALL' \
            | sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null
        sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd
    " && echo "  Configured passwordless sudo for security tools in kali." || true

    # Ensure the sudo nmap wrapper is in place (idempotent re-run of setup-kali-box logic).
    distrobox enter --root kali -- bash -c "
        if command -v nmap >/dev/null 2>&1; then
            printf '#!/bin/sh\nexec sudo /usr/bin/nmap \"\$@\"\n' \
                | sudo tee /usr/local/bin/nmap > /dev/null
            sudo chmod 755 /usr/local/bin/nmap
            echo '  Installed sudo nmap wrapper at /usr/local/bin/nmap'
        fi
    " || true

    # Export every .desktop file found in the kali container, including subdirs.
    distrobox enter --root kali -- bash -c '
        exported=0
        while IFS= read -r -d "" f; do
            [[ -f "$f" ]] || continue
            app=$(basename "$f" .desktop)
            distrobox-export --app "$app" 2>/dev/null && exported=$((exported+1)) || true
        done < <(find /usr/share/applications -name "*.desktop" -print0)
        echo "  Exported ${exported} desktop entries."
    '

    # Patch exported wrappers to use the Security category so KDE groups them.
    _appdir="${HOME}/.local/share/applications"
    _patched=0
    for _f in "${_appdir}/"*.desktop; do
        [[ -f "${_f}" ]] || continue
        if grep -qE '\-\-name[[:space:]]+kali|-n[[:space:]]+kali' "${_f}" 2>/dev/null; then
            if grep -q '^Categories=' "${_f}"; then
                sed -i 's|^Categories=.*|Categories=X-KythSecurity;|' "${_f}"
            else
                printf '\nCategories=X-KythSecurity;\n' >> "${_f}"
            fi
            _patched=$((_patched+1))
        fi
    done

    echo "  Set Categories=X-KythSecurity; on ${_patched} entries."
    # Strip visibility guards so entries appear in the KDE launcher.
    for _f in "${_appdir}/"*.desktop; do
        [[ -f "${_f}" ]] || continue
        grep -qE '\-\-name[[:space:]]+kali|-n[[:space:]]+kali' "${_f}" 2>/dev/null || continue
        sed -i '/^NoDisplay[[:space:]]*=[[:space:]]*true/Id' "${_f}"
        sed -i '/^OnlyShowIn[[:space:]]*=/d' "${_f}"
        sed -i '/^NotShowIn[[:space:]]*=/d' "${_f}"
    done
    # Replace pkexec/kdesu/gksu with sudo -E for all exported kali apps.
    _fixed_priv=0
    for _f in "${_appdir}/"*.desktop; do
        [[ -f "${_f}" ]] || continue
        grep -qE '\-\-name[[:space:]]+kali|-n[[:space:]]+kali' "${_f}" 2>/dev/null || continue
        if grep -qE 'pkexec|kdesu|gksu|gksudo' "${_f}" 2>/dev/null; then
            sed -i -E 's/(pkexec|kdesu|gksu|gksudo)[[:space:]]+/sudo -E /g' "${_f}"
            _fixed_priv=$((_fixed_priv+1))
        fi
    done
    if [[ "${_fixed_priv}" -gt 0 ]]; then
        echo "  Replaced pkexec/kdesu with sudo -E on ${_fixed_priv} entries."
    fi

    # zenmap requires root for raw-socket scans and cannot re-elevate via polkit
    # inside the container.  Route every exported zenmap launcher unconditionally
    # through kyth-distrobox-root-launch so it always runs as root.
    # Match by distrobox Exec pattern OR by kali* filename prefix so this
    # re-run is idempotent even after a previous partial patch.
    for _f in "${_appdir}/"*zenmap*.desktop; do
        [[ -f "${_f}" ]] || continue
        grep -qE '\-\-name[[:space:]]+kali|-n[[:space:]]+kali|kyth-distrobox-root-launch' "${_f}" 2>/dev/null \
            || [[ "${_f##*/}" == kali* ]] || continue
        sed -i -E 's|^Exec=.*$|Exec=kyth-distrobox-root-launch --root kali /usr/bin/zenmap|' "${_f}"
        sed -i -E 's|^TryExec=.*$|TryExec=kyth-distrobox-root-launch|' "${_f}"
        echo "  Routed ${_f##*/} → kyth-distrobox-root-launch --root kali /usr/bin/zenmap"
    done

    update-desktop-database "${_appdir}" 2>/dev/null || true
    # Rebuild KDE's application-launcher cache (update-desktop-database alone
    # is not enough — KDE maintains its own ksycoca index).
    kbuildsycoca6 --noincremental 2>/dev/null || true

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Kali tools are now exported to the application launcher under 'Security Tools'."

# ujust setup-waydroid microg     # with MicroG (open-source Play Services substitute)
[group('KythOS')]
ai-dev-status:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-ai-dev status

[group('KythOS')]
ai-dev-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-ai-dev setup

[group('KythOS')]
ai-dev-enter:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-ai-dev enter

[group('KythOS')]
ai-dev-start:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-ai-dev start

[group('KythOS')]
ai-dev-stop:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-ai-dev stop

[group('KythOS')]
ai-dev-remove:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-ai-dev remove

[group('KythOS')]
setup-waydroid image="vanilla":
    #!/usr/bin/env bash
    set -euo pipefail

    image="{{ image }}"
    case "${image}" in
        vanilla|microg) ;;
        *)
            echo "Unknown image type: ${image}" >&2
            echo "Valid options: vanilla (default), microg" >&2
            exit 1
            ;;
    esac

    # ── Step 1: install waydroid if it's not layered yet ─────────────────────
    if ! command -v waydroid >/dev/null 2>&1; then
        echo "Waydroid is not installed — layering it via rpm-ostree."
        echo "A reboot is required to activate the new layer."
        echo
        sudo rpm-ostree install --idempotent waydroid
        echo
        echo "Done. Reboot and then run 'ujust setup-waydroid' again to finish setup."
        exit 0
    fi

    # ── Step 2: check binder is available ────────────────────────────────────
    if [[ ! -e /dev/binder && ! -e /dev/anbox-binder ]]; then
        echo "WARNING: /dev/binder not found." >&2
        echo "Loading binder_linux kernel module..." >&2
        sudo modprobe binder_linux devices="binder,hwbinder,vndbinder" || {
            echo "ERROR: Could not load binder_linux. Waydroid requires binder support." >&2
            echo "Try the CachyOS kernel from System Hub -> Advanced -> Kernel, then reboot." >&2
            exit 1
        }
    fi

    # ── Step 3: initialise if not already done ───────────────────────────────
    if [[ ! -f /var/lib/waydroid/images/system.img ]]; then
        echo "Initialising Waydroid (downloading Android image ~600 MB)..."
        echo "Image type: ${image}"
        echo
        case "${image}" in
            microg)
                sudo waydroid init -s MICROG
                ;;
            *)
                sudo waydroid init
                ;;
        esac
    else
        echo "Waydroid image already present — skipping download."
    fi

    # ── Step 4: enable and start the container service ───────────────────────
    echo "Enabling waydroid-container service..."
    sudo systemctl enable --now waydroid-container

    echo
    echo "Waydroid is ready."
    echo
    echo "  waydroid show-full-ui              # launch Android full-screen"
    echo "  waydroid app install <file.apk>    # sideload an APK"
    echo "  waydroid session stop              # end the Android session"
    echo "  sudo systemctl stop waydroid-container  # shut down the container"
    echo
    if [[ "${image}" == "vanilla" ]]; then
        echo "Tip: rerun with 'ujust setup-waydroid microg' to reinstall with"
        echo "MicroG for app store access (Aurora Store, F-Droid)."
    fi
