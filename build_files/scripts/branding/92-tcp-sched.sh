# shellcheck shell=bash
# ── TCP/sched tunables 106-110 — off by default ─
install -m 0755 /ctx/kyth-tcp-ecn /usr/bin/kyth-tcp-ecn
install -m 0755 /ctx/kyth-tcp-slow-start /usr/bin/kyth-tcp-slow-start
install -m 0755 /ctx/kyth-sched-autogroup /usr/bin/kyth-sched-autogroup
install -m 0755 /ctx/kyth-sched-nr-migrate /usr/bin/kyth-sched-nr-migrate
install -m 0755 /ctx/kyth-page-cluster /usr/bin/kyth-page-cluster
mkdir -p /etc/kyth
for toml in tcp-ecn.toml tcp-slow-start.toml sched-autogroup.toml sched-nr-migrate.toml page-cluster.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
