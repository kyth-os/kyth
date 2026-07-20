# shellcheck shell=bash
install_latencyflex() {
	local LFX_REPO_API="https://api.github.com/repos/ishitatsuyuki/LatencyFleX/releases/latest"
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
				echo "WARNING: latencyflex: no verification metadata for ${LFX_TARBALL}; skipping unverified install." >&2
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
					echo "latencyflex: could not find layer .so or .json in archive; skipping."
				fi
			fi
		else
			echo "latencyflex: no tarball found in release assets; skipping."
		fi
	else
		echo "latencyflex: failed to fetch release info from GitHub; skipping."
	fi
	rm -rf "${TMPDIR_LFX}"
}
