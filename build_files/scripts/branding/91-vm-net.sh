# shellcheck shell=bash
# ── VM/net tunables 101-105 — off by default ─
install -m 0755 /ctx/kyth-vm-watermark /usr/bin/kyth-vm-watermark
install -m 0755 /ctx/kyth-tcp-notsent /usr/bin/kyth-tcp-notsent
install -m 0755 /ctx/kyth-max-map-count /usr/bin/kyth-max-map-count
install -m 0755 /ctx/kyth-dirty-ratio /usr/bin/kyth-dirty-ratio
install -m 0755 /ctx/kyth-vfs-cache /usr/bin/kyth-vfs-cache
mkdir -p /etc/kyth
for toml in vm-watermark.toml tcp-notsent.toml max-map-count.toml dirty-ratio.toml vfs-cache.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
