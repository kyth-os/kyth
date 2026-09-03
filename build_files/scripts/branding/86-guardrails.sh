# shellcheck shell=bash
# ── Guardrails 76-80: perf gate + snapshot + telemetry + flatpak trim + windows verify ─
install -m 0755 /ctx/kyth-perf-gate /usr/bin/kyth-perf-gate
install -m 0755 /ctx/kyth-flatpak-trim /usr/bin/kyth-flatpak-trim
# Native kyth-windows-verify is installed from the hub-web-builder stage.
install -m 0755 /ctx/kyth-telemetry-opt /usr/bin/kyth-telemetry-opt
# gaming snapshot is used by kyth-gaming-master (77), no separate binary needed
mkdir -p /etc/kyth
for toml in perf-gate.toml telemetry-opt.toml flatpak-trim.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
