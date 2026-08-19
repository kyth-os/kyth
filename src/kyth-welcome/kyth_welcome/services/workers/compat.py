"""Qt worker for fetching remote compatibility data updates."""
from __future__ import annotations

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_logger = logging.getLogger(__name__)

from ...qt import Signal
from ..gaming import compat_data
from ..gaming.compat_data import (
    _COMPAT_CACHE_PATH,
    _COMPAT_REMOTE_URL,
    _parse_compat_payload,
)
from ..runtime import TrackedThread


class CompatRefreshWorker(TrackedThread):
    """Fetch newer compatibility data from the repo and cache it per-user."""

    refreshed = Signal(str, list)  # (updated, list[CompatGame])
    unchanged = Signal()

    def run(self):
        try:
            req = Request(_COMPAT_REMOTE_URL, headers={"User-Agent": "KythOS-Compat/1.0"})
            with urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
            updated, games = _parse_compat_payload(json.loads(raw))
            if not games or updated <= compat_data._COMPAT_DATA_UPDATED:
                self.unchanged.emit()
                return
            os.makedirs(os.path.dirname(_COMPAT_CACHE_PATH), exist_ok=True)
            with open(_COMPAT_CACHE_PATH, "w", encoding="utf-8") as fh:
                fh.write(raw)
            self.refreshed.emit(updated, games)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError, HTTPError, URLError) as exc:
            _logger.debug("Compat refresh failed: %s", exc, exc_info=True)
            self.unchanged.emit()
