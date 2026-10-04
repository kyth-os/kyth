#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── SELinux: stop aliasing /var/home to /home ─────────────────────────────────
# selinux-policy 45 added "/var/home /home" to file_contexts.subs_dist. A subs
# rule rewrites the lookup path BEFORE matching, so /var/home/<user>/... is
# looked up as /home/<user>/.... But the user-home rules libsemanage generates
# into file_contexts.homedirs are written for the real home directory,
# /var/home/<user>/..., because that is what HOME is on ostree systems
# (/home is only a symlink). After the alias nothing matches, every path under
# /var/home resolves to default_t, and restorecon happily "confirms" default_t
# as correct.
#
# Effect on a Fedora 45 deployment: xdm_t (plasmalogin) was denied getattr on
# ~/.local/share/kwalletd/kdewallet.salt, pam_kwallet5 could not unlock the
# wallet at login, and KDE Wallet prompted for its password on first boot. The
# same default_t labels would deny anything else a confined login-time service
# touches under a home directory. Fedora 44's policy has no such alias (its
# homedirs rules and lookups agreed), so this is new with the F45 policy.
#
# Removing the alias line is enough: lookups then reach the /var/home rules
# directly, and the existing relabel units fix labels on disk (both are keyed to
# every file_contexts* file, so this edit alone schedules a correcting pass).
# /var/roothome -> /root and the other aliases are left alone.
SUBS_FILE="${KYTH_SELINUX_SUBS_DIST:-/etc/selinux/targeted/contexts/files/file_contexts.subs_dist}"

if [[ ! -f "${SUBS_FILE}" ]]; then
	echo "33-selinux-var-home-label-alias: ${SUBS_FILE} not present; nothing to do"
	exit 0
fi

# Match the alias exactly (source path /var/home, whitespace, any target); never
# touch /var/home/<something> or /var/homefoo style lines.
if grep -qE '^/var/home[[:space:]]' "${SUBS_FILE}"; then
	tmp="$(mktemp "${SUBS_FILE}.XXXXXX")"
	grep -vE '^/var/home[[:space:]]' "${SUBS_FILE}" >"${tmp}" || true
	chmod --reference="${SUBS_FILE}" "${tmp}"
	mv -f "${tmp}" "${SUBS_FILE}"
fi

if grep -qE '^/var/home[[:space:]]' "${SUBS_FILE}"; then
	echo "33-selinux-var-home-label-alias: failed to remove the /var/home alias" >&2
	exit 1
fi
echo "33-selinux-var-home-label-alias: /var/home no longer aliased to /home"
