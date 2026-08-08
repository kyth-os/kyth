# shellcheck shell=bash
# ── vm/fs/net 121-125 — off by default ─
install -m 0755 /ctx/kyth-swappiness /usr/bin/kyth-swappiness
install -m 0755 /ctx/kyth-tcp-fin-timeout /usr/bin/kyth-tcp-fin-timeout
install -m 0755 /ctx/kyth-somaxconn /usr/bin/kyth-somaxconn
install -m 0755 /ctx/kyth-inotify-watches /usr/bin/kyth-inotify-watches
install -m 0755 /ctx/kyth-min-free-kbytes /usr/bin/kyth-min-free-kbytes
mkdir -p /etc/kyth
for toml in swappiness.toml tcp-fin-timeout.toml somaxconn.toml inotify-watches.toml min-free-kbytes.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
