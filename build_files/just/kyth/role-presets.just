# Role presets — progressive vs Bazzite/Nobara which ship one image
# Kyth keeps base lean (universal) + opt-in presets via ujust, not rebase
[group('KythOS')]
apply-preset preset:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{ preset }}" in
        everyday) echo "Applying everyday preset (balanced)"; kyth-apply-role-preset everyday ;;
        gaming) echo "Applying gaming preset (SCX + MangoHud)"; kyth-apply-role-preset gaming ;;
        dev) echo "Applying dev preset (containers + AI)"; kyth-apply-role-preset dev ;;
        creator) echo "Applying creator preset (Davinci + OBS)"; kyth-apply-role-preset creator ;;
        *) echo "Unknown preset: {{ preset }} (everyday/gaming/dev/creator)" >&2; exit 1 ;;
    esac

[group('KythOS')]
list-presets:
    @echo "Available presets: everyday, gaming, dev, creator"
