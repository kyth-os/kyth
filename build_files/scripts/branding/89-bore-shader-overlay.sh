# shellcheck shell=bash
# ── Bore/Shader/Overlay/Backlog/EPP 91-95 — off by default ─
install -m 0755 /ctx/kyth-bore /usr/bin/kyth-bore
install -m 0755 /ctx/kyth-shader-cache-size /usr/bin/kyth-shader-cache-size
install -m 0755 /ctx/kyth-podman-overlay /usr/bin/kyth-podman-overlay
install -m 0755 /ctx/kyth-net-backlog /usr/bin/kyth-net-backlog
install -m 0755 /ctx/kyth-epp-ac /usr/bin/kyth-epp-ac
mkdir -p /etc/kyth
for toml in bore.toml shader-cache-size.toml podman-overlay.toml net-backlog.toml epp-ac.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
