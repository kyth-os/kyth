#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cache_dir="${KYTH_CI_TOOL_CACHE:-${repo_root}/.cache/kyth-ci-tools}"
bin_dir="${cache_dir}/bin"
mkdir -p "${cache_dir}" "${bin_dir}"

ACTIONLINT_VERSION="${ACTIONLINT_VERSION:-1.7.7}"
HADOLINT_VERSION="${HADOLINT_VERSION:-2.14.0}"
JUST_VERSION="${JUST_VERSION:-1.52.0}"
SHELLCHECK_VERSION="${SHELLCHECK_VERSION:-0.10.0}"
SHELLCHECK_SHA256="${SHELLCHECK_SHA256:-6c881ab0698e4e6ea235245f22832860544f17ba386442fe7e9d629f8cbedf87}"
ZIZMOR_VERSION="${ZIZMOR_VERSION:-1.25.2}"
ZIZMOR_SHA256="${ZIZMOR_SHA256:-aa1facd105f0d83fe5c55b1adcd9d7417de5d83aa27471f91dc0b66cf3803577}"

download_and_verify() {
	local name="$1"
	local archive="$2"
	local base_url="$3"
	local sha256_or_file="$4"
	local bin_in_archive="$5"
	local target="${bin_dir}/${name}"

	[[ -x "${target}" ]] && return

	local work
	work="$(mktemp -d)"
	curl -fsSL -o "${work}/${archive}" "${base_url}/${archive}"

	if [[ -n "${sha256_or_file}" ]]; then
		if [[ "${#sha256_or_file}" -eq 64 && "${sha256_or_file}" =~ ^[0-9a-fA-F]+$ ]]; then
			echo "${sha256_or_file}  ${work}/${archive}" | sha256sum -c -
		else
			local check_file
			check_file="$(basename "${sha256_or_file}")"
			curl -fsSL -o "${work}/${check_file}" "${base_url}/${sha256_or_file}"
			if [[ "${check_file}" == *.sha256 ]]; then
				(cd "${work}" && sha256sum -c "${check_file}")
			else
				(cd "${work}" && grep " ${archive}$" "${check_file}" | sha256sum -c -)
			fi
		fi
	fi

	if [[ "${archive}" == *.tar.gz || "${archive}" == *.tar.xz ]]; then
		tar_args=(--extract --no-same-owner)
		[[ "${archive}" == *.tar.gz ]] && tar_args+=(--gzip)
		[[ "${archive}" == *.tar.xz ]] && tar_args+=(--xz)
		tar "${tar_args[@]}" --file "${work}/${archive}" \
			--directory "${work}" "${bin_in_archive}"
		install -m 0755 "${work}/${bin_in_archive}" "${target}"
	else
		install -m 0755 "${work}/${archive}" "${target}"
	fi

	rm -rf "${work}"
}

download_and_verify "actionlint" \
	"actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" \
	"https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}" \
	"actionlint_${ACTIONLINT_VERSION}_checksums.txt" "actionlint"

download_and_verify "hadolint" \
	"hadolint-linux-x86_64" \
	"https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}" \
	"hadolint-linux-x86_64.sha256" ""

download_and_verify "just" \
	"just-${JUST_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
	"https://github.com/casey/just/releases/download/${JUST_VERSION}" \
	"SHA256SUMS" "just"

download_and_verify "shellcheck" \
	"shellcheck-v${SHELLCHECK_VERSION}.linux.x86_64.tar.xz" \
	"https://github.com/koalaman/shellcheck/releases/download/v${SHELLCHECK_VERSION}" \
	"${SHELLCHECK_SHA256}" "shellcheck-v${SHELLCHECK_VERSION}/shellcheck"

download_and_verify "zizmor" \
	"zizmor-x86_64-unknown-linux-gnu.tar.gz" \
	"https://github.com/woodruffw/zizmor/releases/download/v${ZIZMOR_VERSION}" \
	"${ZIZMOR_SHA256}" "zizmor"

# Shell environment changes do not cross GitHub Actions step boundaries.
# Publish the cached tool directory for subsequent steps, including cache hits.
if [[ -n "${GITHUB_PATH:-}" ]]; then
	printf '%s\n' "${bin_dir}" >>"${GITHUB_PATH}"
fi

printf '%s\n' "${bin_dir}"
