#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/check-multilib.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/../lib/check-multilib.sh"

# ── mimalloc high-performance allocator ──────────────────────────────────────
# Microsoft's mimalloc is a general-purpose allocator with excellent performance.
# We install both 64-bit and 32-bit versions so it can be preloaded for both.
# No --skip-unavailable / || true here: sysconfig/46-mimalloc-preload.sh sets
# LD_PRELOAD=libmimalloc.so unconditionally for every desktop session, so a
# missing arch must fail the build loudly, not ship a silent crash-on-login.
# Explicit .x86_64 (not bare `mimalloc`) is required: given the bare name
# alongside `mimalloc.i686`, dnf5's solver was observed resolving both specs
# to the single i686 package and never queuing x86_64 at all — reproduced
# identically across 4 separate CI builds, so this was a solver behavior,
# not mirror flakiness. Every other explicit multilib pair in this file
# already uses the pkg.x86_64 + pkg.i686 form; mimalloc now matches it.
dnf5 install -y mimalloc.x86_64 mimalloc.i686
check_multilib_pairs mimalloc
