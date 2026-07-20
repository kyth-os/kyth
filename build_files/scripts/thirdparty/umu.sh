# shellcheck shell=bash
install_umu() {
	local UMU_REPO_API="https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest"
	local TMPDIR_UMU
	TMPDIR_UMU=$(mktemp -d)
	local release_json="${TMPDIR_UMU}/release.json"

	if curl -fsSL "${CURL_COMMON_ARGS[@]}" "${CURL_AUTH_ARGS[@]}" "${UMU_REPO_API}" -o "${release_json}" 2>/dev/null; then
		local UMU_URL
		UMU_URL=$(
			grep -oP 'https://[^"]+/releases/download/[^"]+umu-launcher-[^"]+-zipapp\.tar' "${release_json}" |
				head -n1
		) || true
		if [[ -z "${UMU_URL}" ]]; then
			UMU_URL=$(
				grep -oP 'https://[^"]+/releases/download/[^"]+\.tar(\.(gz|zst))?' "${release_json}" |
					grep -iv 'source\|src' |
					head -n1
			) || true
		fi
		if [[ -n "${UMU_URL}" ]]; then
			local UMU_TARBALL
			UMU_TARBALL=$(basename "${UMU_URL}")
			echo "umu-launcher: downloading ${UMU_TARBALL}"
			curl -fsSL "${CURL_COMMON_ARGS[@]}" "${UMU_URL}" -o "${TMPDIR_UMU}/${UMU_TARBALL}"
			verify_release_asset "${release_json}" "${TMPDIR_UMU}/${UMU_TARBALL}" \
				"${UMU_TARBALL}" "${TMPDIR_UMU}"
			tar -xf "${TMPDIR_UMU}/${UMU_TARBALL}" -C "${TMPDIR_UMU}/"
			local UMU_BIN
			UMU_BIN=$(find "${TMPDIR_UMU}" -name 'umu-run' -type f | head -n1)
			if [[ -n "${UMU_BIN}" ]]; then
				install -m 0755 "${UMU_BIN}" /usr/bin/umu-run
				local UMU_PKGDIR
				UMU_PKGDIR=$(find "${TMPDIR_UMU}" -maxdepth 3 -name 'umu' -type d | grep -v '__pycache__' | head -n1)
				if [[ "${UMU_TARBALL}" != *-zipapp.tar && -n "${UMU_PKGDIR}" ]]; then
					local PY_SITEPKG
					PY_SITEPKG=$(python3 -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
					mkdir -p "${PY_SITEPKG}"
					cp -r "${UMU_PKGDIR}" "${PY_SITEPKG}/"
				fi
				echo "umu-launcher: installed $(umu-run --version 2>/dev/null || echo 'unknown version')"
			else
				echo "umu-launcher: umu-run binary not found at expected path in archive; skipping." >&2
			fi
		else
			echo "umu-launcher: no installable tarball found in release assets; skipping."
		fi
	else
		echo "umu-launcher: failed to fetch release info from GitHub; skipping."
	fi
	rm -rf "${TMPDIR_UMU}"
}
