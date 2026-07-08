# Upgrade the OS and Flatpak apps.
# Pulls the latest KythOS image via bootc and updates all Flatpak apps.

# The OS update is staged — a reboot is required to activate it.
[group('KythOS')]
kyth-upgrade:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "━━━ KythOS upgrade ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    # ── Check for rpm-ostree layers ───────────────────────────────────────────
    # bootc upgrade fails if any packages have been layered via rpm-ostree.
    # Detect this upfront and give a clear fix rather than a cryptic error.
    # requested-packages covers repo-layered packages (e.g. 'rpm-ostree install
    # waydroid' from ujust setup-waydroid); requested-local-packages covers
    # local RPM files; layered-commit-packages covers commit-layered ones.
    layered=$(rpm-ostree status --json 2>/dev/null \
        | python3 -c "import sys,json; d=json.load(sys.stdin).get('deployments', [{}])[0]; pkgs=d.get('requested-packages', []) + d.get('requested-local-packages', []) + d.get('layered-commit-packages', []); print(' '.join(pkgs) if pkgs else '')" 2>/dev/null || true)

    if [[ -n "${layered}" ]]; then
        echo "  ERROR: rpm-ostree packages are layered:" >&2
        echo "    ${layered}" >&2
        echo >&2
        echo "  These conflict with bootc upgrades. To fix:" >&2
        echo "    rpm-ostree reset     # removes all layered packages" >&2
        echo "    ujust kyth-upgrade   # then retry" >&2
        echo >&2
        if [[ " ${layered} " == *" waydroid "* ]]; then
            echo "  NOTE: 'waydroid' was layered by 'ujust setup-waydroid'." >&2
            echo "  'rpm-ostree reset' removes the Waydroid package (your Android" >&2
            echo "  data in /var/lib/waydroid is kept). After the OS update, rerun" >&2
            echo "  'ujust setup-waydroid' to layer it again." >&2
        else
            echo "  If you still need those packages, install them via Flatpak instead." >&2
        fi
        exit 1
    fi

    # ── OS update via bootc ───────────────────────────────────────────────────
    echo "── OS (bootc) ──────────────────────────────────────────────────────"
    booted_digest=$(bootc status --format json 2>/dev/null \
        | python3 -c "import sys,json; s=json.load(sys.stdin); \
          print(s.get('status',{}).get('booted',{}).get('image',{}) \
                 .get('imageDigest','unknown'))" 2>/dev/null || echo "unknown")

    sudo bootc upgrade

    staged_digest=$(bootc status --format json 2>/dev/null \
        | python3 -c "import sys,json; s=json.load(sys.stdin); \
          print(s.get('status',{}).get('staged',{}).get('image',{}) \
                 .get('imageDigest','') or '')" 2>/dev/null || echo "")

    if [[ -n "${staged_digest}" && "${staged_digest}" != "${booted_digest}" ]]; then
        os_updated=1
        echo "  ✓ New image staged and ready."
    else
        os_updated=0
        echo "  ✓ Already up to date."
    fi
    echo

    # ── Flatpak updates ───────────────────────────────────────────────────────
    echo "── Flatpak apps ────────────────────────────────────────────────────"
    if command -v flatpak >/dev/null 2>&1; then
        flatpak update -y
    else
        echo "  flatpak not available — skipping."
    fi
    echo

    # ── Summary ───────────────────────────────────────────────────────────────
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [[ "${os_updated}" -eq 1 ]]; then
        echo "  OS update staged. Reboot when ready to apply it:"
        echo "    systemctl reboot"
    else
        echo "  Everything is up to date."
    fi

# Show the currently booted image, any staged update, and rollback availability.
[group('KythOS')]
status:
    #!/usr/bin/env bash
    set -euo pipefail
    bootc status

