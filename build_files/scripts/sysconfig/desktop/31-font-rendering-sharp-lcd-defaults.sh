#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Font rendering — sharp LCD defaults ──────────────────────────────────────
# Linux freetype defaults vary by distro; Fedora's are conservative. hintfull
# snaps stems to pixel boundaries for maximum on-screen crispness (matches the
# sharpness of Windows ClearType on typical 1080p panels). autohint=false keeps
# FreeType using the font's own hinting tables rather than its generic engine.
# Users who prefer a different look can drop a file in ~/.config/fontconfig/.
mkdir -p /etc/fonts/conf.d
write_config /etc/fonts/local.conf <<'FONTCONFIGEOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <match target="font">
    <edit name="antialias"  mode="assign"><bool>true</bool></edit>
    <edit name="hinting"    mode="assign"><bool>true</bool></edit>
    <edit name="autohint"   mode="assign"><bool>false</bool></edit>
    <edit name="hintstyle"  mode="assign"><const>hintfull</const></edit>
    <edit name="rgba"       mode="assign"><const>rgb</const></edit>
    <edit name="lcdfilter"  mode="assign"><const>lcddefault</const></edit>
  </match>
</fontconfig>
FONTCONFIGEOF
