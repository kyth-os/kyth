#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cache_dir="${KYTH_CI_TOOL_CACHE:-${repo_root}/.cache/kyth-ci-tools}"
bin_dir="${cache_dir}/bin"
mkdir -p "${cache_dir}" "${bin_dir}"

ACTIONLINT_VERSION="${ACTIONLINT_VERSION:-1.7.7}"
HADOLINT_VERSION="${HADOLINT_VERSION:-2.14.0}"
JUST_VERSION="${JUST_VERSION:-1.52.0}"
ZIZMOR_VERSION="${ZIZMOR_VERSION:-1.25.2}"
ZIZMOR_SHA256="${ZIZMOR_SHA256:-aa1facd105f0d83fe5c55b1adcd9d7417de5d83aa27471f91dc0b66cf3803577}"

install_actionlint() {
	local target="${bin_dir}/actionlint"
	[[ -x "${target}" ]] && return
	local work archive base
	work="$(mktemp -d)"
	archive="actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz"
	base="https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}"
	curl -fsSL -o "${work}/${archive}" "${base}/${archive}"
	curl -fsSL -o "${work}/checksums.txt" "${base}/actionlint_${ACTIONLINT_VERSION}_checksums.txt"
	(cd "${work}" && grep " ${archive}$" checksums.txt | sha256sum -c -)
	tar -xzf "${work}/${archive}" -C "${work}" actionlint
	install -m 0755 "${work}/actionlint" "${target}"
	rm -rf "${work}"
}

install_hadolint() {
	local target="${bin_dir}/hadolint"
	[[ -x "${target}" ]] && return
	local work binary base
	work="$(mktemp -d)"
	binary="hadolint-linux-x86_64"
	base="https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}"
	curl -fsSL -o "${work}/${binary}" "${base}/${binary}"
	curl -fsSL -o "${work}/${binary}.sha256" "${base}/${binary}.sha256"
	(cd "${work}" && sha256sum -c "${binary}.sha256")
	install -m 0755 "${work}/${binary}" "${target}"
	rm -rf "${work}"
}

install_just() {
	local target="${bin_dir}/just"
	[[ -x "${target}" ]] && return
	local work archive base
	work="$(mktemp -d)"
	archive="just-${JUST_VERSION}-x86_64-unknown-linux-musl.tar.gz"
	base="https://github.com/casey/just/releases/download/${JUST_VERSION}"
	curl -fsSL -o "${work}/${archive}" "${base}/${archive}"
	curl -fsSL -o "${work}/SHA256SUMS" "${base}/SHA256SUMS"
	(cd "${work}" && grep " ${archive}$" SHA256SUMS | sha256sum -c -)
	tar -xzf "${work}/${archive}" -C "${work}" just
	install -m 0755 "${work}/just" "${target}"
	rm -rf "${work}"
}

install_zizmor() {
	local target="${bin_dir}/zizmor"
	[[ -x "${target}" ]] && return
	local work archive base
	work="$(mktemp -d)"
	archive="zizmor-x86_64-unknown-linux-gnu.tar.gz"
	base="https://github.com/woodruffw/zizmor/releases/download/v${ZIZMOR_VERSION}"
	curl -fsSL -o "${work}/${archive}" "${base}/${archive}"
	echo "${ZIZMOR_SHA256}  ${work}/${archive}" | sha256sum -c -
	tar -xzf "${work}/${archive}" -C "${work}" zizmor
	install -m 0755 "${work}/zizmor" "${target}"
	rm -rf "${work}"
}

install_actionlint
install_hadolint
install_just
install_zizmor
printf '%s\n' "${bin_dir}"
