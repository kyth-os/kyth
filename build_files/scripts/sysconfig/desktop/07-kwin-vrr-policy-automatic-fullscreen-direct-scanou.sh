#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── KWin VRR policy — Automatic (fullscreen / direct scanout) ────────────────
# KDE Plasma ships with VRR disabled (VrrPolicy=0 / Never). Gaming users expect
# their 144 Hz / VRR monitor to actually use variable refresh in games.
# "Automatic" (1) enables VRR only when KWin hands a surface directly to the
# display (fullscreen / direct scanout) — i.e., during games — and reverts to
# fixed rate on the desktop. "Always" (2) would enable VRR even on composited
# desktop, which causes flicker artifacts on some panels and wastes panel power.
#
# Key-level write: set only [Wayland] VrrPolicy in /etc/xdg/kwinrc, preserving
# every other section/key. The previous full-file overwrite clobbered
# decoration, blur and plugin defaults owned by other fragments and by
# user-polish, and user-polish could never converge on a stable file.
mkdir -p /etc/xdg
touch /etc/xdg/kwinrc
KWIN_TMP="$(mktemp)"
awk '
    /^\[.*\]/ {
        if (in_wayland && !wrote) { print "VrrPolicy=1"; wrote = 1 }
        in_wayland = ($0 == "[Wayland]")
        print
        next
    }
    in_wayland && /^[#[:space:]]*VrrPolicy[[:space:]]*=/ {
        if (!wrote) { print "VrrPolicy=1"; wrote = 1 }
        next
    }
    { print }
    END { if (in_wayland && !wrote) print "VrrPolicy=1" }
' /etc/xdg/kwinrc >"${KWIN_TMP}"
if ! grep -q '^\[Wayland\]' "${KWIN_TMP}"; then
    printf '\n[Wayland]\nVrrPolicy=1\n' >>"${KWIN_TMP}"
fi
cat "${KWIN_TMP}" >/etc/xdg/kwinrc
rm -f "${KWIN_TMP}"
