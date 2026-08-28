#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
# `just test` was the one quality gate that ran the ~180-file suite at full
# priority with no memory cap: validate.sh, run-quality.sh and ci-preflight.sh
# all wrap themselves, so a plain `pytest` was the cheapest way to crash the
# desktop session. Same wrapper, same properties.
# shellcheck source=lib/desktop-throttle.sh disable=SC1091
source "${repo_root}/build_files/scripts/lib/desktop-throttle.sh"
kyth_deprioritize_on_desktop "$@"

cd "${repo_root}"

test_python="python3"
if [[ -x .venv-gui/bin/python ]]; then
	test_python=".venv-gui/bin/python"
fi

exec "${test_python}" -m pytest -q "$@"
