# shellcheck shell=bash
# Shared file-drop helpers for sysconfig / branding build fragments.
#
# Fragments run in isolated bash subshells (see lib/fragment-runner.sh "bash"
# mode), so each fragment that wants these helpers sources this file itself:
#
#     source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"
#     write_config /etc/modprobe.d/amdgpu-kyth.conf <<'EOF'
#     options amdgpu ppfeaturemask=0xffffffff
#     EOF
#
# The goal is to stop every fragment hand-rolling "mkdir -p $(dirname); cat >
# file; chmod" with subtly different parent-dir handling and modes.

# write_config <dest> [mode]
#
# Write stdin verbatim to <dest>, creating the parent directory first and
# applying <mode> (default 0644). Feed content with a *quoted* heredoc
# (<<'EOF') to preserve config text without shell expansion.
write_config() {
	local dest=${1:?write_config: destination path required}
	local mode=${2:-0644}
	mkdir -p "$(dirname "${dest}")"
	cat >"${dest}"
	chmod "${mode}" "${dest}"
}

# write_line <content> <dest> [mode]
#
# Convenience for one-line config files (module-load lists, single options).
# Creates the parent directory and applies <mode> (default 0644).
write_line() {
	local content=${1?write_line: content required}
	local dest=${2:?write_line: destination path required}
	local mode=${3:-0644}
	mkdir -p "$(dirname "${dest}")"
	printf '%s\n' "${content}" >"${dest}"
	chmod "${mode}" "${dest}"
}
