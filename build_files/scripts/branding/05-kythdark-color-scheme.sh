# shellcheck shell=bash
# ── KythDark color scheme ─────────────────────────────────────────────────────
# Tokyo Night-derived palette: #0c0e16 dark slate base, #4f8cff Kyth blue accent.
# All nine Color:* sections share the same palette so colors are consistent
# across button, view, window, selection, tooltip, and header contexts.
mkdir -p /usr/share/color-schemes
cat >/usr/share/color-schemes/KythDark.colors <<'KYTHCOLORSEOF'
[ColorEffects:Disabled]
Color=56,56,56
ColorAmount=0
ColorEffect=0
ContrastAmount=0.65
ContrastEffect=1
IntensityAmount=0.1
IntensityEffect=2

[ColorEffects:Inactive]
ChangeSelectionColor=true
Color=112,111,110
ColorAmount=0.025
ColorEffect=2
ContrastAmount=0.1
ContrastEffect=2
Enable=false
IntensityAmount=0
IntensityEffect=0

[Colors:Button]
BackgroundAlternate=22,24,36
BackgroundNormal=18,20,31
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Complementary]
BackgroundAlternate=22,24,36
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Header]
BackgroundAlternate=18,20,31
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Selection]
BackgroundAlternate=79,140,255
BackgroundNormal=79,140,255
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=255,255,255
ForegroundInactive=204,204,204
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=255,255,255
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Tooltip]
BackgroundAlternate=18,20,31
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:View]
BackgroundAlternate=18,20,31
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Window]
BackgroundAlternate=18,20,31
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[General]
ColorScheme=KythDark
Name=Kyth Dark
shadeSortColumn=true

[KDE]
contrast=4
KYTHCOLORSEOF
