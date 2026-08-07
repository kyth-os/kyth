# Shared variables (kyth_registry). `just` deduplicates repeated imports,
# so this stays valid both standalone and when pulled in via kyth.just.
import 'common.just'

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

    sudo kyth-safe-upgrade

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

# Show the digest-aware boot health and quarantined update records.
[group('KythOS')]
update-health:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-boot-health status

# Explicitly allow a previously quarantined digest to be tried again.
# Usage: ujust retry-quarantined-update sha256:...
[group('KythOS')]
retry-quarantined-update digest:
    #!/usr/bin/env bash
    set -euo pipefail
    sudo kyth-boot-health clear-quarantine --digest "{{ digest }}"
    echo "Cleared quarantine for {{ digest }}. The update watcher may stage it again."

# Rebase to a different KythOS image.
# Usage:
#   ujust rebase kyth:stable
#   ujust rebase kyth:testing
#   ujust rebase kyth:latest
#   ujust rebase                   (defaults to kyth:latest)
#
# Short form "kyth:<tag>" is expanded to {{ kyth_registry }}/kyth:<tag>.
# A full image reference (containing '/') is used as-is.

[group('KythOS')]
rebase image_ref="kyth:latest":
    #!/usr/bin/env bash
    set -euo pipefail
    ref="{{ image_ref }}"
    # Expand short form: "kyth:tag" or "kyth" → "{{ kyth_registry }}/kyth:tag"
    if [[ "$ref" != *"/"* ]]; then
        ref="{{ kyth_registry }}/${ref}"
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
    sudo bootc switch "{{ kyth_registry }}/kyth:${tag}"
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
    if [[ "${current_ref}" == {{ kyth_registry }}/kyth:* ]]; then
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

    target="{{ kyth_registry }}/kyth:${channel}${suffix}"
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

# Flatpak trim — weekly unused runtime removal
[group('KythOS')]
flatpak-trim mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-flatpak-trim "{{ mode }}"
