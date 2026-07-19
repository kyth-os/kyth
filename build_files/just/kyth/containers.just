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