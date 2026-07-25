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
