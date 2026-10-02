#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── KWallet PAM bridge: wire pam_kwallet into the PLM PAM stack ──────────────
# pam-kwallet is installed but Fedora's plasmalogin PAM files do not always
# include the relabel helper. Without the session hook the wallet is never
# unlocked at login; the first app that touches it receives a "wallet is closed"
# error and prompts the user.
#
# The module filename is resolved from the installed package at build time
# instead of being hardcoded: Fedora renamed the package (kwallet-pam ->
# pam-kwallet) and the module may follow (pam_kwallet5.so vs pam_kwallet6.so).
# Fail closed here — wiring a nonexistent module would silently break wallet
# unlock at login while the build looks green.
#
# Fedora 45's plasmalogin stack may also ship pam_oo7 lines (the new default
# secrets provider). KythOS standardizes on KWallet — every app pin, the
# kwalletrc defaults, and the wallet-unlock SELinux work target it — so exactly
# one provider must auto-start at login. Any active pam_oo7 line is commented
# out here; if we ever migrate to oo7 this block is the single place to flip.
#
# We also inject a relabeling helper that runs BEFORE pam_kwallet's session
# hook. The kwalletd directory can end up labeled default_t when first created
# by a system-context process (the greeter helper runs as xdm_t; SELinux denies
# xdm_t→default_t getattr, so pam_kwallet cannot read the salt file and
# silently fails to unlock the wallet on every login).
write_config /usr/libexec/kyth-kwallet-relabel 0755 <<'RELABELEOF'
#!/bin/bash
[[ -n "${PAM_USER:-}" && -d "/var/home/${PAM_USER}/.local/share/kwalletd" ]] && \
    restorecon -RF "/var/home/${PAM_USER}/.local/share/kwalletd" &>/dev/null
exit 0
RELABELEOF

for PAM_FILE in /etc/pam.d/plasmalogin /usr/lib/pam.d/plasmalogin; do
	[ -f "${PAM_FILE}" ] || continue

	# Resolve the module from the installed package; never hardcode it. Prefer the
	# highest-versioned module when several ship (matches the kwallet6 direction).
	KWALLET_PAM_SO="$(rpm -ql pam-kwallet 2>/dev/null | grep -E '/pam_kwallet[^/]*\.so$' | sort -V | tail -n 1 || true)"
	if [[ -z "${KWALLET_PAM_SO}" ]]; then
		echo "ERROR: no pam_kwallet*.so module found in installed pam-kwallet package; refusing to wire PAM" >&2
		exit 1
	fi
	KWALLET_PAM_MODULE="$(basename "${KWALLET_PAM_SO}")"

	# Single secrets provider: neutralize any ACTIVE pam_oo7 line. Lines that
	# are already commented out (or use the "-" disabled prefix) are left alone.
	if grep -qE '^[[:space:]]*(auth|session)[[:space:]]+.*pam_oo7' "${PAM_FILE}"; then
		sed -i -E 's/^([[:space:]]*)((auth|session)[[:space:]]+.*pam_oo7.*)$/\1# \2  # kyth: KWallet is the single secrets provider/' "${PAM_FILE}"
	fi

	# Only treat UNCOMMENTED pam_kwallet lines as already wired; a commented
	# (or "-" prefixed) vendor line must not satisfy the guard.
	if ! grep -qE "^[[:space:]]*(auth|session)[[:space:]]+.*${KWALLET_PAM_MODULE}" "${PAM_FILE}"; then
		printf '\nauth     optional     %s\nsession  optional     pam_exec.so /usr/libexec/kyth-kwallet-relabel\nsession  optional     %s auto_start\n' \
			"${KWALLET_PAM_MODULE}" "${KWALLET_PAM_MODULE}" >>"${PAM_FILE}"
	elif ! grep -q kyth-kwallet-relabel "${PAM_FILE}"; then
		awk -v mod="${KWALLET_PAM_MODULE}" '!done && $0 ~ mod && /auto_start/ {
            print "session  optional  pam_exec.so /usr/libexec/kyth-kwallet-relabel"
            done=1
        } { print }' "${PAM_FILE}" >/tmp/kyth-plasmalogin.tmp && mv /tmp/kyth-plasmalogin.tmp "${PAM_FILE}"
	fi
	break
done

# Boot-time repair: on bootc/ostree upgrades, /etc/pam.d/plasmalogin in the
# /etc overlay can be stale (missing the bridge above). Install an idempotent
# oneshot that re-verifies the wiring on every boot; harmless when already
# correct. Without this, upgraded systems prompt for the wallet on every login.
install -m 0755 /ctx/sysconfig/desktop/kyth-kwallet-pam-ensure /usr/libexec/kyth-kwallet-pam-ensure
write_config /usr/lib/systemd/system/kyth-kwallet-pam-ensure.service <<'PAMENSURESERVICEEOF'
[Unit]
Description=Ensure KWallet PAM bridge is wired
Before=plasmalogin.service display-manager.service
DefaultDependencies=no
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/libexec/kyth-kwallet-pam-ensure

[Install]
WantedBy=multi-user.target
PAMENSURESERVICEEOF
systemctl enable kyth-kwallet-pam-ensure.service 2>/dev/null || true
