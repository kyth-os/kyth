# shellcheck shell=bash
# ── KythOS-native just provider (Fedora base) ────────────────────────────────
# Universal Blue ships the `ujust` binary and the /usr/share/ublue-os/just
# tree; the Fedora base ships neither. When ujust is already present (ublue
# base, or a BASE_IMAGE override that provides it) there is nothing to do —
# 31-ujust-recipes.sh owns recipe delivery there.
#
# Otherwise install the KythOS recipes into a KythOS-owned tree and provide a
# `ujust` shim so the documented `ujust <recipe>` contract (e.g.
# `ujust kyth-upgrade`, `ujust rebase kyth:testing`) keeps working. The shim
# is deliberately thin: system recipes live in the system justfile, and the
# `just` binary itself is installed by packages/18.
if ! command -v ujust >/dev/null 2>&1; then
	mkdir -p /usr/share/kyth/just
	cp /ctx/just/kyth.just /usr/share/kyth/just/75-kyth.just
	# kyth.just imports its per-domain recipe files from kyth/ next to itself
	# (just resolves imports relative to the importing file), so that
	# directory ships alongside it here — mirroring 31's ublue-base layout.
	cp -r /ctx/just/kyth /usr/share/kyth/just/kyth
	cat >/usr/share/kyth/justfile <<'JUSTFILEEOF'
# KythOS system justfile (Fedora base; no Universal Blue just tree present).
import? "/usr/share/kyth/just/75-kyth.just"
JUSTFILEEOF
	install -Dm 0755 /dev/stdin /usr/bin/ujust <<'UJUSTEOF'
#!/bin/sh
# KythOS ujust shim: run the KythOS system recipes via just.
# On ublue-based images this file is never installed — the real ujust wins.
exec /usr/bin/just --justfile /usr/share/kyth/justfile "$@"
UJUSTEOF
fi