# Rebase to a different KythOS image.
# Usage:
#   ujust rebase kyth:stable
#   ujust rebase kyth:testing
#   ujust rebase kyth:latest
#   ujust rebase                   (defaults to kyth:latest)
#
# Short form "kyth:<tag>" is expanded to ghcr.io/mrtrick37/kyth:<tag>.
# A full image reference (containing '/') is used as-is.

[group('KythOS')]
rebase image_ref="kyth:latest":
    #!/usr/bin/env bash
    set -euo pipefail
    ref="{{ image_ref }}"
    # Expand short form: "kyth:tag" or "kyth" → "ghcr.io/mrtrick37/kyth:tag"
    if [[ "$ref" != *"/"* ]]; then
        ref="ghcr.io/mrtrick37/${ref}"
    fi
    # Default to :latest if no tag was given
    if [[ "$ref" != *":"* ]]; then
        ref="${ref}:latest"
    fi
    echo "Rebasing to: ${ref}"
    echo "This will take effect on next reboot."
    sudo bootc switch "${ref}"

# Switch to a KythOS release channel.
# Channels:
#   stable   — :latest tag (main branch, recommended)
#   testing  — :testing tag (dev branch, may be unstable)
# Usage:
#   ujust switch-channel           (defaults to stable)

# ujust switch-channel testing
[group('KythOS')]
switch-channel channel="stable":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{ channel }}" in
        stable|latest) base_tag="latest" ;;
        testing)       base_tag="testing" ;;
        *)
            echo "Unknown channel: {{ channel }}" >&2
            echo "Valid channels: stable (default), testing" >&2
            exit 1
            ;;
    esac
    flavor="$(cat /usr/share/kyth/kernel-flavor 2>/dev/null || echo fedora)"
    case "${flavor}" in
        cachy) suffix="-cachy" ;;
        *) suffix="" ;;
    esac
    tag="${base_tag}${suffix}"
    echo "Switching to KythOS :${tag}..."
    sudo bootc switch "ghcr.io/mrtrick37/kyth:${tag}"
    echo "Channel switch staged. Reboot to activate."

# Switch to a kernel-flavored KythOS image.
# Default Fedora is recommended. CachyOS is an advanced variant that keeps
# rollback support by switching the whole bootc image instead of layering kernels.
# Usage:
#   ujust switch-kernel fedora
# ujust switch-kernel cachy
[group('KythOS')]
switch-kernel flavor="fedora":
    #!/usr/bin/env bash
    set -euo pipefail

    flavor="$(printf '%s' "{{ flavor }}" | tr '[:upper:]' '[:lower:]')"
    case "${flavor}" in
        fedora|stock) suffix="" ; label="Fedora" ;;
        cachy|cachyos) suffix="-cachy" ; label="CachyOS" ;;
        *)
            echo "Unknown kernel flavor: {{ flavor }}" >&2
            echo "Valid flavors: fedora, cachy" >&2
            exit 1
            ;;
    esac

    status_text="$(sudo -n bootc status 2>/dev/null || bootc status 2>/dev/null || true)"
    current_ref="$(awk '/Booted image:/ {print $NF; exit}' <<<"${status_text}")"
    current_tag=""
    if [[ "${current_ref}" == ghcr.io/mrtrick37/kyth:* ]]; then
        current_tag="${current_ref##*:}"
        current_tag="${current_tag%%@*}"
    fi
    current_tag="${current_tag:-latest}"
    case "${current_tag}" in
        testing*) channel="testing" ;;
        *) channel="latest" ;;
    esac
    if [[ "${suffix}" == "-cachy" ]]; then
        channel="testing"
    fi

    target="ghcr.io/mrtrick37/kyth:${channel}${suffix}"
    echo "Switching to ${label} kernel image: ${target}"
    echo "This stages a new deployment and keeps rollback available from the boot menu."
    if ! output="$(sudo bootc switch "${target}" 2>&1)"; then
        printf '%s\n' "${output}" >&2
        if grep -qi 'manifest unknown' <<<"${output}"; then
            echo "ERROR: ${target} is not published yet." >&2
        else
            echo "ERROR: unable to switch to ${target}." >&2
        fi
        if [[ "${channel}" == "latest" && "${suffix}" == "-cachy" ]]; then
            echo "The CachyOS kernel image may only be available on the testing channel until the stable build publishes :latest-cachy." >&2
            echo "Try: ujust switch-channel testing" >&2
            echo "Then reboot and run: ujust switch-kernel cachy" >&2
        else
            echo "Try again after the image build finishes, or check your network connection." >&2
        fi
        exit 1
    fi
    printf '%s\n' "${output}"
    echo "Kernel switch staged. Reboot to activate."

