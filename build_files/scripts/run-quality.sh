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
"${quality_python}" -m ruff check build_files tests .github/scripts

echo "==> Python coverage"
"${quality_python}" -m coverage erase
"${quality_python}" -m coverage run -m unittest discover -s tests
"${quality_python}" -m coverage report -m
"${quality_python}" -m coverage json
"${quality_python}" build_files/scripts/check-critical-coverage.py
"${quality_python}" -m coverage xml
"${quality_python}" -m coverage html

echo "==> Quality gates passed"
