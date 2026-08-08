# shellcheck shell=bash
# ── Clean perf 46-50: kargs/io/net/uksmd/journal — declarative, zero-cost when off ─
install -m 0755 /ctx/kyth-kargs-apply /usr/bin/kyth-kargs-apply
install -m 0755 /ctx/kyth-io-tune /usr/bin/kyth-io-tune
install -m 0755 /ctx/kyth-net-tune /usr/bin/kyth-net-tune
install -m 0755 /ctx/kyth-uksmd /usr/bin/kyth-uksmd
install -m 0755 /ctx/kyth-journal-tune /usr/bin/kyth-journal-tune
# idempotent applies on boot — only writes drop-ins if TOML says enabled
# no enable needed: helpers are on-demand via Hub/ujust, no daemon residue when off
mkdir -p /etc/kyth
# seed defaults (balanced/off) without overwriting user choices
for toml in kargs.toml io.toml net-latency.toml uksmd.toml journal.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
