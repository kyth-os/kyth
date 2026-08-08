# shellcheck shell=bash
# ── TCP/fs 116-120 — off by default ─
install -m 0755 /ctx/kyth-tcp-fastopen /usr/bin/kyth-tcp-fastopen
install -m 0755 /ctx/kyth-tcp-mtu-probing /usr/bin/kyth-tcp-mtu-probing
install -m 0755 /ctx/kyth-dirty-expire /usr/bin/kyth-dirty-expire
install -m 0755 /ctx/kyth-file-max /usr/bin/kyth-file-max
install -m 0755 /ctx/kyth-perf-cpu /usr/bin/kyth-perf-cpu
mkdir -p /etc/kyth
for toml in tcp-fastopen.toml tcp-mtu-probing.toml dirty-expire.toml file-max.toml perf-cpu.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
