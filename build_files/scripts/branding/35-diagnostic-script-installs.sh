# shellcheck shell=bash
# ── Read-only diagnostic/health-check scripts ──────────────────────────────────
install -m 0755 /ctx/kyth-smoke-check /usr/bin/kyth-smoke-check
# Sourced (not executed directly) by kyth-post-update-check, kyth-firstboot-app-status,
# kyth-controller-check, kyth-resume-check, and kyth-nvidia-status below.
install -m 0644 /ctx/kyth-diagnostics-common.sh /usr/libexec/kyth-diagnostics-common.sh
install -m 0755 /ctx/kyth-post-update-check /usr/bin/kyth-post-update-check
install -m 0755 /ctx/kyth-firstboot-app-status /usr/bin/kyth-firstboot-app-status
install -m 0755 /ctx/kyth-controller-check /usr/bin/kyth-controller-check
install -m 0755 /ctx/kyth-resume-check /usr/bin/kyth-resume-check
install -m 0755 /ctx/kyth-nvidia-status /usr/bin/kyth-nvidia-status
install -m 0755 /ctx/kyth-creator-check /usr/bin/kyth-creator-check
install -m 0755 /ctx/kyth-vm-acceptance-guest /usr/libexec/kyth-vm-acceptance-guest
install -m 0644 /ctx/kyth-vm-acceptance.service /usr/lib/systemd/system/kyth-vm-acceptance.service
systemctl enable kyth-vm-acceptance.service
