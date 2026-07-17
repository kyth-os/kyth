# KythOS ujust recipes. Split by domain under kyth/ — this file just wires
# the pieces together. `just` resolves each import relative to this file, so
# the whole kyth/ directory ships alongside this one (see branding.sh).
import "kyth/common.just"
import "kyth/system-updates.just"
import "kyth/diagnostics.just"
import "kyth/dualboot.just"
import "kyth/secureboot.just"
import "kyth/desktop-tools.just"
import "kyth/performance.just"
import "kyth/gpu-drivers.just"
import "kyth/gaming.just"
import "kyth/containers.just"
import "kyth/dev-tools.just"
import "kyth/streaming.just"
