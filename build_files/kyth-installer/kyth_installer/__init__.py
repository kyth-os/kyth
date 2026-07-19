"""kyth-installer — KythOS graphical installer backend."""

import sys
from pathlib import Path

_SHARED = str(Path(__file__).resolve().parent.parent.parent / "kyth_shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)