# Export Steam Flatpak game shortcuts into the host application menu.
[group('KythOS')]
export-steam-games:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-steam-game-export

# Run a game or app with the temporary performance profile wrapper.
[group('KythOS')]
game-performance +args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/game-performance {{ args }}

# Set desktop/system performance mode.

# Modes: max, gaming, performance, balanced, powersave, status
[group('KythOS')]
performance-mode mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-performance-mode "{{ mode }}"

# Quick shortcut: switch to gaming mode (EPP=performance, half-speed animations, no blur).
[group('KythOS')]
gaming-mode:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-performance-mode gaming

# Quick shortcut: restore balanced mode (EPP=balance_performance, full animations).
[group('KythOS')]
balanced-mode:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-performance-mode balanced

# Run a command with a named temporary profile.
[group('KythOS')]
game-performance-profile profile +args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/game-performance --profile "{{ profile }}" {{ args }}

# Run a game or app inside gamescope (adaptive sync + frame pacing, no HDR).
# Useful even without HDR: better VRR, FSR upscaling, frame limiter.
# Usage: ujust gamescope -- %command%
#        ujust gamescope -W 2560 -H 1440 -r 165 -- %command%

# Extra gamescope flags can be passed before the -- separator.
[group('KythOS')]
gamescope +args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/kyth-gamescope quality {{ args }}

# Run a game or app inside gamescope with HDR enabled.
# Requires an HDR-capable display and a Wayland session.
# Note: --hdr-itm-enable (SDR→HDR tone mapping) is intentionally omitted —
#       it makes SDR content look over-saturated. Add it manually if you want it:
#       ujust game-hdr --hdr-itm-enable -- %command%
# Usage: ujust game-hdr -- %command%

# ujust game-hdr -W 2560 -H 1440 -- %command%
[group('KythOS')]
game-hdr +args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/kyth-gamescope hdr {{ args }}

# Run a game or app with KythOS Gamescope presets.
# Usage:
#   ujust game-scope quality -- %command%
#   ujust game-scope hdr --fps 120 -- %command%
# ujust game-scope sharp --fsr --nested 1920x1080 --output 2560x1440 -- %command%
[group('KythOS')]
game-scope preset="quality" *args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/kyth-gamescope "{{ preset }}" {{ args }}

# Show or change the active sched-ext scheduler.
# Usage: ujust scx status | ujust scx list | ujust scx set lavd
[group('KythOS')]
scx action="status" scheduler="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "{{ scheduler }}" ]]; then
        /usr/bin/kyth-scx "{{ action }}" "{{ scheduler }}"
    else
        /usr/bin/kyth-scx "{{ action }}"
    fi

# Show or change the experimental NVMe queue tuning profile.
# Usage: ujust nvme-tuning status | ujust nvme-tuning kyth | ujust nvme-tuning default
[group('KythOS')]
nvme-tuning profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-nvme-tuning "{{ profile }}"

# Run an OpenGL app through Zink.
[group('KythOS')]
zink-run +args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/zink-run {{ args }}

