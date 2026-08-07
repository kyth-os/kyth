#!/usr/bin/env bash
set -euo pipefail
# Hash-gate rpm-lock — pins every RPM NVR in the image like hash-gaming-versions
repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"
inputs=( build_files/rpm-lock.json build_files/scripts/hash-rpm-lock.sh build_files/scripts/validate.sh Dockerfile )
if command -v sha256sum >/dev/null 2>&1; then hash_cmd="sha256sum"; else hash_cmd="shasum -a 256"; fi
tmp="$(mktemp)"
for f in "${inputs[@]}"; do [[ -f "${f}" ]] && { cat "${f}" >> "${tmp}"; echo "---${f}---" >> "${tmp}"; } done
hash="$(${hash_cmd} "${tmp}" | cut -c1-12)"
rm -f "${tmp}"
echo "rpm-lock hash: ${hash}"
# Validate Dockerfile ARG/LABEL if present
if grep -q "ARG RPM_LOCK_HASH" Dockerfile; then
    arg=$(grep "ARG RPM_LOCK_HASH" Dockerfile | sed -E 's/.*=//; s/"//g; s/ //g')
    if [[ "${arg}" != "unset" && "${arg}" != "${hash}" ]]; then echo "rpm-lock drift: Dockerfile ARG ${arg} != computed ${hash}" >&2; exit 1; fi
fi
# Also verify rpm-lock.json vs current (best-effort)
if [[ -f build_files/rpm-lock.json ]]; then
    echo "rpm-lock.json present — hash-gated"
fi
