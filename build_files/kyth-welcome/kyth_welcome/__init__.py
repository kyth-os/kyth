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

import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
# Source checkout: build_files/kyth-welcome/kyth_welcome/__init__.py
#   → kyth_shared beside kyth-welcome under build_files.
_p = _here.parent.parent / "kyth_shared"
if _p.is_dir() and str(_p) not in sys.path:
    sys.path.insert(0, str(_p))
