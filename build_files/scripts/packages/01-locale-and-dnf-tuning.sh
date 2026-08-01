#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Locale filtering ──────────────────────────────────────────────────────────
# Strip non-English locale data from every subsequent RPM install.
# Saves 100–300 MB across the full package set with no functional loss
# on an English workstation.
echo '%_install_langs en_US' >>/etc/rpm/macros

# ── DNF parallelism ───────────────────────────────────────────────────────────
# Raise parallel download slots from the default 3 to 10 — same value used by
# UBlue, Bazzite, and recommended in Fedora documentation.
# Prevent any package dependency from pulling in a new kernel (e.g. akmod deps
# installing kernel-modules without kernel-core, which leaves a modules dir
# with no vmlinuz and breaks the bootc kernel check downstream). The bare
# `kernel` meta package is pinned too: its subpackages are excluded, so dnf5
# upgrade would otherwise report it as a broken-dependency Problem every day
# (the kernel version is fixed from the base image by design).
# CountMe adds an anonymous weekly age bucket to one repository metadata request.
# This lets Fedora-style mirror logs estimate active systems without user
# accounts, hardware IDs, or per-machine identifiers. Fedora's aggregate is
# repository-scoped and cannot be used as a KythOS-specific install count.
cat >>/etc/dnf/dnf.conf <<'DNFCONFEOF'
max_parallel_downloads=10
excludepkgs=kernel,kernel-core*,kernel-modules*,kernel-modules-core*,kernel-modules-extra*,kernel-devel*,kernel-debug*
countme=True
nodocs=True
DNFCONFEOF

# KythOS is its own distribution identity. Replace the inherited Fedora artwork
# package with Fedora's generic drop-in before installing desktop components so
# upstream boot watermarks and launcher icons cannot leak into the final image.
dnf5 swap -y --allowerasing fedora-logos generic-logos
