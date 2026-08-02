# shellcheck shell=bash
# Shared fragment orchestrator for numbered *.sh fragment directories.
#
# Usage:
#   source /path/to/lib/fragment-runner.sh
#   run_fragments "packages"   # runs fragments with bash
#   run_fragments "branding"  # runs fragments with source (default)
#
# The second argument controls execution mode:
#   "bash"   — each fragment runs in a subshell via bash (isolated)
#   "source" — each fragment is sourced into the current shell (shared state)
#   Default is "source" since branding fragments share state.

run_fragments() {
	local dir_name="${1:?fragment directory name required}"
	local mode="${2:-source}"
	local HERE FRAG_DIR frag frag_dir frag_name previous_dir fragments

	HERE="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
	if [[ -d "${HERE}/${dir_name}" ]]; then
		FRAG_DIR="${HERE}/${dir_name}"
	elif [[ -d "/ctx/${dir_name}" ]]; then
		FRAG_DIR="/ctx/${dir_name}"
	else
		echo "${dir_name} fragments not found (looked in ${HERE}/${dir_name} and /ctx/${dir_name})" >&2
		exit 1
	fi

	mapfile -t fragments < <(find "${FRAG_DIR}" -type f -name '*.sh' | sort)
	if ((${#fragments[@]} == 0)); then
		echo "No ${dir_name} fragments in ${FRAG_DIR}" >&2
		exit 1
	fi

	for frag in "${fragments[@]}"; do
		frag_dir="$(dirname "${frag}")"
		frag_name="$(basename "${frag}")"
		if [[ "${mode}" == "source" ]]; then
			previous_dir="${PWD}"
			cd "${frag_dir}" || return 1
			# shellcheck disable=SC1090
			source "./${frag_name}"
			cd "${previous_dir}" || return 1
		else
			(
				cd "${frag_dir}" || exit 1
				bash "./${frag_name}"
			)
		fi
	done
}
