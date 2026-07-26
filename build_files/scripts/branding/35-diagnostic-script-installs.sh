# shellcheck shell=bash
# ── Read-only diagnostic/health-check scripts ──────────────────────────────────
# kyth-smoke-check is installed as a kyth-shared console entry point.
install -m 0755 /ctx/kyth-post-update-check /usr/bin/kyth-post-update-check
install -m 0755 /ctx/kyth-firstboot-app-status /usr/bin/kyth-firstboot-app-status
install -m 0755 /ctx/kyth-controller-check /usr/bin/kyth-controller-check
install -m 0755 /ctx/kyth-resume-check /usr/bin/kyth-resume-check
install -m 0755 /ctx/kyth-nvidia-status /usr/bin/kyth-nvidia-status
install -m 0755 /ctx/kyth-creator-check /usr/bin/kyth-creator-check
install -m 0755 /ctx/kyth-vm-acceptance-guest /usr/libexec/kyth-vm-acceptance-guest
install -m 0644 /ctx/kyth-vm-acceptance.service /usr/lib/systemd/system/kyth-vm-acceptance.service
systemctl enable kyth-vm-acceptance.service
