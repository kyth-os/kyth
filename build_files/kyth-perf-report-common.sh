# shellcheck shell=bash
# Shared helper for KythOS performance/benchmark reporting scripts
# (kyth-kerver, kyth-snappy-bench). Sourced, not executed directly.
#
# NOTE: kyth-post-update-check's deployment_id() and kyth-smoke-check's
# short_bootc_ref() are NOT unified with this — they prefer status.booted
# over spec.image (the actually-booted image, not the staged target) and
# short_bootc_ref() also retries with `sudo -n`. Those are deliberate
# differences for their use cases (verifying actual running state), not
# incidental duplication.

# Echo the currently-targeted bootc image reference (staged spec, falling
# back to the booted image), or "unavailable" if bootc isn't present or the
# query fails.
get_booted_bootc_ref() {
	if ! command -v bootc >/dev/null 2>&1; then
		echo "unavailable"
		return
	fi
	local ref
	ref=$(bootc status --json 2>/dev/null | jq -r '.spec.image.image // .status.booted.image.image.image // "unavailable"' 2>/dev/null || true)
	echo "${ref:-unavailable}"
}
