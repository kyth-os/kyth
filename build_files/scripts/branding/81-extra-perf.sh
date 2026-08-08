# shellcheck shell=bash
# ── Extra perf 51-55: THP/mimalloc/IRQ/btrfs/trim — declarative, zero-cost when off ─
install -m 0755 /ctx/kyth-thp-tune /usr/bin/kyth-thp-tune
install -m 0755 /ctx/kyth-mimalloc /usr/bin/kyth-mimalloc
install -m 0755 /ctx/kyth-mimalloc-run /usr/bin/kyth-mimalloc-run
install -m 0755 /ctx/kyth-irq-tune /usr/bin/kyth-irq-tune
install -m 0755 /ctx/kyth-btrfs-tune /usr/bin/kyth-btrfs-tune
install -m 0755 /ctx/kyth-trim-tune /usr/bin/kyth-trim-tune
mkdir -p /etc/kyth
for toml in thp.toml mimalloc.toml irq.toml btrfs-perf.toml trim.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
# mimalloc package optional — wrapper falls back gracefully if missing
# thp/irq/btrfs/trim are all drop-in only, no daemon when off
