# shellcheck shell=bash
# ── Read-only diagnostic/health-check scripts ──────────────────────────────────
# kyth-smoke-check is installed as a kyth-shared console entry point.
install -m 0755 /ctx/kyth-post-update-check /usr/bin/kyth-post-update-check
install -m 0755 /ctx/kyth-firstboot-app-status /usr/bin/kyth-firstboot-app-status
install -m 0755 /ctx/kyth-controller-check /usr/bin/kyth-controller-check
install -m 0755 /ctx/kyth-resume-check /usr/bin/kyth-resume-check
install -m 0755 /ctx/kyth-nvidia-status /usr/bin/kyth-nvidia-status
install -m 0755 /ctx/kyth-creator-check /usr/bin/kyth-creator-check
install -m 0644 /ctx/config/qualification-budgets.json /usr/share/kyth/qualification-budgets.json
install -m 0755 /ctx/kyth-vm-acceptance-guest /usr/libexec/kyth-vm-acceptance-guest
install -m 0644 /ctx/kyth-vm-acceptance.service /usr/lib/systemd/system/kyth-vm-acceptance.service
systemctl enable kyth-vm-acceptance.service

install -m 0755 /ctx/kyth-boot-verify /usr/bin/kyth-boot-verify

# greenboot owns boot counting and rollback. These hooks add KythOS-specific
# required checks plus digest-aware success/failure and quarantine records.
install -Dm0755 /ctx/kyth-greenboot-required /etc/greenboot/check/required.d/40_kyth_core_health.sh
install -Dm0755 /ctx/kyth-greenboot-success /etc/greenboot/green.d/40_kyth_record_success.sh
install -Dm0755 /ctx/kyth-greenboot-failure /etc/greenboot/red.d/40_kyth_record_failure.sh
