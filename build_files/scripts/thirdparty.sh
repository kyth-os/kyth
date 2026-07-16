#!/bin/bash

set -euo pipefail

# shellcheck source=lib/curl-common.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib/curl-common.sh"
CURL_COMMON_ARGS+=(--max-time 300)

is_enabled() {
	case "${1,,}" in
	1 | true | yes | on) return 0 ;;
	*) return 1 ;;
	esac
}

# verify_release_asset RELEASE_JSON TARBALL_PATH TARBALL_NAME TMPDIR
#
# Looks for a checksum file in the GitHub release JSON that corresponds to
# TARBALL_NAME, downloads it, and verifies TARBALL_PATH against it.
# Supports common patterns:
#   - <tarball>.sha256 / <tarball>.sha512 (per-file sidecar)
#   - SHA256SUMS / SHA512SUMS / checksums.txt (multi-file manifest)
#
# Returns:
#   0  — checksum verified OK
#  exit 1 — checksum missing, unreadable, or mismatched
verify_release_asset() {
	local release_json=$1
	local tarball_path=$2
	local tarball_name=$3
	local tmpdir=$4

	local checksum_url="" algo=""
	local expected_hash=""

	# 0. Prefer immutable per-asset digests embedded directly in the GitHub
	# release metadata when available.
	local asset_digest=""
	asset_digest=$(
		python3 - "$release_json" "$tarball_name" <<'PY'
import json
import sys

release_json, tarball_name = sys.argv[1], sys.argv[2]
with open(release_json, "r", encoding="utf-8") as f:
    data = json.load(f)

for asset in data.get("assets", []):
    if asset.get("name") == tarball_name:
        print(asset.get("digest", ""))
        break
PY
	)
	if [[ -n "${asset_digest}" ]]; then
		if [[ "${asset_digest}" == *:* ]]; then
			algo="${asset_digest%%:*}"
			expected_hash="${asset_digest#*:}"
		elif [[ "${asset_digest}" =~ ^[0-9a-fA-F]{64}$ ]]; then
			algo="sha256"
			expected_hash="${asset_digest}"
		elif [[ "${asset_digest}" =~ ^[0-9a-fA-F]{128}$ ]]; then
			algo="sha512"
			expected_hash="${asset_digest}"
		else
			algo=""
			expected_hash=""
		fi

		if [[ -n "${algo}" && -n "${expected_hash}" ]]; then
			local actual_hash=""
			case "${algo}" in
			sha256) actual_hash=$(sha256sum "${tarball_path}" | awk '{print $1}') ;;
			sha512) actual_hash=$(sha512sum "${tarball_path}" | awk '{print $1}') ;;
			*)
				echo "WARNING: Unsupported release digest algorithm '${algo}' for ${tarball_name}; falling back to checksum files." >&2
				actual_hash=""
				;;
			esac

			if [[ -n "${actual_hash}" ]]; then
				if [[ "${actual_hash}" != "${expected_hash,,}" ]]; then
					echo "ERROR: ${algo^^} mismatch for ${tarball_name}!" >&2
					echo "  Expected: ${expected_hash}" >&2
					echo "  Got:      ${actual_hash}" >&2
					exit 1
				fi

				echo "${tarball_name}: ${algo^^} verified OK (release asset digest)"
				return 0
			fi
		fi
	fi

	# 1. Look for a per-file sidecar: <tarball>.sha256, .sha512, .sha256sum, .sha512sum
	# sha256sum/sha512sum extensions cover Winetricks-style naming.
	for ext in sha256 sha512 sha256sum sha512sum SHA256 SHA512; do
		local candidate
		candidate=$(grep -oP "https://[^\"]+" "${release_json}" |
			grep -F "${tarball_name}.${ext}" | head -n1 || true)
		if [[ -n "${candidate}" ]]; then
			checksum_url="${candidate}"
			# Normalise: sha256sum/SHA256 → sha256; sha512sum/SHA512 → sha512
			case "${ext,,}" in
			*512*) algo="sha512" ;;
			*) algo="sha256" ;;
			esac
			break
		fi
	done

	# 2. If no sidecar, look for a manifest (SHA256SUMS, checksums.txt, etc.)
	if [[ -z "${checksum_url}" ]]; then
		for pattern in SHA256SUMS SHA512SUMS checksums.txt sha256sums.txt sha512sums.txt; do
			local candidate
			candidate=$(grep -oP "https://[^\"]+" "${release_json}" |
				grep -iF "${pattern}" | head -n1 || true)
			if [[ -n "${candidate}" ]]; then
				checksum_url="${candidate}"
				# Infer algo from filename
				if echo "${pattern,,}" | grep -q 512; then
					algo="sha512"
				else
					algo="sha256"
				fi
				break
			fi
		done
	fi

	if [[ -z "${checksum_url}" ]]; then
		echo "ERROR: No checksum file found for ${tarball_name} in release assets." >&2
		echo "Refusing to install ${tarball_name} without integrity metadata." >&2
		exit 1
	fi

	local checksum_file_path="${tmpdir}/checksum_file"
	if ! curl -fsSL "${CURL_COMMON_ARGS[@]}" "${checksum_url}" -o "${checksum_file_path}"; then
		echo "ERROR: Failed to download checksum file from ${checksum_url}." >&2
		echo "Refusing to install ${tarball_name} without a trusted checksum." >&2
		exit 1
	fi

	# If this is a multi-file manifest, filter to just the line for our tarball
	expected_hash=$(grep -F "${tarball_name}" "${checksum_file_path}" |
		awk '{print $1}' | head -n1 || true)

	# Fallback: if the file contains only a bare hash (sidecar style), use it directly
	if [[ -z "${expected_hash}" ]]; then
		expected_hash=$(awk '{print $1}' "${checksum_file_path}" | head -n1 || true)
	fi

	if [[ -z "${expected_hash}" ]]; then
		echo "ERROR: Could not extract hash for ${tarball_name} from checksum file." >&2
		echo "Refusing to install ${tarball_name} with unverifiable checksum metadata." >&2
		exit 1
	fi

	local actual_hash=""
	case "${algo}" in
	sha256) actual_hash=$(sha256sum "${tarball_path}" | awk '{print $1}') ;;
	sha512) actual_hash=$(sha512sum "${tarball_path}" | awk '{print $1}') ;;
	esac

	if [[ "${actual_hash}" != "${expected_hash}" ]]; then
		echo "ERROR: ${algo^^} mismatch for ${tarball_name}!" >&2
		echo "  Expected: ${expected_hash}" >&2
		echo "  Got:      ${actual_hash}" >&2
		exit 1
	fi

	echo "${tarball_name}: ${algo^^} verified OK"
	return 0
}

