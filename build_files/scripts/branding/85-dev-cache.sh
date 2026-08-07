# shellcheck shell=bash
# ── Dev container cache 71-75 — tmpfs/pre-fetch off by default ─
install -m 0755 /ctx/kyth-podman-btrfs /usr/bin/kyth-podman-btrfs
install -m 0755 /ctx/kyth-distrobox-cache /usr/bin/kyth-distrobox-cache
install -m 0755 /ctx/kyth-sccache /usr/bin/kyth-sccache
install -m 0755 /ctx/kyth-flatpak-prefetch /usr/bin/kyth-flatpak-prefetch
install -m 0755 /ctx/kyth-work-cache /usr/bin/kyth-work-cache
mkdir -p /etc/kyth
for toml in podman-btrfs.toml distrobox-cache.toml sccache.toml flatpak-prefetch.toml work-cache.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
