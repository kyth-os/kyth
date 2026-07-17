#!/bin/bash
# shellcheck shell=bash
# Thin orchestrator for domain sysconfig fragments.
# Fragments live in build_files/scripts/sysconfig/*.sh and are run in sorted order.
set -euo pipefail

# When executed from the container build (bound at /ctx/sysconfig-static.sh),
# fragments are mounted alongside at /ctx/sysconfig/. In the repo checkout they
# sit next to this file under scripts/sysconfig/.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "${HERE}/sysconfig" ]]; then
  FRAG_DIR="${HERE}/sysconfig"
elif [[ -d /ctx/sysconfig ]]; then
  FRAG_DIR=/ctx/sysconfig
else
  echo "sysconfig fragments not found (looked in ${HERE}/sysconfig and /ctx/sysconfig)" >&2
  exit 1
fi

shopt -s nullglob
fragments=("${FRAG_DIR}"/*.sh)
if ((${#fragments[@]} == 0)); then
  echo "No sysconfig fragments in ${FRAG_DIR}" >&2
  exit 1
fi

for frag in "${fragments[@]}"; do
  # shellcheck disable=SC1090
  bash "${frag}"
done
