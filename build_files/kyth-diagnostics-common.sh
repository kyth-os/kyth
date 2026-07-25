# shellcheck shell=bash
# Shared helpers for KythOS's read-only runtime diagnostic scripts
# (kyth-controller-check, kyth-nvidia-status, kyth-resume-check, and the
# notify()-based ones: kyth-post-update-check, kyth-firstboot-app-status).
# Sourced, not executed directly.

have() { command -v "$1" >/dev/null 2>&1; }
pass() { printf 'PASS  %-28s %s\n' "$1" "$2"; }
warn() {
	printf 'WARN  %-28s %s\n' "$1" "$2"
	WARNINGS=$((WARNINGS + 1))
}
fail() {
	printf 'FAIL  %-28s %s\n' "$1" "$2"
	FAILURES=$((FAILURES + 1))
}

WARNINGS=0
FAILURES=0

print_header() {
	echo "KythOS $1"
	echo "Generated: $(date -Is)"
	echo
}

# Print the pass/warn/fail summary and exit with the matching code: 2 if any
# FAILURES were recorded, 1 if any WARNINGS were, 0 otherwise.
# $1 names the thing being checked, used in "Result: $1 has failures./looks
# good." $2, if given, replaces the default "$1 has warnings." line — e.g.
# to add a more specific hint for that particular script's warning case.
print_result() {
	echo
	if [[ "${FAILURES}" -gt 0 ]]; then
		echo "Result: $1 has failures."
		exit 2
	fi
	if [[ "${WARNINGS}" -gt 0 ]]; then
		echo "Result: ${2:-$1 has warnings.}"
		exit 1
	fi
	echo "Result: $1 looks good."
}

# Desktop-notification primitive shared by kyth-post-update-check and
# kyth-firstboot-app-status. Each caller wraps this in its own local
# notify() with its own gating policy (e.g. an opt-out flag) rather than
# calling it directly, since those policies differ between the two scripts.
_kyth_notify_send() {
	local title="$1"
	local body="$2"
	if have notify-send; then
		notify-send --app-name="KythOS" "$title" "$body" >/dev/null 2>&1 || true
	elif have kdialog; then
		kdialog --title "$title" --passivepopup "$body" 12 >/dev/null 2>&1 || true
	fi
}
