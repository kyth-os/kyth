# shellcheck shell=bash
install_winetricks() {
	local WINETRICKS_REPO_API="https://api.github.com/repos/Winetricks/winetricks/releases/latest"
	local TMPDIR_WTX
	TMPDIR_WTX=$(mktemp -d)
	local release_json="${TMPDIR_WTX}/release.json"
	mkdir -p "$(realpath -m /usr/local)/bin"

	if curl -fsSL "${CURL_COMMON_ARGS[@]}" "${CURL_AUTH_ARGS[@]}" "${WINETRICKS_REPO_API}" -o "${release_json}" 2>/dev/null; then
		local WTX_SCRIPT_URL
		WTX_SCRIPT_URL=$(
			grep -oP 'https://[^"]+' "${release_json}" |
				grep '/releases/download/' |
				grep -v '\.sha256sum\|\.asc\|\.sig\|source' |
				grep 'winetricks$' | head -n1 || true
		)
		if [[ -n "${WTX_SCRIPT_URL}" ]]; then
			curl -fsSL "${CURL_COMMON_ARGS[@]}" "${WTX_SCRIPT_URL}" -o "${TMPDIR_WTX}/winetricks"
			verify_release_asset "${release_json}" "${TMPDIR_WTX}/winetricks" \
				"winetricks" "${TMPDIR_WTX}"
			head -1 "${TMPDIR_WTX}/winetricks" | grep -q '^#!' ||
				{
					echo "ERROR: winetricks does not look like a shell script after hash verification"
					exit 1
				}
			install -m 0755 "${TMPDIR_WTX}/winetricks" /usr/local/bin/winetricks
			echo "winetricks installed: $(winetricks --version 2>/dev/null || echo 'unknown version')"
		else
			echo "winetricks: no release asset found in GitHub response; skipping."
		fi
	else
		echo "winetricks: failed to fetch release info from GitHub; skipping."
	fi
	rm -rf "${TMPDIR_WTX}"
}
