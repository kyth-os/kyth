# shellcheck shell=bash
# ── PSI/NUMA/PCIe/THP/HDR 86-90 — off by default ─
install -m 0755 /ctx/kyth-psi-gaming /usr/bin/kyth-psi-gaming
install -m 0755 /ctx/kyth-numa /usr/bin/kyth-numa
install -m 0755 /ctx/kyth-pcie /usr/bin/kyth-pcie
install -m 0755 /ctx/kyth-thp-collapse /usr/bin/kyth-thp-collapse
install -m 0755 /ctx/kyth-hdr-per-game /usr/bin/kyth-hdr-per-game
mkdir -p /etc/kyth
for toml in psi.toml numa.toml pcie.toml thp-collapse.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
