# shellcheck shell=bash
# ── TCP/VM 111-115 — off by default ─
install -m 0755 /ctx/kyth-tcp-retries2 /usr/bin/kyth-tcp-retries2
install -m 0755 /ctx/kyth-tcp-keepalive /usr/bin/kyth-tcp-keepalive
install -m 0755 /ctx/kyth-sched-child /usr/bin/kyth-sched-child
install -m 0755 /ctx/kyth-vm-stat /usr/bin/kyth-vm-stat
install -m 0755 /ctx/kyth-numa-balancing /usr/bin/kyth-numa-balancing
mkdir -p /etc/kyth
for toml in tcp-retries2.toml tcp-keepalive.toml sched-child.toml vm-stat.toml numa-balancing.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
