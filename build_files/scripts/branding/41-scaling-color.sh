# shellcheck shell=bash
# ── Scaling + ICC color ────────────────────────────────────────────────────
# ICC drop dir for optional profiles; kyth-apply-scaling writes kscreen scales
# from ~/.config/kyth/scaling.toml at runtime.
if command -v colord >/dev/null 2>&1; then
	mkdir -p /usr/share/color/icc/kyth
fi
install -m 0755 /ctx/kyth-apply-scaling /usr/bin/kyth-apply-scaling
install -m 0755 /ctx/kyth-apply-display-hdr /usr/bin/kyth-apply-display-hdr
