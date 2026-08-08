# shellcheck shell=bash
# ── Gaming perf 56-60: ananicy/zswap/gpu/sched/readahead ─
install -m 0755 /ctx/kyth-ananicy /usr/bin/kyth-ananicy
install -m 0755 /ctx/kyth-zswap /usr/bin/kyth-zswap
install -m 0755 /ctx/kyth-gpu-power /usr/bin/kyth-gpu-power
install -m 0755 /ctx/kyth-sched-latency /usr/bin/kyth-sched-latency
install -m 0755 /ctx/kyth-readahead /usr/bin/kyth-readahead
install -m 0755 /ctx/kyth-readahead-run /usr/bin/kyth-readahead-run
mkdir -p /etc/kyth
for toml in ananicy.toml zswap.toml gpu-power.toml sched-latency.toml readahead.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
