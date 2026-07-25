# shellcheck shell=bash
#
# install_available_optional_packages: install a list of "nice to have"
# packages as one batched transaction, dropping any not present in configured
# repos and falling back to individual installs if the batch fails. Shared by
# the optional gaming-peripheral and optional desktop-tooling package
# fragments so one flaky COPR/mirror package can't block a whole fragment.
is_enabled() {
	case "${1,,}" in
	1 | true | yes | on) return 0 ;;
	*) return 1 ;;
	esac
}

install_available_optional_packages() {
	local group_name=$1
	shift

	local pkg
	local -a available_packages=()

	# One metadata load for all packages instead of N individual queries.
	# %{arch} is included because some optional packages are arch-suffixed
	# (e.g. "extest.i686") — the RPM Name tag alone never carries an arch
	# qualifier, so matching on %{name} alone always reports those as
	# unavailable even when they exist in configured repos.
	local available_set available_names
	available_set=$(dnf5 repoquery --available --qf '%{name}.%{arch}\n' "$@" 2>/dev/null | sort -u)
	available_names=$(sed -E 's/\.[^.]+$//' <<<"${available_set}" | sort -u)

	for pkg in "$@"; do
		# Only treat a dotted suffix as an arch qualifier when it's an actual
		# RPM arch (e.g. "extest.i686") — plenty of real package names contain
		# dots too (python3.11, boost1.78, ...) and must not be misread as
		# "name.arch".
		if [[ "${pkg}" =~ \.(x86_64|i686|i386|noarch|aarch64|armv7hl|ppc64le|s390x|src)$ ]]; then
			# Caller passed an arch-qualified name — match the exact
			# name.arch pair dnf5 reported.
			if grep -qx "${pkg}" <<<"${available_set}"; then
				available_packages+=("${pkg}")
			else
				echo "optional ${group_name} package '${pkg}' is unavailable in configured repos; skipping."
			fi
		elif grep -qx "${pkg}" <<<"${available_names}"; then
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
