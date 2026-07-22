# shellcheck shell=bash
install_scx() {
	: "${SCX_VERSION:?SCX_VERSION must be an exact release tag}"
	require_release_tag SCX_VERSION "${SCX_VERSION}"
	local SCX_REPO_API="https://api.github.com/repos/sched-ext/scx/releases/tags/${SCX_VERSION}"
	local TMPDIR_SCX
	TMPDIR_SCX=$(mktemp -d)
	local release_json="${TMPDIR_SCX}/release.json"

	if curl -fsSL "${CURL_COMMON_ARGS[@]}" "${CURL_AUTH_ARGS[@]}" "${SCX_REPO_API}" -o "${release_json}" 2>/dev/null; then
		local SCX_TARBALL_URL
		SCX_TARBALL_URL=$(
			grep -oP 'https://[^"]+\.tar\.(gz|zst)' "${release_json}" |
				grep -i 'x86.64\|x86_64\|amd64' |
				grep -iv 'source' |
				head -n1
		) || true

		if [[ -n "${SCX_TARBALL_URL}" ]]; then
			local SCX_TARBALL
			SCX_TARBALL=$(basename "${SCX_TARBALL_URL}")
			echo "scx: downloading ${SCX_TARBALL}"
			curl -fsSL "${CURL_COMMON_ARGS[@]}" "${SCX_TARBALL_URL}" -o "${TMPDIR_SCX}/${SCX_TARBALL}"
			verify_release_asset "${release_json}" "${TMPDIR_SCX}/${SCX_TARBALL}" \
				"${SCX_TARBALL}" "${TMPDIR_SCX}"
			tar -xf "${TMPDIR_SCX}/${SCX_TARBALL}" -C "${TMPDIR_SCX}/"

			find "${TMPDIR_SCX}" \( -name 'scx_*' -o -name 'scx_loader' \) -type f \
				-exec install -m 0755 {} /usr/bin/ \;

			if command -v scx_loader >/dev/null 2>&1; then
				mkdir -p /usr/lib/systemd/system
				cat >/usr/lib/systemd/system/scx_loader.service <<'SCXSVCEOF'
[Unit]
Description=sched-ext userspace scheduler loader
Documentation=https://github.com/sched-ext/scx
After=basic.target

[Service]
Type=simple
EnvironmentFile=-/etc/scx/scx_loader.conf
ExecStart=/usr/bin/scx_loader
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SCXSVCEOF

				local SCX_SCHEDULER=""
				local sched
				for sched in scx_lavd scx_rusty scx_bpfland; do
					if command -v "$sched" >/dev/null 2>&1; then
						SCX_SCHEDULER="$sched"
						break
					fi
				done

				if [[ -n "$SCX_SCHEDULER" ]]; then
					mkdir -p /etc/scx
					cat >/etc/scx/scx_loader.conf <<SCXEOF
SCX_SCHEDULER=${SCX_SCHEDULER}
SCXEOF
					systemctl enable scx_loader.service 2>/dev/null || true
					echo "scx: enabled ${SCX_SCHEDULER}"
				else
					echo "ERROR: scx: pinned release ${SCX_VERSION} contains no supported scheduler binaries." >&2
					rm -rf "${TMPDIR_SCX}"
					return 1
				fi
			else
				echo "ERROR: scx: pinned release ${SCX_VERSION} contains no scx_loader." >&2
				rm -rf "${TMPDIR_SCX}"
				return 1
			fi
		else
			echo "ERROR: scx: pinned release ${SCX_VERSION} has no x86_64 tarball." >&2
			rm -rf "${TMPDIR_SCX}"
			return 1
		fi
	else
		echo "ERROR: scx: failed to fetch pinned release ${SCX_VERSION}." >&2
		rm -rf "${TMPDIR_SCX}"
		return 1
	fi

	rm -rf "${TMPDIR_SCX}"
}
