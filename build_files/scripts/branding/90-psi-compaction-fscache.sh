# shellcheck shell=bash
# ── PSI poll / Compaction / FSCache 96-98 — off by default ─
install -m 0755 /ctx/kyth-psi-poll /usr/bin/kyth-psi-poll
install -m 0755 /ctx/kyth-compaction /usr/bin/kyth-compaction
install -m 0755 /ctx/kyth-fscache /usr/bin/kyth-fscache
mkdir -p /etc/kyth
for toml in psi-poll.toml compaction.toml fscache.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
