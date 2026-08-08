# shellcheck shell=bash
# ── Master + wine/kwin/pipewire/btrfs-autotune 61-65 ─
install -m 0755 /ctx/kyth-gaming-master /usr/bin/kyth-gaming-master
install -m 0755 /ctx/kyth-wine-sync /usr/bin/kyth-wine-sync
install -m 0755 /ctx/kyth-kwin-latency /usr/bin/kyth-kwin-latency
install -m 0755 /ctx/kyth-pipewire-gaming /usr/bin/kyth-pipewire-gaming
install -m 0755 /ctx/kyth-btrfs-autotune /usr/bin/kyth-btrfs-autotune
mkdir -p /etc/kyth
for toml in gaming-performance.toml wine-sync.toml kwin-latency.toml pipewire-gaming.toml btrfs-autotune.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
# btrfs autotune script generated on first apply, weekly timer optional
