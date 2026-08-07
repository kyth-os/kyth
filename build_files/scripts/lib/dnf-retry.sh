# shellcheck shell=bash
# Shared DNF retry helper for transient Copr/mirror failures.
# Provides dnf_retry (wraps any dnf5 invocation) and copr_enable_retry.
# Each retries up to 3 times with backoff and metadata clean between attempts.
# All retries use --setopt=retries=10 --setopt=timeout=120 to match the
# rpmfusion bootstrap hardening and to survive brief Fedora/Copr outages.

dnf_retry() {
	local attempt
	local -a base_args=()
	# Avoid duplicating --setopt if caller already passed it.
	local has_retries=0
	local has_timeout=0
	for arg in "$@"; do
		[[ "${arg}" == retries=* || "${arg}" == --setopt=retries=* ]] && has_retries=1
		[[ "${arg}" == timeout=* || "${arg}" == --setopt=timeout=* ]] && has_timeout=1
	done
	if (( ! has_retries )); then
		base_args+=(--setopt=retries=10)
	fi
	if (( ! has_timeout )); then
		base_args+=(--setopt=timeout=120)
	fi
	for attempt in 1 2 3; do
		if dnf5 "${base_args[@]}" "$@"; then
			return 0
		fi
		local status=$?
		if ((attempt < 3)); then
			echo "WARNING: dnf5 $* failed (attempt ${attempt}/3, status ${status}); retrying in $((attempt * 5))s..." >&2
			sleep $((attempt * 5))
			dnf5 clean metadata 2>/dev/null || true
		else
			return "${status}"
		fi
	done
}

copr_enable_retry() {
	local copr=$1
	dnf_retry copr enable -y "${copr}"
}