# Run a game with the Vulkan low-latency layer (Anti-Lag 2 / Reflex on any GPU).
# Exposes VK_AMD_anti_lag by default; pass --reflex for VK_NV_low_latency2.
# Also works as a Steam launch option: LOW_LATENCY_LAYER=1 %command%
# Usage: ujust low-latency -- %command%

# ujust low-latency --reflex -- %command%
[group('KythOS')]
low-latency +args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/low-latency-run {{ args }}

# Print a short KythOS system/kernel tuning summary.
[group('KythOS')]
kerver:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-kerver

# Print a paste-friendly system support snapshot.
[group('KythOS')]
device-info:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-device-info

# Run the daily-driver readiness smoke check.
[group('KythOS')]
smoke-check *args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-smoke-check {{ args }}

# Run the once-per-deployment post-update confidence check now.
[group('KythOS')]
post-update-check *args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-post-update-check --force {{ args }}

# Check controller readiness for Steam Input, Bluetooth, and remapping paths.
[group('KythOS')]
controller-check:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-controller-check

# Check common suspend/resume regressions: network, audio, Bluetooth, display, Vulkan.
[group('KythOS')]
resume-check:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-resume-check

# Check NVIDIA hardware, akmod build, loaded module, and reboot-needed state.
[group('KythOS')]
nvidia-status:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-nvidia-status

# Install LACT from Flathub on an immutable system.
[group('KythOS')]
install-lact:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v flatpak >/dev/null 2>&1; then
        echo "flatpak is not available on this system." >&2
        exit 1
    fi
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub io.github.ilya_zlobintsev.LACT
    echo
    echo "LACT installed."
    echo "Launch it from the app launcher."
    echo "If you want overclocking/undervolting on AMD, review the official LACT Atomic guidance first."

# Install GPU Screen Recorder from Flathub — near-zero overhead capture and instant replay
# using AMD/NVIDIA GPU hardware encoding. Select the GPU Screen Recorder UI or Tray from
# the app menu; configure a replay buffer key in preferences for ShadowPlay-style highlights.
[group('KythOS')]
install-gpu-screen-recorder:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub com.dec05eba.gpu_screen_recorder
    echo
    echo "GPU Screen Recorder installed. Launch it from the app menu."

# Install Vesktop from Flathub — Discord with native Wayland, better screenshare, and Vencord.
[group('KythOS')]
install-vesktop:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub dev.vencord.Vesktop
    echo
    echo "Vesktop installed. Launch it from the app menu."

# Install GOverlay from Flathub for MangoHud and vkBasalt configuration.
[group('KythOS')]
install-goverlay:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub io.github.benjamimgois.goverlay
    echo
    echo "GOverlay installed. Launch it from the app menu."

# Install MangoJuice from Flathub for lightweight MangoHud configuration.
[group('KythOS')]
install-mangojuice:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub io.github.radiolamp.mangojuice
    echo
    echo "MangoJuice installed. Launch it from the app menu."

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

# Install BoxBuddy (distrobox GUI) from Flathub.
[group('KythOS')]
install-boxbuddy:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v flatpak >/dev/null 2>&1; then
        echo "flatpak is not available on this system." >&2
        exit 1
    fi
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub io.github.dvlv.boxbuddyrs
    echo
    echo "BoxBuddy installed. Launch it from the app launcher to manage your distrobox containers."

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

