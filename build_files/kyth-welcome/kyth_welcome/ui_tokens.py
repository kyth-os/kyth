SPACING_TINY = 4
SPACING_SMALL = 8
SPACING_MEDIUM = 12
SPACING_LARGE = 16
SPACING_XLARGE = 24

RADIUS_CARD = 8
ACCENT_BLUE = "#4f8cff"
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


# ── Kyth Theme tokens (wizard shell) ───────────────────────────────────────────
# Grounded in the palette already shipping in theme_hub_overlay.py / theme_genz.py
# and the brand SVGs (build_files/branding/*.svg) — refined into one named set
# for the first-boot wizard rather than the ad hoc hex literals it used to carry.
# STATUS_OK/WARN/ERROR above are intentionally left alone: they're load-bearing
# for existing Hub pages and are a separate, later migration (see plan Phase 3).
KYTH_GROUND = "#0a0c13"
KYTH_SURFACE = "#12141f"
KYTH_SURFACE_RAISED = "#181b29"
KYTH_HAIRLINE = "#262b3d"
KYTH_BLUE = "#5b8cff"
KYTH_BLUE_DIM = "#3a5bb0"
KYTH_BLUE_LIGHT = "#8fb8ff"
KYTH_VIOLET = "#bb9af7"
KYTH_TEXT = "#f2f4fb"
KYTH_TEXT_MUTED = "#93a1bd"
KYTH_TEXT_FAINT = "#5b6580"
KYTH_DANGER = "#c42b1c"
KYTH_DANGER_LIGHT = "#d13438"
KYTH_RADIUS = 10
KYTH_RADIUS_SM = 6
