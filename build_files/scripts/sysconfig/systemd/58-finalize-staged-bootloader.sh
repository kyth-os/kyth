#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# Write the BLS entry as soon as bootc stages, and again at shutdown if the
# in-session finalize was skipped (raw `bootc upgrade`). See docs/update-safety.md.
install -m 0755 /ctx/sysconfig/kyth-finalize-staged /usr/libexec/kyth-finalize-staged
ln -sfn /usr/libexec/kyth-finalize-staged /usr/bin/kyth-finalize-staged

install -d /usr/lib/systemd/system/ostree-finalize-staged.service.d
write_config /usr/lib/systemd/system/ostree-finalize-staged.service.d/10-kyth-boot-rw.conf <<'EOF'
[Service]
# bootc starts this unit after staging. Finalize immediately (do not wait
# for shutdown ExecStop): remount,rw on Kyth's /boot bind-mount is EINVAL,
# and a failed shutdown finalize leaves the image queued forever.
# The '-' prefix keeps the unit active if in-session finalize fails so
# ExecStop can retry at reboot.
ExecStart=
ExecStart=-/usr/libexec/kyth-finalize-staged
ExecStop=
ExecStop=/usr/libexec/kyth-finalize-staged
EOF
