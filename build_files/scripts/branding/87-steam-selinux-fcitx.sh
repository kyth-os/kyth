# shellcheck shell=bash
# ── Steam/SELinux/Fcitx/HDR/Audit 81-85 — off by default ─
install -m 0755 /ctx/kyth-steam-deadzone /usr/bin/kyth-steam-deadzone
install -m 0755 /ctx/kyth-selinux-gaming /usr/bin/kyth-selinux-gaming
install -m 0755 /ctx/kyth-fcitx-latency /usr/bin/kyth-fcitx-latency
install -m 0755 /ctx/kyth-hdr-store /usr/bin/kyth-hdr-store
install -m 0755 /ctx/kyth-system-audit /usr/bin/kyth-system-audit
mkdir -p /etc/kyth
for toml in steam-deadzone.toml selinux-gaming.toml fcitx-latency.toml hdr-store.toml; do
    [[ -f /etc/kyth/$toml ]] || true
done
