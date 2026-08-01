# shellcheck shell=bash
#
# The gaming-stack packages installed with explicit x86_64+i686 pairs in
# packages.sh. Kept here, not re-listed at each call site, so the install-time
# and upgrade-time guard calls can't drift out of sync with each other.
#
# libobs_vkcapture/libobs_glcapture are deliberately NOT in this list: as of
# 2026-07-17 the ublue-os/obs-vkcapture COPR's fedora-44-i386 (and f43/rawhide
# i386) build is broken upstream — only f42-i386 still succeeds — so the i686
# package genuinely does not exist to install, not a mirror desync. Hard-
# failing the build over it would be wrong: a missing i686 capture layer only means
# OBS can't game-capture 32-bit titles — a degraded feature, not a crash.
# Revisit and re-add once ublue-os/obs-vkcapture's i386 chroot builds again.
KYTH_MULTILIB_PAIRS=(
	mangohud vkBasalt libFAudio
	gamemode libXScrnSaver libatomic nss
)

# Fails loudly if any package in the given list is installed for only one of
# x86_64/i686. A `dnf5 install --skip-unavailable ... || true` pattern can
# silently drop just one arch of a pair without failing the build — that's
# exactly what previously allowed one architecture of a required pair to ship
# without its counterpart. This guard stays as defense in depth in case a
# future edit reintroduces --skip-unavailable somewhere in this list. Uses
# exit codes, not `rpm -q` output, since some rpm builds print "package ...
# is not installed" to stdout rather than stderr — capturing that text would
# silently defeat an output-based check.
check_multilib_pairs() {
	local pkg has_x86_64 has_i686 split=0
	for pkg in "$@"; do
		rpm -q "${pkg}.x86_64" &>/dev/null && has_x86_64=1 || has_x86_64=0
		rpm -q "${pkg}.i686" &>/dev/null && has_i686=1 || has_i686=0
		# If i686 is disabled by build profile, both x86_64 and i686 are not expected to be paired
		if ((has_x86_64 != has_i686)); then
			echo "ERROR: ${pkg} installed for only one architecture (x86_64=${has_x86_64} i686=${has_i686}). Mirror/COPR desync likely — retry the build." >&2
			split=1
		fi
	done
	((split == 0))
}

# Packages known to legitimately ship i686-only (no x86_64 build exists, or
# the x86_64 build is intentionally not installed). Populate this after
# reviewing scan_multilib_orphans output — anything not on this list that
# scan_multilib_orphans flags is a candidate to promote into
# KYTH_MULTILIB_PAIRS (and check_multilib_pairs) as a hard build failure.
KYTH_MULTILIB_SCAN_ALLOWLIST=()

# Report-only: scans every installed .i686 package for a missing x86_64
# counterpart and warns (does not fail the build). check_multilib_pairs only
# catches a split in the hand-picked KYTH_MULTILIB_PAIRS list — the next
# mirror desync or careless --skip-unavailable could just as easily hit a
# package nobody thought to list. This scan covers that general case without
# risking a false-positive build break: run it, review the WARN lines against
# real image state, and either allowlist legitimate i686-only packages or
# promote real orphans into KYTH_MULTILIB_PAIRS so they start failing the
# build instead of just warning.
scan_multilib_orphans() {
	local name allow allowed
	while IFS= read -r name; do
		[[ -z "${name}" ]] && continue
		allowed=0
		for allow in "${KYTH_MULTILIB_SCAN_ALLOWLIST[@]:-}"; do
			[[ "${name}" == "${allow}" ]] && allowed=1 && break
		done
		((allowed)) && continue
		echo "WARN: ${name}.i686 installed with no x86_64 counterpart (report-only — review and either allowlist or promote to check_multilib_pairs)." >&2
	done < <(comm -23 \
		<(rpm -qa --qf '%{NAME}\t%{ARCH}\n' | awk -F'\t' '$2=="i686"{print $1}' | sort -u) \
		<(rpm -qa --qf '%{NAME}\t%{ARCH}\n' | awk -F'\t' '$2=="x86_64"{print $1}' | sort -u))
}
