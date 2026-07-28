# shellcheck shell=bash
# ── Kyth Dark Plasma shell theme (frosted glass panel) ────────────────────────
# Minimal theme that overrides only the panel background SVG; all other assets
# fall back to breeze-dark via X-Plasma-Fallback-Theme.  The panel-background
# SVG uses fill-opacity=0.82 so KWin's blur effect shines through, producing
# a frosted glass look. A thin teal top-edge accent line ties the panel to
# the KythDark color accent and System Hub visual language.
write_config /usr/share/plasma/desktoptheme/kyth-dark/metadata.json <<'KYTHMETAEOF'
{
    "KPlugin": {
        "Authors": [{"Name": "KythOS"}],
        "Description": "KythOS dark plasma theme with frosted glass panel",
        "Id": "kyth-dark",
        "License": "Apache-2.0",
        "Name": "Kyth Dark",
        "Version": "1.0"
    },
    "X-Plasma-API": "5.0",
    "X-Plasma-Fallback-Theme": "breeze-dark"
}
KYTHMETAEOF

# panel-background.svg — 9-patch panel background.
# Coordinates: 100×100 canvas, 4px borders, semi-transparent dark slate fill.
# The hint-* elements encode margin widths for the Plasma SVG renderer;
# they are invisible (fill:none) and exist only to carry the numeric hint.
# A 1px teal accent line runs along the top edge of the panel.
write_config /usr/share/plasma/desktoptheme/kyth-dark/widgets/panel-background.svg <<'KYTHPANELSVGEOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <!-- Margin hints (invisible, encode border widths for the 9-patch renderer) -->
  <rect id="hint-left-margin"   x="0"  y="49" width="4"  height="1" fill="none"/>
  <rect id="hint-right-margin"  x="96" y="49" width="4"  height="1" fill="none"/>
  <rect id="hint-top-margin"    x="49" y="0"  width="1"  height="5" fill="none"/>
  <rect id="hint-bottom-margin" x="49" y="96" width="1"  height="4" fill="none"/>
  <!-- Teal top accent line (1px, spans the full width across the top border) -->
  <rect id="top"         x="4"  y="0"  width="92" height="1"  fill="#4f8cff" fill-opacity="0.70"/>
  <!-- 9-patch fill regions: semi-transparent dark slate -->
  <rect id="topleft"     x="0"  y="0"  width="4"  height="5"  fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="topright"    x="96" y="0"  width="4"  height="5"  fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="left"        x="0"  y="5"  width="4"  height="91" fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="center"      x="4"  y="1"  width="92" height="95" fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="right"       x="96" y="5"  width="4"  height="91" fill="#0c0e16" fill-opacity="0.9"/>
<rect id="bottomleft"  x="0"  y="96" width="4"  height="4"  fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="bottom"      x="4"  y="96" width="92" height="4"  fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="bottomright" x="96" y="96" width="4"  height="4"  fill="#0c0e16" fill-opacity="0.9"/>
</svg>
KYTHPANELSVGEOF
