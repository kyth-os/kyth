#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── Polkit: systemd flatpak service authorization for wheel group ──────────────
write_config /usr/share/polkit-1/rules.d/99-kyth-systemd.rules <<'POLKITEOF'
/* Allow users in the wheel group to manage specific KythOS systemd services without password authentication */
polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.systemd1.manage-units" &&
        subject.isInGroup("wheel")) {
        var unit = action.lookup("unit");
        if (unit == "kyth-default-flatpaks.service" ||
            unit == "kyth-flathub-setup.service") {
            var verb = action.lookup("verb");
            if (verb == "start" || verb == "stop" || verb == "restart") {
                return polkit.Result.YES;
            }
        }
    }
});
POLKITEOF
