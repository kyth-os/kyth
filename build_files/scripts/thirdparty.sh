#!/bin/bash

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/lib/thirdparty-common.sh"

# Each per-tool fragment defines its own install_<name> function.
for _fragment in "${HERE}/thirdparty"/*.sh; do
	# shellcheck source=/dev/null
	source "${_fragment}"
done
unset _fragment

# ── Parallel download + install ───────────────────────────────────────────────
_launch umu install_umu
_launch latencyflex install_latencyflex
if is_enabled "${ENABLE_SCX:-1}"; then
	_launch scx install_scx
fi

_wait_and_report
