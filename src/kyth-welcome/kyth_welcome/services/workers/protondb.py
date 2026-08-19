"""Qt worker for batch ProtonDB tier fetches."""
from __future__ import annotations

import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_logger = logging.getLogger(__name__)

from ...qt import Signal
from ..runtime import TrackedThread


class ProtonDbBatchWorker(TrackedThread):
    """Fetches ProtonDB tiers for a list of Steam appids, skipping already-cached ones."""
    tier_fetched = Signal(str, str)   # (appid, tier)
    finished_all = Signal(dict)       # full {appid: tier} map

    def __init__(self, appids: list[str], existing: dict[str, str]):
        super().__init__()
        self._appids = appids
        self._existing = dict(existing)

    def run(self):
        result = dict(self._existing)
        for appid in self._appids:
            if not appid or appid in result:
                continue
            try:
                req = Request(
                    f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json",
                    headers={"User-Agent": "KythOS-GameCheck/1.0"},
                )
                with urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    tier = data.get("tier") or "pending"
                    result[appid] = tier
                    self.tier_fetched.emit(appid, tier)
            except (OSError, ValueError, KeyError, json.JSONDecodeError, HTTPError, URLError) as exc:
                _logger.debug("ProtonDB fetch failed for %s: %s", appid, exc, exc_info=True)
                result[appid] = "pending"
            time.sleep(0.06)
        self.finished_all.emit(result)


# Compat alias used by gaming package re-exports
_ProtonDbBatchWorker = ProtonDbBatchWorker
