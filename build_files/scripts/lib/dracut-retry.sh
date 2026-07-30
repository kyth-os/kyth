# shellcheck shell=bash

# Build an initramfs defensively. dracut's `hardlink` post-processing pass
# (deduplicating identical files in the initramfs) uses util-linux hardlink's
# AF_ALG kernel-crypto-API file comparison, which reliably SIGSEGVs on these
# GitHub Actions build containers — a known upstream issue (util-linux is
# removing AF_ALG from hardlink entirely: util-linux/util-linux#4334).
# --nohardlink skips that pass; the resulting initramfs is a few KB larger,
# never smaller/functionally different. The retry-with-lsinitrd-verification
# loop below is kept as defense-in-depth against any other transient dracut
# failure, not as the fix for this specific one.
kyth_build_initramfs() {
	local output=$1
	shift
	local attempt status=1

	for attempt in 1 2; do
		rm -f "${output}"
		if TMPDIR=/var/tmp dracut "$@" --nohardlink --force "${output}" \
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
