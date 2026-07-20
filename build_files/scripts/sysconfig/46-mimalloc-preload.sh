#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── mimalloc Preload ─────────────────────────────────────────────────────────
# Preloads mimalloc for desktop environment applications and games.
# Applying this at the environment level prevents it from running for early boot/system services.
#
# Uses the versioned soname (libmimalloc.so.2), not the bare libmimalloc.so:
# Fedora's mimalloc runtime package only ships libmimalloc.so.{2,2.2} — the
# unversioned symlink is a linker-time convenience that lives in mimalloc-devel,
# which isn't installed on the desktop image. LD_PRELOAD=libmimalloc.so
# therefore failed to resolve for every process on every login ("ld.so: ...
# cannot be preloaded ... ignored") — non-fatal per-process, but confirmed on
# a live system running the arch-split fix, so that fix alone doesn't cover
# this. Bump the ".2" here if a future mimalloc bump changes the soname.
#
# Uses the absolute path, not just the versioned soname: glibc's dynamic
# linker only resolves a bare LD_PRELOAD soname via ld.so.cache for normal
# unprivileged processes. Under secure-execution mode — sudo, or rootless
# podman/docker's setuid newuidmap/newgidmap helpers — it refuses to resolve
# bare names at all and prints the same "cannot be preloaded (cannot open
# shared object file)" warning on every such invocation. An absolute path in
# a trusted directory (/usr/lib64) is honored in both modes.
mkdir -p /etc/environment.d
cat >/etc/environment.d/20-mimalloc.conf <<'EOF'
LD_PRELOAD=/usr/lib64/libmimalloc.so.2
EOF