# Download and install the latest GE-Proton to /var/lib/kyth/ge-proton/.
[group('KythOS')]
update-ge-proton:
    #!/usr/bin/env bash
    set -euo pipefail
    sudo /usr/bin/kyth-ge-proton-update

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

    box="kyth-dev"
    image="${KYTH_DEV_IMAGE:-registry.fedoraproject.org/fedora-toolbox:44}"
    packages=(
        git gh just jq yq skopeo podman buildah
        python3 python3-pip python3-virtualenv
        ShellCheck shfmt ripgrep fd-find
        vim-enhanced neovim
    )

    if ! command -v distrobox >/dev/null 2>&1; then
        echo "ERROR: distrobox is not installed." >&2
        echo "Install it first, then rerun this recipe." >&2
        exit 1
    fi

    kyth-vscode-wallet

    if distrobox list --no-color 2>/dev/null | grep -q "^${box}\b"; then
        echo "${box} already exists."
        echo "Enter it with: distrobox enter ${box}"
        exit 0
    fi

    echo "━━━ Setting up KythOS development box ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Image: ${image}"
    echo
    distrobox create --image "${image}" --name "${box}" --yes
    distrobox enter "${box}" -- sudo dnf install -y "${packages[@]}"
    echo
    echo "Done. Enter it with: distrobox enter ${box}"
    echo "VS Code launch command: code"

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

# Set up Sunshine game streaming server.
# Sunshine lets you stream your desktop to any Moonlight client (phone, TV,
# Shield, another PC). Uses the hardware encoder on AMD/Intel/NVIDIA GPUs.
# After setup, open https://localhost:47990 in a browser to configure.
[group('KythOS')]
setup-sunshine:
    #!/usr/bin/env bash
    set -euo pipefail

    if ! command -v sunshine >/dev/null 2>&1; then
        echo "Sunshine is not installed. Installing via rpm-ostree..."
        sudo rpm-ostree install --idempotent sunshine
        echo
        echo "Reboot required to activate. Then run 'ujust setup-sunshine' again."
        exit 0
    fi

    # Enable and start Sunshine as a user service
    systemctl --user enable --now sunshine.service

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

# Add a 'Boot Windows' entry to Steam as a non-Steam game.
# Clicking it from within Steam reboots directly into Windows via EFI firmware.
# Requires a dual-boot setup with Windows on a separate EFI entry.
[group('KythOS')]
setup-boot-windows-steam:
    #!/usr/bin/env bash
    set -euo pipefail

    # Find the Windows EFI boot entry
    windows_entry=$(sudo efibootmgr -v 2>/dev/null \
        | grep -i "windows\|Windows Boot Manager" \
        | grep -oP '(?<=Boot)[0-9A-F]{4}' | head -n1)

    if [[ -z "${windows_entry}" ]]; then
        echo "ERROR: No Windows EFI boot entry found." >&2
        echo "Run 'sudo efibootmgr -v' to list available entries." >&2
        exit 1
    fi

    # Install the helper script
    tmpscript=$(mktemp)
    printf '#!/bin/bash\nexec sudo efibootmgr -n %s && sudo systemctl reboot\n' \
        "${windows_entry}" > "${tmpscript}"
    sudo install -Dm 0755 "${tmpscript}" /usr/local/bin/boot-windows
    rm -f "${tmpscript}"

    # Add sudo rule for boot-windows (passwordless reboot + efibootmgr)
    printf '%%wheel ALL=(root) NOPASSWD: /usr/sbin/efibootmgr -n *, /usr/bin/systemctl reboot\n' \
        | sudo tee /etc/sudoers.d/kyth-boot-windows >/dev/null
    sudo chmod 0440 /etc/sudoers.d/kyth-boot-windows

    echo "boot-windows helper installed."
    echo
    echo "Add it to Steam:"
    echo "  Steam → Add a game → Add a Non-Steam Game → Browse → /usr/local/bin/boot-windows"

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
install-obs:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub com.obsproject.Studio
    flatpak override --user --env=OBS_VKCAPTURE=1 com.obsproject.Studio || true
    echo
    echo "OBS Studio installed. Launch it from the app menu."
    echo "obs-vkcapture is enabled for Vulkan/OpenGL game capture."

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
install-itch:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub io.itch.itch
    echo
    echo "Itch.io installed. Launch it from the app menu."

# Install RetroArch — multi-system emulator frontend (NES, SNES, PS1, N64, ...).
[group('KythOS')]
install-retroarch:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub org.libretro.RetroArch
    echo
    echo "RetroArch installed. Launch it from the app menu."
    echo "Tip: download cores from inside RetroArch: Main Menu → Load Core → Download a Core."

