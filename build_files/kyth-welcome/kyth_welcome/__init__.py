"""kyth-welcome — KythOS System Hub and first-run wizard.

Shows once on first login (via /etc/skel autostart) and is always
accessible from the application menu as "KythOS System Hub".

Package layout:
    qt.py          Qt binding shim (PySide6 preferred, PyQt6 fallback)
    theme.py       application-wide QSS stylesheet
    core_base.py   re-exports + session/UI helpers
    actions.py     Qt UI actions (flatpak button install, …)
    services/      domain logic (process, bootc, registry, runtime, …)
    widgets.py     shared UI building blocks (Page base, cards, tiles)
    page_*.py      one module per hub page
    windows.py     MainWindow (System Hub shell)
    wizard/        first-run WizardWindow + step mixins
    app.py         entry point
"""

import os
import sys
from pathlib import Path

_shared = None
_here = Path(__file__).resolve().parent
# Source checkout: build_files/kyth-welcome/kyth_welcome/__init__.py
#   → kyth_shared at parent.parent.parent / "kyth_shared"
_p = _here.parent.parent.parent / "kyth_shared"
if _p.is_dir() and str(_p) not in sys.path:
    _shared = str(_p)
# Container image: kyth_shared is installed at /usr/kyth_shared
if not _shared:
    _p = Path("/usr/kyth_shared")
    if _p.is_dir() and str(_p) not in sys.path:
        _shared = str(_p)
# Source checkout (alternate layout): kyth_shared adjacent to the shim
if not _shared:
    _p = _here.parent.parent / "kyth_shared"
    if _p.is_dir() and str(_p) not in sys.path:
        _shared = str(_p)
# Fallback: sibling of the shim's parent directory
if not _shared:
    _p = _here.parent / "kyth_shared"
    if _p.is_dir() and str(_p) not in sys.path:
        _shared = str(_p)
if _shared:
    sys.path.insert(0, _shared)
