#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── KWallet PAM bridge: wire pam_kwallet5.so into the SDDM PAM stack ─────────
# kwallet-pam is installed but Fedora's sddm package does NOT always enable it.
# Without the session hook the wallet is never unlocked at login; the first app
# that touches it receives a "wallet is closed" error and prompts the user.
# pam_kwallet5.so handles both kwalletd5 and kwalletd6.
#
# We also inject a relabeling helper that runs BEFORE pam_kwallet5's session
# hook. The kwalletd directory can end up labeled default_t when first created
# by a system-context process (sddm-helper runs as xdm_t; SELinux denies
# xdm_t→default_t getattr, so pam_kwallet5 cannot read the salt file and
# silently fails to unlock the wallet on every login).
write_config /usr/libexec/kyth-kwallet-relabel 0755 <<'RELABELEOF'
#!/bin/bash
[[ -n "${PAM_USER:-}" && -d "/var/home/${PAM_USER}/.local/share/kwalletd" ]] && \
    restorecon -RF "/var/home/${PAM_USER}/.local/share/kwalletd" &>/dev/null
exit 0
RELABELEOF

SDDM_PAM=/etc/pam.d/sddm
if [ -f "${SDDM_PAM}" ]; then
	if ! grep -q pam_kwallet5 "${SDDM_PAM}"; then
		# Fedora SDDM package didn't include kwallet5 lines — add them with relabeler.
		printf '\nauth     optional     pam_kwallet5.so\nsession  optional     pam_exec.so /usr/libexec/kyth-kwallet-relabel\nsession  optional     pam_kwallet5.so auto_start\n' >>"${SDDM_PAM}"
	elif ! grep -q kyth-kwallet-relabel "${SDDM_PAM}"; then
		# kwallet5 lines already present (standard Fedora path) — insert relabeler
		# immediately before the first pam_kwallet5 session line so restorecon
		# corrects the label before pam_kwallet5 tries to open the salt file.
		awk '!done && /pam_kwallet5.*auto_start/ {
            print "session  optional  pam_exec.so /usr/libexec/kyth-kwallet-relabel"
            done=1
        } { print }' "${SDDM_PAM}" >/tmp/kyth-sddm.tmp && mv /tmp/kyth-sddm.tmp "${SDDM_PAM}"
	fi
fi
