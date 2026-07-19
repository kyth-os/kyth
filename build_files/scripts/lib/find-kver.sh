# shellcheck shell=bash
#
# Finds the newest /usr/lib/modules/<kver> dir that actually has a vmlinuz.
# The upstream base image can ship kernel-less debris dirs (e.g. modules
# prebuilt for a kernel it doesn't ship yet), so the highest-versioned dir
# by name isn't necessarily a real, bootable kernel. Prints the kver, or
# nothing if no dir has a vmlinuz.
find_active_kver() {
	local kver="" kdir
	for kdir in $(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V); do
		if [ -s "/usr/lib/modules/${kdir}/vmlinuz" ]; then
			kver="${kdir}"
		fi
	done
	printf '%s' "${kver}"
}