release_asset_has_verification() {
	local release_json=$1
	local tarball_name=$2

	local asset_digest=""
	asset_digest=$(
		python3 - "$release_json" "$tarball_name" <<'PY'
import json
import sys

release_json, tarball_name = sys.argv[1], sys.argv[2]
with open(release_json, "r", encoding="utf-8") as f:
    data = json.load(f)

for asset in data.get("assets", []):
    if asset.get("name") == tarball_name and asset.get("digest"):
        print(asset["digest"])
        break
PY
	)
	if [[ -n "${asset_digest}" ]]; then
		return 0
	fi

	for ext in sha256 sha512 sha256sum sha512sum SHA256 SHA512; do
		if grep -oP 'https://[^"]+' "${release_json}" | grep -Fq "${tarball_name}.${ext}"; then
			return 0
		fi
	done

	for pattern in SHA256SUMS SHA512SUMS checksums.txt sha256sums.txt sha512sums.txt; do
		if grep -oP 'https://[^"]+' "${release_json}" | grep -iFq "${pattern}"; then
			return 0
		fi
	done

	return 1
}

# ── Per-tool install functions ────────────────────────────────────────────────
# Each function is self-contained and runs in its own subshell so they can be
# backgrounded safely. All write to distinct paths; no shared mutable state.

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

install_scx() {
	local SCX_REPO_API="https://api.github.com/repos/sched-ext/scx/releases/latest"
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
					echo "scx: no scheduler binaries found in archive"
				fi
			else
				echo "scx: scx_loader not found after extraction"
			fi
		else
			echo "scx: no x86_64 tarball found in release assets; skipping."
		fi
	else
		echo "scx: failed to fetch release info from GitHub; skipping."
	fi

	rm -rf "${TMPDIR_SCX}"
}

