# shellcheck shell=bash
# ── Boot/OOM/Shader/CFS/Audit 66-70 — zero-cost when off ─
install -m 0755 /ctx/kyth-boot-timeout /usr/bin/kyth-boot-timeout
install -m 0755 /ctx/kyth-oom-gaming /usr/bin/kyth-oom-gaming
install -m 0755 /ctx/kyth-shader-tmpfs /usr/bin/kyth-shader-tmpfs
install -m 0755 /ctx/kyth-gaming-cfs /usr/bin/kyth-gaming-cfs
install -m 0755 /ctx/kyth-gaming-audit /usr/bin/kyth-gaming-audit
mkdir -p /etc/kyth
for toml in loader.toml oom-gaming.toml shader-tmpfs.toml gaming-cfs.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
# gaming slice already installed via 27-performance-daemons; audit is on-demand
