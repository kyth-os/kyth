# shellcheck shell=bash
install_opticscaler() {
	# OptiScaler — universal upscaling intermediary that lets any game use FSR2/3,
	# XeSS, or DLSS-translation on AMD/Intel GPUs via Proton's DLL override
	# mechanism. DLLs are baked at /usr/share/kyth/opticscaler/ for offline
	# deployment; use 'ujust deploy-opticscaler <game-dir>' at runtime.
	local OS_REPO_API="https://api.github.com/repos/cdozdil/OptiScaler/releases/latest"
	local TMPDIR_OS
	TMPDIR_OS=$(mktemp -d)
	local release_json="${TMPDIR_OS}/release.json"

	if curl -fsSL "${CURL_COMMON_ARGS[@]}" "${CURL_AUTH_ARGS[@]}" "${OS_REPO_API}" -o "${release_json}" 2>/dev/null; then
		local OS_URL
		# Prefer a combined zip (x64/win64); skip symbols, debug, or win32-only builds.
		OS_URL=$(
			grep -oP 'https://[^"]+\.zip' "${release_json}" |
				grep -iv 'source\|symbols\|pdb\|debug' |
				grep -iv '\bwin32\b\|_x86[^_]' |
				head -n1
		) || true

		if [[ -n "${OS_URL}" ]]; then
			local OS_ZIP
			OS_ZIP=$(basename "${OS_URL}")
			if ! release_asset_has_verification "${release_json}" "${OS_ZIP}"; then
				echo "WARNING: opticscaler: no verification metadata for ${OS_ZIP}; skipping unverified build-time install." >&2
				echo "  Run 'ujust deploy-opticscaler <game-dir>' on the live system instead." >&2
			else
				echo "opticscaler: downloading ${OS_ZIP}"
				curl -fsSL "${CURL_COMMON_ARGS[@]}" "${OS_URL}" -o "${TMPDIR_OS}/${OS_ZIP}"
				verify_release_asset "${release_json}" "${TMPDIR_OS}/${OS_ZIP}" \
					"${OS_ZIP}" "${TMPDIR_OS}"
				mkdir -p "${TMPDIR_OS}/extracted" /usr/share/kyth/opticscaler
				unzip -q "${TMPDIR_OS}/${OS_ZIP}" -d "${TMPDIR_OS}/extracted/"
				# Copy everything from the zip root into the baked directory so
				# deploy-opticscaler can later rsync the full set to a game folder.
				cp -r "${TMPDIR_OS}/extracted/." /usr/share/kyth/opticscaler/
				local count
				count=$(find /usr/share/kyth/opticscaler -name '*.dll' | wc -l)
				echo "opticscaler: baked ${count} DLL(s) to /usr/share/kyth/opticscaler/"
			fi
		else
			echo "opticscaler: no suitable zip found in release assets; skipping."
		fi
	else
		echo "opticscaler: failed to fetch release info from GitHub; skipping."
	fi
	rm -rf "${TMPDIR_OS}"
}
