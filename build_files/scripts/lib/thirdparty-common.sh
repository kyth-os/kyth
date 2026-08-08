# shellcheck shell=bash
# Shared helpers for thirdparty tool installer fragments.
# Source this before defining per-tool install functions.

THIRDPARTY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${THIRDPARTY_LIB_DIR}/curl-common.sh"
CURL_COMMON_ARGS+=(--max-time 300)

is_enabled() {
	case "${1,,}" in
	1 | true | yes | on) return 0 ;;
	*) return 1 ;;
	esac
}

require_release_tag() {
	local name=$1 value=$2
	if [[ ! "${value}" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]]; then
		echo "ERROR: ${name} is not a safe immutable release tag: ${value}" >&2
		return 1
	fi
}

# verify_release_asset RELEASE_JSON TARBALL_PATH TARBALL_NAME TMPDIR
verify_release_asset() {
	local release_json=$1
	local tarball_path=$2
	local tarball_name=$3
	local tmpdir=$4

	local checksum_url="" algo=""
	local expected_hash=""

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
	for ext in sha256 sha512 sha256sum sha512sum SHA256 SHA512; do
		local candidate
		candidate=$(grep -oP "https://[^\"]+" "${release_json}" |
			grep -F "${tarball_name}.${ext}" | head -n1 || true)
		if [[ -n "${candidate}" ]]; then
			checksum_url="${candidate}"
			case "${ext,,}" in
			*512*) algo="sha512" ;;
			*) algo="sha256" ;;
			esac
			break
		fi
	done

	# 2. If no sidecar, look for a manifest
	if [[ -z "${checksum_url}" ]]; then
		for pattern in SHA256SUMS SHA512SUMS checksums.txt sha256sums.txt sha512sums.txt; do
			local candidate
			candidate=$(grep -oP "https://[^\"]+" "${release_json}" |
				grep -iF "${pattern}" | head -n1 || true)
			if [[ -n "${candidate}" ]]; then
				checksum_url="${candidate}"
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

	expected_hash=$(grep -F "${tarball_name}" "${checksum_file_path}" |
		awk '{print $1}' | head -n1 || true)
	if [[ -z "${expected_hash}" ]]; then
		expected_hash=$(awk '{print $1}' "${checksum_file_path}" | head -n1 || true)
	fi

	if [[ -z "${expected_hash}" ]]; then
		echo "ERROR: Could not extract hash for ${tarball_name} from checksum file." >&2
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

# Parallel execution helpers
declare -A _pids=()
declare -A _sf=()

_launch() {
	local name=$1
	shift
	local sf
	sf=$(mktemp)
	_sf[$name]=$sf
	("$@") && echo 0 >"$sf" || echo $? >"$sf" &
	_pids[$name]=$!
}

_wait_and_report() {
	wait
	local -a _failed=()
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
}
