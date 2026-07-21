# shellcheck shell=bash
install_topgrade() {
	local TOPGRADE_REPO_API="https://api.github.com/repos/topgrade-rs/topgrade/releases/latest"
	local TMPDIR_TG
	TMPDIR_TG=$(mktemp -d)
	local release_json="${TMPDIR_TG}/release.json"

	if curl -fsSL "${CURL_COMMON_ARGS[@]}" "${CURL_AUTH_ARGS[@]}" "${TOPGRADE_REPO_API}" -o "${release_json}" 2>/dev/null; then
		local TOPGRADE_URL
		TOPGRADE_URL=$(
			grep -oP 'https://[^"]+\.tar\.(gz|zst)' "${release_json}" |
				grep -i 'x86.64\|x86_64\|amd64' |
				grep -i 'musl\|linux' |
				grep -iv 'source' |
				head -n1
		) || true
		if [[ -n "${TOPGRADE_URL}" ]]; then
			local TOPGRADE_TARBALL
			TOPGRADE_TARBALL=$(basename "${TOPGRADE_URL}")
			curl -fsSL "${CURL_COMMON_ARGS[@]}" "${TOPGRADE_URL}" -o "${TMPDIR_TG}/${TOPGRADE_TARBALL}"
			verify_release_asset "${release_json}" "${TMPDIR_TG}/${TOPGRADE_TARBALL}" \
				"${TOPGRADE_TARBALL}" "${TMPDIR_TG}"
			tar -xf "${TMPDIR_TG}/${TOPGRADE_TARBALL}" -C "${TMPDIR_TG}/"
			find "${TMPDIR_TG}" -name 'topgrade' -type f \
				-exec install -m 0755 {} /usr/bin/topgrade \;
			echo "topgrade installed: $(topgrade --version 2>/dev/null || echo 'unknown version')"
		else
			echo "topgrade: no musl x86_64 tarball found in release assets; skipping."
		fi
	else
		echo "topgrade: failed to fetch release info from GitHub; skipping."
	fi
	rm -rf "${TMPDIR_TG}"
}
