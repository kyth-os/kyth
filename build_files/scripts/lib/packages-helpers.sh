# shellcheck shell=bash
#
# install_available_optional_packages: install a list of "nice to have"
# packages as one batched transaction, dropping any not present in configured
# repos and falling back to individual installs if the batch fails. Shared by
# the optional gaming-peripheral and optional desktop-tooling package
# fragments so one flaky COPR/mirror package can't block a whole fragment.
install_available_optional_packages() {
	local group_name=$1
	shift

	local pkg
	local -a available_packages=()

	# One metadata load for all packages instead of N individual queries.
	local available_set
	available_set=$(dnf5 repoquery --available --qf '%{name}\n' "$@" 2>/dev/null | sort -u)

	for pkg in "$@"; do
		if grep -qx "${pkg}" <<<"${available_set}"; then
			available_packages+=("${pkg}")
		else
			echo "optional ${group_name} package '${pkg}' is unavailable in configured repos; skipping."
		fi
	done

	((${#available_packages[@]})) || return 0

	# Use one transaction in the normal case. If one optional package has a
	# transient conflict, retry individually so the rest still land.
	if dnf5 install -y --skip-unavailable "${available_packages[@]}"; then
		return 0
	fi

	echo "WARNING: optional ${group_name} package batch failed; retrying individually." >&2
	for pkg in "${available_packages[@]}"; do
		dnf5 install -y --skip-unavailable "${pkg}" ||
			echo "WARNING: optional ${group_name} package '${pkg}' failed to install; continuing." >&2
	done
}
