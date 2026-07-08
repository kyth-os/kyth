SPACING_TINY = 4
SPACING_SMALL = 8
SPACING_MEDIUM = 12
SPACING_LARGE = 16
SPACING_XLARGE = 24

RADIUS_CARD = 8
ACCENT_BLUE = "#4f8cff"
STATUS_OK = "#4caf50"
STATUS_WARN = "#d4a843"
STATUS_ERROR = "#ef5350"
TEXT_MUTED = "#8cadcf"


def accent_line_style(color: str = ACCENT_BLUE) -> str:
    return f"background: {color}; border: none;"
