"""Central banner/status helpers for privileged actions (arch #2).

All Hub pages that run a privileged `Worker`/`popen` should surface
failures via the same helper so users see actionable text + log hint,
not a generic "failed".
"""
from __future__ import annotations

from typing import Any

try:
    from ..core_base import restyle as _restyle
except Exception:  # pragma: no cover — bare import for tests without Qt
    def _restyle(widget: Any) -> None:  # type: ignore[no-redef]
        try:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
            pass


def set_banner(label: Any, text: str, *, kind: str = "err") -> None:
    """Show *text* on *label* with style *kind* (err|ok|info) and restyle."""
    style = {"err": "status-err", "ok": "status-ok", "info": "subheading"}.get(kind, kind)
    try:
        label.setText(text)
        label.setObjectName(style)
        label.show()
        _restyle(label)
    except Exception:
        pass


def clear_banner(label: Any) -> None:
    try:
        label.setText("")
        label.hide()
        _restyle(label)
    except Exception:
        pass