# Install Piper — GUI for configuring gaming mice (DPI, buttons, LEDs).

# Uses the Flatpak which bundles ratbagd — no rpm-ostree layering required.
[group('KythOS')]
install-piper:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub org.freedesktop.Piper
    echo
    echo "Piper installed. Launch it from the app menu."

# Install OpenRGB — unified RGB lighting control for motherboards, RAM, GPUs,
# fans and peripherals. Uses the Flatpak with --device=all for hardware access.
# Note: SMBus/i2c access (RAM RGB, some motherboard headers) may need the i2c
# kernel modules loaded. If devices are missing, run:

# sudo modprobe i2c-dev i2c-piix4    (or the appropriate module for your board)
[group('KythOS')]
install-openrgb:
    #!/usr/bin/env bash
    set -euo pipefail
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub org.openrgb.OpenRGB
    # Grant access to USB and i2c/SMBus devices
    flatpak override --user --device=all org.openrgb.OpenRGB
    echo
    echo "OpenRGB installed. Launch it from the app menu."
    echo "If RGB RAM or motherboard headers are missing, load i2c kernel modules:"
    echo "  sudo modprobe i2c-dev i2c-piix4"

# Show the current KythOS Secure Boot enrollment state.
#
# This is safe to run any time. It does not change firmware settings.
[group('KythOS')]
secureboot-status:
    #!/usr/bin/env bash
    set -euo pipefail

    CERT_PEM="/usr/share/kyth/secureboot/kyth-secureboot.cer"
    CERT_DER="/usr/share/kyth/secureboot/kyth-secureboot.der"
    FLAG="/var/lib/kyth/mok-enrolled"

    echo "━━━ KythOS Secure Boot Status ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    if [[ -f "${CERT_DER}" ]]; then
        echo "  Certificate: present at ${CERT_DER}"
    elif [[ -f "${CERT_PEM}" ]]; then
        echo "  Certificate: present as PEM at ${CERT_PEM}"
    else
        echo "  Certificate: missing — this image was built without Secure Boot support"
    fi

    if mokutil --sb-state 2>/dev/null; then
        :
    else
        echo "  Firmware state: unavailable — boot this system in UEFI mode to use MOK enrollment"
    fi

    if mokutil --list-enrolled 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS MOK: enrolled"
    else
        echo "  KythOS MOK: not enrolled"
    fi

    if mokutil --list-new 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  Pending enrollment: staged for next reboot"
    else
        echo "  Pending enrollment: none detected"
    fi

    if [[ -f "${FLAG}" ]]; then
        echo "  First-boot service marker: ${FLAG}"
    else
        echo "  First-boot service marker: not set"
    fi

