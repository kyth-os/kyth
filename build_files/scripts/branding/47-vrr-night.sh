# shellcheck shell=bash
# ── VRR + Night color scheduler ──────────────────────────────────────────
# Installs kyth-apply-vrr which writes [Wayland] VrrPolicy + [NightColor]
# from ~/.config/kyth/vrr.toml (and best-effort per-output via kscreen-doctor).
install -m 0755 /ctx/kyth-apply-vrr /usr/bin/kyth-apply-vrr
