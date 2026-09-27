# shellcheck shell=bash
# ── Guardrails 76-80: perf gate + snapshot + telemetry + flatpak trim + windows verify ─
install -m 0755 /ctx/kyth-perf-gate /usr/bin/kyth-perf-gate
install -m 0755 /ctx/kyth-flatpak-trim /usr/bin/kyth-flatpak-trim
# kyth-windows-verify has no legacy-fixture install line here (unlike its
# siblings in this file): it is installed solely as one of the tunable
# dispatcher's 94 symlinks in the Dockerfile's final RUN block, same as
# every other tunable. See build_files/scripts/tunable-dispatcher.sh's
# header for why a standalone binary at this path is deliberately avoided.
install -m 0755 /ctx/kyth-telemetry-opt /usr/bin/kyth-telemetry-opt
# gaming snapshot is used by kyth-gaming-master (77), no separate binary needed
mkdir -p /etc/kyth
for toml in perf-gate.toml telemetry-opt.toml flatpak-trim.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
