# shellcheck shell=bash
# ── net/vm 126-130 — off by default ─
install -m 0755 /ctx/kyth-rmem-max /usr/bin/kyth-rmem-max
install -m 0755 /ctx/kyth-wmem-max /usr/bin/kyth-wmem-max
install -m 0755 /ctx/kyth-aio-max /usr/bin/kyth-aio-max
install -m 0755 /ctx/kyth-overcommit-memory /usr/bin/kyth-overcommit-memory
install -m 0755 /ctx/kyth-netdev-budget /usr/bin/kyth-netdev-budget
mkdir -p /etc/kyth
for toml in rmem-max.toml wmem-max.toml aio-max.toml overcommit-memory.toml netdev-budget.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
