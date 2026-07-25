# shellcheck shell=bash
#
# Small assertion primitives shared by every script that verifies a built
# initramfs actually contains the branded KythOS Plymouth theme: the live
# ISO (installer/build.sh), the installed-image build
# (scripts/plymouth-initramfs.sh), and the runtime repair tool
# (scripts/repair-current-plymouth-initramfs.sh). Each caller checks a
# differently-scoped subset of the same underlying facts, so this stays a
# handful of composable primitives rather than one big verify-everything
# function.

# Fail with "ERROR: <message>" on stderr and exit 1 unless `pattern` is
# found in `file` (fixed-string/basic regex, as grep -q).
plymouth_require_pattern() {
	local file="$1" pattern="$2" message="$3"
	grep -q "${pattern}" "${file}" || {
		echo "ERROR: ${message}" >&2
		exit 1
	}
}

# Same as plymouth_require_pattern but with extended regex matching (grep -Eq).
plymouth_require_pattern_ere() {
	local file="$1" pattern="$2" message="$3"
	grep -Eq "${pattern}" "${file}" || {
		echo "ERROR: ${message}" >&2
		exit 1
	}
}

# Fail unless `lhs` and `rhs` are byte-identical.
plymouth_require_match() {
	local lhs="$1" rhs="$2" message="$3"
	cmp -s "${lhs}" "${rhs}" || {
		echo "ERROR: ${message}" >&2
		exit 1
	}
}

# Fail if any distro fallback Plymouth theme (bgrt-fedora/bgrt/spinner) is
# present in `listing_file` (the output of `lsinitrd <initramfs>`).
plymouth_forbid_fallback_theme() {
	local listing_file="$1" message="$2"
	if grep -Ei 'usr/share/plymouth/themes/(bgrt-fedora|bgrt|spinner)(/|$)' "${listing_file}" >&2; then
		echo "ERROR: ${message}" >&2
		exit 1
	fi
}
