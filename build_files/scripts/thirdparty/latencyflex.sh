# shellcheck shell=bash
install_latencyflex() {
	: "${LATENCYFLEX_VERSION:?LATENCYFLEX_VERSION must be an exact release tag}"
	require_release_tag LATENCYFLEX_VERSION "${LATENCYFLEX_VERSION}"
	local LFX_REPO_API="https://api.github.com/repos/ishitatsuyuki/LatencyFleX/releases/tags/${LATENCYFLEX_VERSION}"
	local TMPDIR_LFX
	TMPDIR_LFX=$(mktemp -d)
	local release_json="${TMPDIR_LFX}/release.json"

	if curl -fsSL "${CURL_COMMON_ARGS[@]}" "${CURL_AUTH_ARGS[@]}" "${LFX_REPO_API}" -o "${release_json}" 2>/dev/null; then
		local LFX_URL
		LFX_URL=$(
			grep -oP 'https://[^"]+\.tar\.(gz|xz|zst)' "${release_json}" |
				grep -iv 'source' |
				head -n1
		) || true
		if [[ -n "${LFX_URL}" ]]; then
			local LFX_TARBALL
			LFX_TARBALL=$(basename "${LFX_URL}")
			if ! release_asset_has_verification "${release_json}" "${LFX_TARBALL}"; then
				echo "ERROR: latencyflex: pinned asset ${LFX_TARBALL} has no verification metadata." >&2
				rm -rf "${TMPDIR_LFX}"
				return 1
			else
				echo "latencyflex: downloading ${LFX_TARBALL}"
				curl -fsSL "${CURL_COMMON_ARGS[@]}" "${LFX_URL}" -o "${TMPDIR_LFX}/${LFX_TARBALL}"
				verify_release_asset "${release_json}" "${TMPDIR_LFX}/${LFX_TARBALL}" \
					"${LFX_TARBALL}" "${TMPDIR_LFX}"
				tar -xf "${TMPDIR_LFX}/${LFX_TARBALL}" -C "${TMPDIR_LFX}/"

				local LFX_SO
				LFX_SO=$(find "${TMPDIR_LFX}" -name 'liblatencyflex_layer.so' | head -n1)
				local LFX_JSON
				LFX_JSON=$(find "${TMPDIR_LFX}" -name '*.json' | grep -i 'latencyflex' | head -n1)

				if [[ -n "${LFX_SO}" && -n "${LFX_JSON}" ]]; then
					install -m 0755 "${LFX_SO}" /usr/lib64/liblatencyflex_layer.so
					mkdir -p /usr/share/vulkan/implicit_layer.d
					install -m 0644 "${LFX_JSON}" \
						/usr/share/vulkan/implicit_layer.d/latencyflex_layer.json
					sed -i 's|"library_path":.*|"library_path": "/usr/lib64/liblatencyflex_layer.so"|' \
						/usr/share/vulkan/implicit_layer.d/latencyflex_layer.json
					echo "latencyflex: Vulkan layer installed"
				else
					echo "ERROR: latencyflex: pinned release ${LATENCYFLEX_VERSION} is missing its layer payload." >&2
					rm -rf "${TMPDIR_LFX}"
					return 1
				fi
			fi
		else
			echo "ERROR: latencyflex: pinned release ${LATENCYFLEX_VERSION} has no installable tarball." >&2
			rm -rf "${TMPDIR_LFX}"
			return 1
		fi
	else
		echo "ERROR: latencyflex: failed to fetch pinned release ${LATENCYFLEX_VERSION}." >&2
		rm -rf "${TMPDIR_LFX}"
		return 1
	fi
	rm -rf "${TMPDIR_LFX}"
}
