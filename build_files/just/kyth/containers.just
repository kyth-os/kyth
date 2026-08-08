# Shared helpers (e.g. _install-flatpak). `just` deduplicates repeated imports,
# so this stays valid both standalone and when pulled in via kyth.just.
import 'common.just'
import 'containers/kali.just'
import 'containers/waydroid.just'

# Install BoxBuddy (distrobox GUI) from Flathub.
[group('KythOS')]
install-boxbuddy: (_install-flatpak "io.github.dvlv.boxbuddyrs" "BoxBuddy")
    @echo "Use it to manage your distrobox containers."

[group('KythOS')]
[private]
_ai-dev cmd:
    #!/usr/bin/env bash
    set -euo pipefail
    kyth-ai-dev {{ cmd }}

[group('KythOS')]
ai-dev-status: (_ai-dev "status")

[group('KythOS')]
ai-dev-setup: (_ai-dev "setup")

[group('KythOS')]
ai-dev-enter: (_ai-dev "enter")

[group('KythOS')]
ai-dev-start: (_ai-dev "start")

[group('KythOS')]
ai-dev-stop: (_ai-dev "stop")

[group('KythOS')]
ai-dev-remove: (_ai-dev "remove")

# Podman btrfs (podman-btrfs.toml) — btrfs driver when on btrfs
[group('KythOS')]
podman-btrfs mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-podman-btrfs "{{ mode }}"

# Distrobox cache tmpfs (distrobox-cache.toml) — 4G ccache+cargo
[group('KythOS')]
distrobox-cache mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-distrobox-cache "{{ mode }}"
