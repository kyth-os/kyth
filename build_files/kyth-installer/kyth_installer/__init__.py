"""kyth-installer — KythOS graphical installer backend."""

import sys
from pathlib import Path

_SOURCE_SHARED = Path(__file__).resolve().parent.parent.parent / "kyth_shared"
if _SOURCE_SHARED.is_dir() and str(_SOURCE_SHARED) not in sys.path:
    sys.path.insert(0, str(_SOURCE_SHARED))
