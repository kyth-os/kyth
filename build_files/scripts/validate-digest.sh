#!/usr/bin/env bash
# validate-digest.sh — check whether a value is a well-formed "sha256:<64 hex>"
# OCI digest. Single source of truth for the digest-format regex repeated
# across the CI workflows.
#
# Usage as an assertion (aborts the step under `set -e` if invalid):
#   build_files/scripts/validate-digest.sh "${DIGEST}"
#
# Usage as a boolean predicate in a compound condition:
#   if ! build_files/scripts/validate-digest.sh "${DIGEST}" 2>/dev/null; then ...
#
# Exits 0 silently if VALUE matches ^sha256:[0-9a-f]{64}$.
# Exits 1 with an error on stderr otherwise.
set -euo pipefail

value="${1:-}"
if [[ ! "${value}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
	echo "::error::Not a well-formed sha256 digest: '${value}'" >&2
	exit 1
fi
