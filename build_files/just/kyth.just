# KythOS ujust recipes. Split by domain under kyth/ — this file just wires
# the pieces together. `just` resolves each import relative to this file, so
# the whole kyth/ directory ships alongside this one (see branding.sh).
import "kyth/common.just"
import "kyth/system.just"
import "kyth/performance.just"
import "kyth/gpu-drivers.just"
import "kyth/gaming.just"
import "kyth/containers.just"
import "kyth/dev-tools.just"
import "kyth/streaming.just"
