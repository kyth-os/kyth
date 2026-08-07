# Shared helpers (e.g. _install-flatpak). `just` deduplicates repeated imports,
# so this stays valid both standalone and when pulled in via kyth.just.
import 'common.just'
import 'gaming/games.just'
import 'gaming/proton.just'
import 'gaming/performance.just'
import 'gaming/hardware.just'

# Gaming parity — Windows switchers land here first. Show the stack KythOS ships.
[group('KythOS')]
gaming-stack-status:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ KythOS Gaming Stack ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Proton-CachyOS: $(cat /usr/share/steam/compatibilitytools.d/*/compatibilitytool.vdf 2>/dev/null | grep -m1 version | head -n1 || echo 'not installed — run: just update-proton-cachyos')"
    echo "  MangoHud:       $(command -v mangohud >/dev/null 2>&1 && mangohud --version 2>/dev/null | head -n1 || echo 'not installed')"
    echo "  vkBasalt:       $(test -f /usr/share/vkBasalt/vkBasalt.conf 2>/dev/null && echo 'installed' || echo 'not installed')"
    echo "  Gamescope:      $(command -v gamescope >/dev/null 2>&1 && echo 'installed' || echo 'not installed')"
    echo "  System Hub → Gaming → Dashboard shows the same checks with fix buttons."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
