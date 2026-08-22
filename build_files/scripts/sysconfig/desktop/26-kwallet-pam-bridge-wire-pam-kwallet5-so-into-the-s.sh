#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── KWallet PAM bridge: wire pam_kwallet5.so into the PLM PAM stack ──────────
# kwallet-pam is installed but Fedora's plasmalogin PAM files do not always
# include the relabel helper. Without the session hook the wallet is never
# unlocked at login; the first app that touches it receives a "wallet is closed"
# error and prompts the user. pam_kwallet5.so handles both kwalletd5 and
# kwalletd6.
#
# We also inject a relabeling helper that runs BEFORE pam_kwallet5's session
# hook. The kwalletd directory can end up labeled default_t when first created
# by a system-context process (the greeter helper runs as xdm_t; SELinux denies
# xdm_t→default_t getattr, so pam_kwallet5 cannot read the salt file and
# silently fails to unlock the wallet on every login).
write_config /usr/libexec/kyth-kwallet-relabel 0755 <<'RELABELEOF'
#!/bin/bash
[[ -n "${PAM_USER:-}" && -d "/var/home/${PAM_USER}/.local/share/kwalletd" ]] && \
    restorecon -RF "/var/home/${PAM_USER}/.local/share/kwalletd" &>/dev/null
exit 0
RELABELEOF

for PAM_FILE in /etc/pam.d/plasmalogin /usr/lib/pam.d/plasmalogin; do
	[ -f "${PAM_FILE}" ] || continue
	if ! grep -q pam_kwallet5 "${PAM_FILE}"; then
		printf '\nauth     optional     pam_kwallet5.so\nsession  optional     pam_exec.so /usr/libexec/kyth-kwallet-relabel\nsession  optional     pam_kwallet5.so auto_start\n' >>"${PAM_FILE}"
	elif ! grep -q kyth-kwallet-relabel "${PAM_FILE}"; then
		awk '!done && /pam_kwallet5.*auto_start/ {
            print "session  optional  pam_exec.so /usr/libexec/kyth-kwallet-relabel"
            done=1
        } { print }' "${PAM_FILE}" >/tmp/kyth-plasmalogin.tmp && mv /tmp/kyth-plasmalogin.tmp "${PAM_FILE}"
	fi
	break
done
