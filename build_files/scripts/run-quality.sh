#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"
quality_python="python3"
if [[ -x .venv-quality/bin/python ]]; then
	quality_python=".venv-quality/bin/python"
fi

if ! "${quality_python}" -m coverage --version >/dev/null 2>&1 ||
	! "${quality_python}" -m ruff --version >/dev/null 2>&1; then
	echo "Quality tools are unavailable. Run: just setup-quality" >&2
	exit 1
fi
echo "==> Python correctness"
# --config pins the root ruff.toml explicitly instead of relying on directory
# walk-up discovery. build_files/{kyth-installer,kyth-welcome,kyth_shared} each
# carry a pyproject.toml with no [tool.ruff] table; ruff is supposed to skip
# those and keep walking up to this repo's root ruff.toml, but that discovery
# step observably flaked between runs on identical input (clean vs. the full
# default pyflakes rule set). Pinning removes the ambiguity outright.
"${quality_python}" -m ruff check --config "${repo_root}/ruff.toml" build_files tests .github/scripts

echo "==> Blind-except audit (BLE001, grandfathered — new top-level files must be clean)"
if ! "${quality_python}" -m ruff check --config "${repo_root}/ruff.toml" --select BLE001 --statistics build_files tests .github/scripts 2>&1 | tee /tmp/kyth-ble001-stats.txt; then
  echo "(BLE001 violations exist in grandfathered files — see /tmp/kyth-ble001-stats.txt)" >&2
fi
# Enforce BLE001 only outside grandfathered globs: any new top-level *.py must be clean
shopt -s nullglob
_top_level_py=(./*.py)
if ((${#_top_level_py[@]})); then
  ble_top_level="$("${quality_python}" -m ruff check --config "${repo_root}/ruff.toml" --select BLE001 --output-format concise "${_top_level_py[@]}" 2>&1 || true)"
  # ruff emits a warning when no file matches; filter it if somehow still present
  ble_top_level="$(printf '%s\n' "${ble_top_level}" | grep -v "Failed to lint" || true)"
  if [ -n "${ble_top_level}" ]; then
    echo "BLE001 in top-level files (must be fixed):" >&2
    echo "${ble_top_level}" >&2
    exit 1
  fi
fi
shopt -u nullglob

echo "==> Python coverage"
PYTHONPATH=build_files/kyth_shared:build_files/kyth-welcome:build_files/kyth-installer "${quality_python}" -m coverage erase
PYTHONPATH=build_files/kyth_shared:build_files/kyth-welcome:build_files/kyth-installer "${quality_python}" -m coverage run -m unittest discover -s tests -b
"${quality_python}" -m coverage report -m
"${quality_python}" -m coverage json
if [[ "${1:-}" == "--changed-only" ]]; then
  "${quality_python}" build_files/scripts/check-critical-coverage.py --changed-only
else
  "${quality_python}" build_files/scripts/check-critical-coverage.py
fi
"${quality_python}" -m coverage xml
"${quality_python}" -m coverage html

echo "==> Quality gates passed"
