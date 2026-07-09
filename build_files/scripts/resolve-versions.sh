#!/bin/bash
# resolve-versions.sh — single source of truth for build-time version lookups.
#
# Used by both the Justfile and .github/workflows/build.yml so the API parsing
# logic exists in exactly one place. Prints the resolved value on stdout;
# diagnostics go to stderr.
#
# Subcommands:
#   proton-cachyos   Latest Proton-CachyOS release tag. Prints "" on failure so
#                    proton-cachyos.sh falls back to the /latest release
#                    endpoint instead of requesting a nonexistent tag.
#   thirdparty-hash  16-char digest of the five thirdparty tool release tags.
#                    Only used as a Docker layer cache-bust value: when every
#                    tool's tag is unchanged the thirdparty layer is a cache hit.
#   cachyos-kernel   Latest succeeded kernel-cachyos COPR build (version-release).
#                    Falls back to today's date so a COPR API outage busts the
#                    kernel layer cache instead of silently freezing it.
#
# Set GITHUB_TOKEN to authenticate GitHub API calls — avoids the 60 req/hr
# unauthenticated rate limit on shared CI runner IP ranges.

set -euo pipefail

CURL_ARGS=(-fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 60)

THIRDPARTY_REPOS=(
	topgrade-rs/topgrade
	Winetricks/winetricks
	Open-Wine-Components/umu-launcher
	ishitatsuyuki/LatencyFleX
	sched-ext/scx
)

# Prints the latest release tag of GitHub repo $1, or "" on any failure.
gh_latest_tag() {
	local auth=()
	[[ -n "${GITHUB_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
	local tmp
	tmp=$(mktemp)
	if curl "${CURL_ARGS[@]}" "${auth[@]}" -o "${tmp}" "https://api.github.com/repos/$1/releases/latest" 2>/dev/null; then
		python3 - "${tmp}" <<'PY' 2>/dev/null || true
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh).get("tag_name", ""))
PY
	fi
	rm -f "${tmp}"
}

cmd_proton_cachyos() {
	local tag
	tag=$(gh_latest_tag CachyOS/proton-cachyos)
	[[ -n "${tag}" ]] || echo "WARNING: could not resolve latest Proton-CachyOS release; proton-cachyos.sh will use the /latest endpoint" >&2
	printf '%s\n' "${tag}"
}

cmd_thirdparty_hash() {
	# Fetch all tags in parallel so the total wait is the slowest single request.
	local tmp repo
	tmp=$(mktemp -d)
	for repo in "${THIRDPARTY_REPOS[@]}"; do
		gh_latest_tag "${repo}" >"${tmp}/${repo//\//_}" &
	done
	wait

	local tags="" tag
	for repo in "${THIRDPARTY_REPOS[@]}"; do
		tag=$(cat "${tmp}/${repo//\//_}")
		[[ -n "${tag}" ]] || echo "WARNING: could not resolve latest release of ${repo}" >&2
		echo "  ${repo}: ${tag:-unknown}" >&2
		tags+="${tag:-unknown}"
	done
	rm -rf "${tmp}"
	printf '%s' "${tags}" | sha256sum | cut -c1-16
}

cmd_cachyos_kernel() {
	# COPR api_3 returns the package object at the top level (there is no
	# "package" wrapper key).
	local tmp nvr
	tmp=$(mktemp)
	if curl "${CURL_ARGS[@]}" -o "${tmp}" "https://copr.fedorainfracloud.org/api_3/package/?ownername=bieszczaders&projectname=kernel-cachyos&packagename=kernel-cachyos&with_latest_succeeded_build=true" 2>/dev/null; then
		nvr=$(
			python3 - "${tmp}" <<'PY' 2>/dev/null || true
import datetime, json, sys

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        sp = json.load(fh)["builds"]["latest_succeeded"]["source_package"]
    ver = sp.get("version") or ""
    rel = sp.get("release") or ""
    nvr = f"{ver}-{rel}".strip("-")
except Exception:
    nvr = ""
print(nvr or datetime.date.today().isoformat())
PY
		)
	else
		nvr=$(date +%Y-%m-%d)
	fi
	rm -f "${tmp}"
	printf '%s\n' "${nvr:-$(date +%Y-%m-%d)}"
}

case "${1:-}" in
proton-cachyos) cmd_proton_cachyos ;;
thirdparty-hash) cmd_thirdparty_hash ;;
cachyos-kernel) cmd_cachyos_kernel ;;
*)
	echo "usage: $0 {proton-cachyos|thirdparty-hash|cachyos-kernel}" >&2
	exit 2
	;;
esac
