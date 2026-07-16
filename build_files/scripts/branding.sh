#!/bin/bash

set -euo pipefail

# Branding is one Docker build layer (see Dockerfile), split into independent,
# numbered sections under branding/ so each concern (theming, Plasma layout,
# boot splash, menu groups, ...) lives in its own file. Sections run in
# filename order and do not share state, so the split is purely organizational.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
branding_dir="${script_dir}/branding"

for section in "${branding_dir}"/*.sh; do
	# shellcheck source=/dev/null
	source "${section}"
done
