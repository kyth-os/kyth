#!/bin/bash

set -euo pipefail

# Branding is one Docker build layer (see Dockerfile), split into independent,
# numbered sections under branding/ so each concern (theming, Plasma layout,
# boot splash, menu groups, ...) lives in its own file. Sections run in
# filename order and do not share state, so the split is purely organizational.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/lib/fragment-runner.sh"
source "${HERE}/lib/config-helpers.sh"
run_fragments "branding" "source"
