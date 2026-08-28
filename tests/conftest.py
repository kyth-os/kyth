"""Pull Qt off the live display before any test module is imported.

Individual modules do `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`,
which is a silent no-op in a desktop session that already exports the
variable — and it only protects the module that remembered to write it.
pytest loads this file first, so forcing it here covers every module,
including ones added later that forget.
"""

import os

_live_desktop = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))
_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Record the verdict before destroying the evidence below: the heavy Hub smoke
# decides whether to run by looking for a session, so stripping these vars
# would otherwise make a live desktop look like a headless CI runner and
# re-enable the very thing that crashes the session.
if _live_desktop and not _ci and os.environ.get("KYTH_FORCE_HEAVY_GUI_SMOKE") != "1":
    os.environ["KYTH_SKIP_HEAVY_GUI_SMOKE"] = "1"

# Nothing under test should reach the session compositor or its GPU, so make
# it unreachable rather than merely unpreferred.
os.environ.pop("WAYLAND_DISPLAY", None)
os.environ.pop("DISPLAY", None)
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
