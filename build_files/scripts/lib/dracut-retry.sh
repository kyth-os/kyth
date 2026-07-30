# shellcheck shell=bash

# Build an initramfs defensively. dracut/dracut-install can occasionally exit
# via SIGSEGV on bootc image builders after writing a partial archive. Never
# reuse that output: remove it, retry once, and require lsinitrd to parse the
# successful result before allowing the container build to continue.
kyth_build_initramfs() {
	local output=$1
	shift
	local attempt status=1

	for attempt in 1 2; do
		rm -f "${output}"
		if TMPDIR=/var/tmp dracut "$@" --force "${output}" \
			2> >(grep -Ev 'xattr|fail to copy' >&2); then
			if lsinitrd "${output}" >/dev/null; then
				return 0
			fi
			status=1
			echo "WARNING: dracut produced an unreadable initramfs (attempt ${attempt}/2)" >&2
		else
			status=$?
			echo "WARNING: dracut failed with status ${status} (attempt ${attempt}/2)" >&2
		fi

		if ((attempt < 2)); then
			echo "Retrying initramfs generation from a clean output..." >&2
		fi
	done

	rm -f "${output}"
	return "${status}"
}