# Manually enroll the KythOS Secure Boot key (MOK) into UEFI firmware.
#
# The default Fedora kernel path does not need this key. Run this before
# enabling Secure Boot for the advanced CachyOS kernel image, or after a
# firmware reset if the KythOS MOK was removed.
#
# After running, reboot and enter the password you chose at the MokManager screen.
[group('KythOS')]
enroll-secureboot:
    #!/usr/bin/env bash
    set -euo pipefail

    CERT_PEM="/usr/share/kyth/secureboot/kyth-secureboot.cer"
    CERT_DER="/usr/share/kyth/secureboot/kyth-secureboot.der"

    if [[ ! -f "${CERT_PEM}" && ! -f "${CERT_DER}" ]]; then
        echo "KythOS Secure Boot certificate not found." >&2
        echo "This image was built without Secure Boot support." >&2
        exit 1
    fi

    if [[ ! -f "${CERT_DER}" ]]; then
        CERT_DER="$(mktemp --tmpdir kyth-secureboot.XXXXXX.der)"
        openssl x509 -in "${CERT_PEM}" -outform DER -out "${CERT_DER}"
    fi

    echo "━━━ KythOS Secure Boot Enrollment ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    SB_STATE="$(mokutil --sb-state 2>/dev/null || true)"
    if echo "${SB_STATE}" | grep -q "SecureBoot enabled"; then
        echo "  Secure Boot is currently enabled."
    else
        echo "  Secure Boot is currently disabled or unavailable."
        echo "  That is OK — for existing installs, staging the key before enabling"
        echo "  Secure Boot is the safest path."
    fi
    echo

    if mokutil --list-enrolled 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS Secure Boot key is already enrolled. Nothing to do."
        exit 0
    fi

    if mokutil --list-new 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS Secure Boot key is already staged for enrollment."
        echo "  Reboot, complete the blue MokManager prompt, then enable Secure Boot"
        echo "  in firmware if it is not enabled already."
        exit 0
    fi

    echo "  Enrolling KythOS Secure Boot certificate."
    echo "  Choose a one-time confirmation password — you will enter it at the"
    echo "  MokManager screen on next reboot to complete enrollment."
    echo
    read -rsp "  Enrollment password: " MOK_PASS
    echo
    read -rsp "  Confirm password:    " MOK_PASS2
    echo
    if [[ "${MOK_PASS}" != "${MOK_PASS2}" ]]; then
        echo "  Passwords do not match." >&2
        exit 1
    fi

    echo "${MOK_PASS}" | sudo mokutil --import "${CERT_DER}" --stdin-passwd

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  MOK enrollment staged."
    echo "  Next steps:"
    echo "    1. Reboot."
    echo "    2. At the blue MokManager screen, choose Enroll MOK / Continue / Yes."
    echo "    3. Enter the password you just chose, then reboot."
    echo "    4. Enable Secure Boot in UEFI/BIOS if it is not enabled already."
    echo "    5. Boot KythOS and run: ujust secureboot-status"

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

    sudo rm -f /var/lib/kyth/hw-setup-done
    sudo akmods --force --kernels "$(uname -r)"

    # Keep nouveau available if compilation fails. Only switch the next boot to
    # the proprietary driver after its module has compiled successfully.
    KARGS="rd.driver.blacklist=nouveau,nova_core modprobe.blacklist=nouveau,nova_core nvidia-drm.modeset=1"
    sudo grubby --update-kernel=ALL --args="${KARGS}" 2>/dev/null || \
        echo "  (grubby: non-fatal — kargs.d applies on next deployment)"

    sudo touch /var/lib/kyth/hw-setup-done

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  NVIDIA driver compiled successfully."
    echo "  Reboot to activate:"
    echo "    systemctl reboot"

# Fix the clock skew between KythOS and a dual-booted Windows install.
#
# Windows stores the hardware clock as local time; Linux stores it as UTC.
# After booting KythOS, Windows sees the RTC in UTC and shows the wrong time.
# This tells KythOS to treat the RTC as local time — matching Windows' expectation.
# NTP sync continues working normally; only the RTC interpretation changes.
# Run once. No reboot required.
[group('KythOS')]
fix-dualboot-clock:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Dual-Boot Clock Fix ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Setting hardware clock to local time (Windows-compatible mode)..."
    sudo timedatectl set-local-rtc 1 --adjust-system-clock
    echo
    timedatectl | grep -E "Local time|RTC time|RTC in local TZ|NTP"
    echo
    echo "  ✓ Done. Windows will now show the correct time after booting from KythOS."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Open KDE Autostart settings — manage apps that launch at login.
# Equivalent to Task Manager → Startup tab on Windows.
[group('KythOS')]
startup-apps:
    #!/usr/bin/env bash
    set -euo pipefail
    kcmshell6 autostart 2>/dev/null \
        || systemsettings 2>/dev/null \
        || { echo "Open System Settings → Autostart to manage login apps."; exit 1; }

