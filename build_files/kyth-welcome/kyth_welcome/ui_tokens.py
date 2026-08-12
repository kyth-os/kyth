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
# Canonical status trio (Phase 3): previously theme_hub_overlay.py carried its
# own separate ok/warn/err values that didn't match these, and even
# disagreed with itself between card-accent-err (#e05f67) and status-err
# (#9f464f/#ffb0b6) — one value each, used everywhere, done/warn/err chips
# included, so the wizard (Phase 1) and Hub finally render the same colors.
STATUS_OK = "#10b981"
STATUS_WARN = "#f59e0b"
STATUS_ERROR = "#f7768e"
TEXT_MUTED = "#8cadcf"

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
KYTH_GROUND = "#090b0e"
KYTH_SURFACE = "#121620"
KYTH_SURFACE_RAISED = "#1a202c"
KYTH_SURFACE_OVERLAY = "#242c3d"
KYTH_HAIRLINE = "rgba(255, 255, 255, 0.08)"
KYTH_HAIRLINE_LIGHT = "rgba(255, 255, 255, 0.16)"
KYTH_HIGHLIGHT = "rgba(255, 255, 255, 0.08)"
KYTH_BLUE = "#38bdf8"
KYTH_BLUE_DIM = "#0284c7"
KYTH_BLUE_LIGHT = "#7dd3fc"
# Qt's QSS rgba() takes an integer 0-255 alpha, not a 0-1 float — this was
# previously "rgba(56, 189, 248, 0.22)", which Qt's parser rejects, so the
# glow it was meant to add was silently dropped wherever it was used.
KYTH_BLUE_GLOW = "rgba(56, 189, 248, 56)"
# Low-alpha KYTH_BLUE tint for pill/badge fills — same hue as KYTH_BLUE so
# text/border/background on a single chip never mix two different blues.
KYTH_BLUE_TINT_BG = "rgba(56, 189, 248, 31)"
KYTH_BLUE_TINT_BORDER = "rgba(56, 189, 248, 92)"
KYTH_PRIMARY_BG = "#1e293b"
KYTH_PRIMARY_BORDER = "#38bdf8"
KYTH_PRIMARY_HOVER_BG = "#0284c7"
KYTH_PRIMARY_HOVER_BORDER = "#7dd3fc"
KYTH_PRIMARY_PRESSED_BG = "#0369a1"
KYTH_VIOLET = "#a855f7"
KYTH_TEXT = "#f8fafc"
KYTH_TEXT_MUTED = "#94a3b8"
KYTH_TEXT_FAINT = "#64748b"
KYTH_DANGER = "#ef4444"
KYTH_DANGER_LIGHT = "#f87171"
KYTH_RADIUS = 12
KYTH_RADIUS_SM = 8
KYTH_RADIUS_XL = 16
