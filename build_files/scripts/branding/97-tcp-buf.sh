# shellcheck shell=bash
# ── tcp/buf 131-135 — off by default ─
install -m 0755 /ctx/kyth-rmem-default /usr/bin/kyth-rmem-default
install -m 0755 /ctx/kyth-wmem-default /usr/bin/kyth-wmem-default
install -m 0755 /ctx/kyth-tcp-window-scaling /usr/bin/kyth-tcp-window-scaling
install -m 0755 /ctx/kyth-tcp-sack /usr/bin/kyth-tcp-sack
install -m 0755 /ctx/kyth-tcp-timestamps /usr/bin/kyth-tcp-timestamps
mkdir -p /etc/kyth
for toml in rmem-default.toml wmem-default.toml tcp-window-scaling.toml tcp-sack.toml tcp-timestamps.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