install_msfonts() {
	# Microsoft "Core Fonts for the Web" — legally redistributable TrueType fonts
	# shipped by Windows since the late 1990s. Arial, Times New Roman, Verdana,
	# Georgia, Courier New, Impact, Trebuchet MS, Comic Sans, Andale Mono, Webdings.
	# Required for correct rendering of Office documents and many websites that
	# hard-code "Arial" or "Times New Roman" without web-safe fallbacks.
	# Without these fonts, LibreOffice substitutes Liberation metrics-compatible
	# equivalents which are visually close but not pixel-identical to Windows.
	local tmp
	tmp=$(mktemp -d)

	local sf_base="https://downloads.sourceforge.net/project/corefonts/the%20fonts/final"
	# The corefonts installers have been immutable since 2002 — pin their
	# sha256 sums so SourceForge mirrors are held to the same integrity bar as
	# every GitHub release this script installs.
	local -A exe_sha256=(
		[andale32.exe]=0524fe42951adc3a7eb870e32f0920313c71f170c859b5f770d82b4ee111e970
		[arial32.exe]=85297a4d146e9c87ac6f74822734bdee5f4b2a722d7eaa584b7f2cbf76f478f6
		[arialb32.exe]=a425f0ffb6a1a5ede5b979ed6177f4f4f4fdef6ae7c302a7b7720ef332fec0a8
		[comic32.exe]=9c6df3feefde26d4e41d4a4fe5db2a89f9123a772594d7f59afd062625cd204e
		[courie32.exe]=bb511d861655dde879ae552eb86b134d6fae67cb58502e6ff73ec5d9151f3384
		[georgi32.exe]=2c2c7dcda6606ea5cf08918fb7cd3f3359e9e84338dc690013f20cd42e930301
		[impact32.exe]=6061ef3b7401d9642f5dfdb5f2b376aa14663f6275e60a51207ad4facf2fccfb
		[times32.exe]=db56595ec6ef5d3de5c24994f001f03b2a13e37cee27bc25c58f6f43e8f807ab
		[trebuc32.exe]=5a690d9bb8510be1b8b4fe49f1f2319651fe51bbe54775ddddd8ef0bd07fdac9
		[verdan32.exe]=c1cb61255e363166794e47664e2f21af8e3a26cb6346eb8d2ae2fa85dd5aad96
		[webdin32.exe]=64595b5abc1080fba8610c5c34fab5863408e806aafe84653ca8575bed17d75a
	)
	local -a exes=(
		andale32.exe arial32.exe arialb32.exe comic32.exe courie32.exe
		georgi32.exe impact32.exe times32.exe trebuc32.exe verdan32.exe
		webdin32.exe
	)

	local failed=0
	for exe in "${exes[@]}"; do
		if ! curl --retry 3 --retry-delay 3 -fsSL -o "${tmp}/${exe}" "${sf_base}/${exe}"; then
			echo "msfonts: failed to download ${exe}" >&2
			((failed++)) || true
		fi
	done

	if [[ $failed -gt 0 ]]; then
		rm -rf "$tmp"
		echo "msfonts: ${failed} download(s) failed — skipping font install" >&2
		return 1
	fi

	local actual
	for exe in "${exes[@]}"; do
		actual=$(sha256sum "${tmp}/${exe}" | awk '{print $1}')
		if [[ "${actual}" != "${exe_sha256[${exe}]}" ]]; then
			rm -rf "$tmp"
			echo "ERROR: msfonts: SHA256 mismatch for ${exe}!" >&2
			echo "  Expected: ${exe_sha256[${exe}]}" >&2
			echo "  Got:      ${actual}" >&2
			exit 1
		fi
	done
	echo "msfonts: all ${#exes[@]} installers SHA256 verified OK"

	mkdir -p /usr/share/fonts/msttcorefonts
	for exe in "${exes[@]}"; do
		local exdir="${tmp}/x_${exe%.exe}"
		mkdir -p "$exdir"
		# Cabinet archives may fail silently on non-font files; extract what we can.
		cabextract -q -d "$exdir" "${tmp}/${exe}" 2>/dev/null || true
		find "$exdir" -iname "*.ttf" -exec cp {} /usr/share/fonts/msttcorefonts/ \;
	done

	# Some cabinets ship uppercase .TTF — normalize to lowercase for consistent queries.
	find /usr/share/fonts/msttcorefonts -name "*.TTF" | while IFS= read -r f; do
		mv "$f" "${f%.TTF}.ttf"
	done

	local count
	count=$(find /usr/share/fonts/msttcorefonts -name "*.ttf" | wc -l)
	fc-cache -f /usr/share/fonts/msttcorefonts
	rm -rf "$tmp"
	echo "msfonts: installed ${count} TrueType fonts"
}

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
		# Prefer a combined zip (x64/win64); skip symbols, debug, or win32-only builds.
		local OS_URL
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

# ── Parallel download + install ───────────────────────────────────────────────
# All tools are independent — fan them out and collect results.
# Background jobs don't propagate set -e to the parent; track exit codes via
# temporary status files and fail loudly if any tool's install failed hard
# (checksum mismatch, corrupt archive, etc.).

declare -A _pids=()
declare -A _sf=()

_launch() {
	local name=$1
	shift
	local sf
	sf=$(mktemp)
	_sf[$name]=$sf
	# Subshell inherits set -euo pipefail from the script; capture its exit code.
	("$@") && echo 0 >"$sf" || echo $? >"$sf" &
	_pids[$name]=$!
}

_launch topgrade install_topgrade
_launch winetricks install_winetricks
_launch umu install_umu
_launch latencyflex install_latencyflex
_launch opticscaler install_opticscaler
_launch msfonts install_msfonts
if is_enabled "${ENABLE_SCX:-1}"; then
	_launch scx install_scx
fi

# Wait for all background jobs and check their status files.
wait

_failed=()
for _name in "${!_sf[@]}"; do
	_rc=$(cat "${_sf[$_name]}" 2>/dev/null || echo 1)
	rm -f "${_sf[$_name]}"
	[[ "${_rc}" -eq 0 ]] || _failed+=("${_name} (exit ${_rc})")
done
unset _pids _sf _name _rc

if [[ ${#_failed[@]} -gt 0 ]]; then
	echo "ERROR: thirdparty installs failed: ${_failed[*]}" >&2
	exit 1
fi
