# shellcheck shell=bash

# Build an initramfs defensively.
#
# kinoite-main ships /root as a symlink to var/roothome, but /var/roothome
# doesn't exist in the container image. dracut's core skeleton setup
# unconditionally calls `inst_symlink /root` for every build (see
# /usr/bin/dracut's `for d in dev proc sys sysroot root run` loop), which
# fails with "dracut-install: ERROR: installing '/root'" against the
# dangling symlink. Creating the target first makes that install succeed.
# --nohardlink additionally skips dracut's post-build hardlink dedup pass,
# whose util-linux AF_ALG file-comparison path is a known SIGSEGV risk on
# some containerized builders (util-linux/util-linux#4334) — unrelated to
# the /root issue above, kept as a separate precaution.
kyth_build_initramfs() {
	local output=$1
	shift
	local attempt status=1
	local stderr_log
	stderr_log=$(mktemp)
	trap 'rm -f "${stderr_log}"' RETURN

	install -d -m 0700 /var/roothome

	for attempt in 1 2; do
		rm -f "${output}"
		if TMPDIR=/var/tmp dracut "$@" --nohardlink --force "${output}" 2>"${stderr_log}"; then
			grep -Ev 'xattr|fail to copy' "${stderr_log}" >&2
			if lsinitrd "${output}" >/dev/null; then
				trap - RETURN
				rm -f "${stderr_log}"
				return 0
			fi
			status=1
			echo "WARNING: dracut produced an unreadable initramfs (attempt ${attempt}/2)" >&2
		else
			status=$?
			grep -Ev 'xattr|fail to copy' "${stderr_log}" >&2
			echo "WARNING: dracut failed with status ${status} (attempt ${attempt}/2)" >&2
		fi

		if ((attempt < 2)); then
			echo "Retrying initramfs generation from a clean output..." >&2
		fi
	done

	trap - RETURN
	rm -f "${output}" "${stderr_log}"
	return "${status}"
}
