#!/usr/bin/env bash
# Coordinated latest Fedora kernel transaction shared by package assembly and
# the daily upgrade layer. Call only for the Fedora kernel flavor.

update_fedora_kernel() {
	# Kernel packages are excluded globally so ordinary transactions cannot
	# leave core and module packages out of sync; this is the one exception.
	dnf5 upgrade -y --refresh --setopt=excludepkgs= \
		--disablerepo=fedora-multimedia \
		kernel \
		kernel-core \
		kernel-modules \
		kernel-modules-core \
		kernel-modules-extra

	FEDORA_KERNEL_VR="$(
		rpm -q kernel-core --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' \
			| sort -V | tail -n 1
	)"
	test -n "${FEDORA_KERNEL_VR}"
	dnf5 install -y --setopt=excludepkgs= \
		--disablerepo=fedora-multimedia \
		"kernel-devel-${FEDORA_KERNEL_VR}"
	rpm -q \
		"kernel-${FEDORA_KERNEL_VR}" \
		"kernel-core-${FEDORA_KERNEL_VR}" \
		"kernel-modules-${FEDORA_KERNEL_VR}" \
		"kernel-modules-core-${FEDORA_KERNEL_VR}" \
		"kernel-modules-extra-${FEDORA_KERNEL_VR}" \
		"kernel-devel-${FEDORA_KERNEL_VR}"

	# Fedora kernels are install-only packages. Atomic images should expose one
	# coherent deployment kernel, so remove superseded versioned payloads only
	# after the latest complete stack and matching devel package are verified.
	local package nevra
	for package in kernel kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-devel; do
		while IFS= read -r nevra; do
			[[ -z "${nevra}" || "${nevra}" == *"-${FEDORA_KERNEL_VR}" ]] && continue
			echo "Removing superseded Fedora kernel package: ${nevra}"
			rpm --nodeps -e "${nevra}"
		done < <(rpm -q "${package}" --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' 2>/dev/null || true)
	done
}