# Install Microsoft core fonts into ~/.local/share/fonts.
# Fixes font substitution in LibreOffice when opening Word/Excel/PowerPoint files.
# Installs: Times New Roman, Arial, Courier New, Verdana, Georgia, Impact, and more.
# Uses p7zip to extract — no cabextract or rpm-ostree layer required.
[group('KythOS')]
install-ms-fonts:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Microsoft Fonts ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Installing Microsoft core fonts to ~/.local/share/fonts/msttcorefonts"
    echo "  (Times New Roman, Arial, Courier New, Verdana, Georgia, Impact, ...)"
    echo
    fonts_dir="${HOME}/.local/share/fonts/msttcorefonts"
    mkdir -p "${fonts_dir}"
    tmp=$(mktemp -d)
    trap 'rm -rf "${tmp}"' EXIT
    base_url="https://sourceforge.net/projects/corefonts/files/the%20fonts/final"
    fonts=(
        andale32.exe arial32.exe arialb32.exe comic32.exe courie32.exe
        georgi32.exe impact32.exe times32.exe trebuc32.exe verdan32.exe
        webdin32.exe
    )
    ok=0; failed=0
    for font in "${fonts[@]}"; do
        dest="${tmp}/${font}"
        printf "  %-20s " "${font}"
        if curl -fsSL --retry 2 -o "${dest}" "${base_url}/${font}/download" 2>/dev/null; then
            extracted=$(7z e "${dest}" -o"${tmp}/extracted_${font}" '*.ttf' '*.TTF' -r -y \
                2>/dev/null | grep -c "Extracting" || true)
            find "${tmp}/extracted_${font}" \( -name '*.ttf' -o -name '*.TTF' \) \
                -exec cp -n {} "${fonts_dir}/" \; 2>/dev/null || true
            actual=$(find "${tmp}/extracted_${font}" \( -name '*.ttf' -o -name '*.TTF' \) \
                2>/dev/null | wc -l)
            if [[ "${actual}" -gt 0 ]]; then
                echo "✓ (${actual} font(s))"
                ok=$((ok+1))
            else
                echo "skip (no .ttf found)"
                failed=$((failed+1))
            fi
        else
            echo "skip (download failed)"
            failed=$((failed+1))
        fi
    done
    fc-cache -f "${fonts_dir}" 2>/dev/null || true
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [[ "${ok}" -gt 0 ]]; then
        echo "  ✓ Installed fonts from ${ok} package(s). Restart LibreOffice to apply."
        if [[ "${failed}" -gt 0 ]]; then
            echo "  ⚠ ${failed} package(s) skipped."
        fi
    else
        echo "  ✗ No fonts installed. Check your network connection and try again." >&2
        exit 1
    fi

# Set up a printer — enables CUPS and opens KDE Printer Settings.
# Most USB and network printers are detected automatically.
# If your printer is not listed, connect it via USB or use Add Printer → Network.
# For stubborn printers, the CUPS web interface is at http://localhost:631
[group('KythOS')]
setup-printer:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Printer Setup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Enabling CUPS print service..."
    sudo systemctl enable --now cups
    echo "  ✓ CUPS is running."
    echo
    echo "  Opening KDE Printer Settings..."
    echo "  Tip: if your printer is not listed, click Add Printer."
    echo "  For network printers, choose Enter URI and type its IP address."
    echo
    echo "  Advanced: CUPS web interface → http://localhost:631"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kcmshell6 kcm_printer_manager 2>/dev/null \
        || systemsettings 2>/dev/null &

# Check for and apply firmware updates via fwupd.
[group('KythOS')]
firmware-update:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Refreshing firmware metadata..."
    fwupdmgr refresh --force
    echo
    echo "Checking for firmware updates..."
    fwupdmgr get-updates || true
    echo
    echo "Applying available firmware updates..."
    fwupdmgr update

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
