#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── irqbalance Tuning ────────────────────────────────────────────────────────
# Owned by systemd/05-irqbalance-tuning.sh (sorts later and must win).
# --deepestcache=2 lives there alongside ONESHOT so this file cannot
# clobber the oneshot setting and leave Type=simple exiting as a failure.
:
