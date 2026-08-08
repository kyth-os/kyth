SPACING_XS = 4
SPACING_TINY = SPACING_XS  # alias for compat — was duplicate 4
SPACING_SMALL = 8
SPACING_MEDIUM = 12
SPACING_LARGE = 16
SPACING_XLARGE = 24
SPACING_2XL = 32

RADIUS_SM = 6
RADIUS_CARD = 12
RADIUS_PILL = 999
RADIUS_BUTTON = 8
RADIUS_HERO = 16
# Single accent — canonical is KYTH_BLUE (#5b8cff); ACCENT_BLUE is legacy alias
ACCENT_BLUE = "#5b8cff"
# Canonical status trio (Phase 3): previously theme_hub_overlay.py carried its
# own separate ok/warn/err values that didn't match these, and even
# disagreed with itself between card-accent-err (#e05f67) and status-err
# (#9f464f/#ffb0b6) — one value each, used everywhere, done/warn/err chips
# included, so the wizard (Phase 1) and Hub finally render the same colors.
STATUS_OK = "#10b981"
STATUS_WARN = "#f59e0b"
STATUS_ERROR = "#f7768e"
TEXT_MUTED = "#8cadcf"


def accent_line_style(color: str = ACCENT_BLUE) -> str:
    return f"background: {color}; border: none;"


# ── Spacing / motion tokens (Phase 1 polish) ─────────────────────────────────
MOTION_FAST = 120  # ms
MOTION_NORMAL = 200

# ── Typography (Windows Settings match: 12/13/15/22, not Inter-everywhere) ──
FONT_SIZE_CAPTION = 11
FONT_SIZE_COPY = 12
FONT_SIZE_SUBTITLE = 13
FONT_SIZE_TITLE = 15
FONT_SIZE_HERO = 22

# ── Kyth Theme tokens (control center shell) ─────────────────────────────────
# SteamOS + Windows Settings inspired: layered depth, not flat black.
# Ground is the window canvas; surface is card/topbar; raised is hover/input.
# Hairline is now a touch lighter for visible panel separation — the old
# #262b3d on #12141f was nearly invisible, collapsing the "black and blah"
# look. Added overlay + highlight tokens for Steam-style hover elevation
# without resorting to glassmorphism or purple gradients.
KYTH_GROUND = "#0c0f14"
KYTH_SURFACE = "#151a24"
KYTH_SURFACE_RAISED = "#1d2436"
KYTH_SURFACE_OVERLAY = "#26304a"
KYTH_HAIRLINE = "#2a344c"
KYTH_HAIRLINE_LIGHT = "#36435f"
KYTH_HIGHLIGHT = "rgba(255,255,255,0.06)"
KYTH_BLUE = "#5b8cff"
KYTH_BLUE_DIM = "#3d5eb8"
KYTH_BLUE_LIGHT = "#8fb8ff"
KYTH_BLUE_GLOW = "rgba(91, 140, 255, 0.18)"
# Primary button — muted slate-blue, not saturated #5b8cff fill. Keeps the
# overall theme's cool-slate palette: dark overlay with a desaturated blue
# border so primary is legible without the neon pop that read as AI-slop.
KYTH_PRIMARY_BG = "#263a54"
KYTH_PRIMARY_BORDER = "#3a5378"
KYTH_PRIMARY_HOVER_BG = "#2e4566"
KYTH_PRIMARY_HOVER_BORDER = "#4a6fa5"
KYTH_PRIMARY_PRESSED_BG = "#1e2f4a"
KYTH_VIOLET = "#bb9af7"
KYTH_TEXT = "#eef2fb"
KYTH_TEXT_MUTED = "#8ea0c0"
KYTH_TEXT_FAINT = "#5b6986"
KYTH_DANGER = "#c42b1c"
KYTH_DANGER_LIGHT = "#d13438"
KYTH_RADIUS = 12
KYTH_RADIUS_SM = 8
KYTH_RADIUS_XL = 16
