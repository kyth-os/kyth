# shellcheck shell=bash
# ── busy/tcp 136-140 — off by default ─
install -m 0755 /ctx/kyth-busy-read /usr/bin/kyth-busy-read
install -m 0755 /ctx/kyth-busy-poll /usr/bin/kyth-busy-poll
install -m 0755 /ctx/kyth-tcp-no-metrics-save /usr/bin/kyth-tcp-no-metrics-save
install -m 0755 /ctx/kyth-tcp-retries1 /usr/bin/kyth-tcp-retries1
install -m 0755 /ctx/kyth-tcp-orphan-retries /usr/bin/kyth-tcp-orphan-retries
mkdir -p /etc/kyth
for toml in busy-read.toml busy-poll.toml tcp-no-metrics-save.toml tcp-retries1.toml tcp-orphan-retries.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
