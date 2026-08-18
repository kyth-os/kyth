# shellcheck shell=bash
set -euo pipefail
# Shared helper for KythOS read-only diagnostic-dump scripts
# (kyth-device-info, kyth-creator-check). Sourced, not executed directly.
#
# NOTE: kyth-session-snapshot is NOT unified with this — it appends to a
# report file instead of stdout and echoes each command line before running
# it, which is a deliberate difference for its use case (a shareable saved
# snapshot), not incidental duplication.

section() {
	echo
	echo "== $1 =="
}

safe_cmd() {
	"$@" 2>/dev/null || true
}
