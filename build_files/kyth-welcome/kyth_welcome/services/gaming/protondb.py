"""ProtonDB cache and batch tier fetch worker."""
from __future__ import annotations

import json
import os
import time
from urllib.request import Request, urlopen

from ...qt import Signal
from .constants import _PROTONDB_CACHE_PATH
from ..runtime import TrackedThread


def _load_protondb_cache() -> dict[str, str]:
    try:
        with open(_PROTONDB_CACHE_PATH, encoding="utf-8") as _f:
            data = json.load(_f)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}
 # _load_protondb_cache

def _save_protondb_cache(cache: dict[str, str]) -> None:
    try:
        os.makedirs(os.path.dirname(_PROTONDB_CACHE_PATH), exist_ok=True)
        with open(_PROTONDB_CACHE_PATH, "w", encoding="utf-8") as _f:
            json.dump(cache, _f)
    except OSError:
        pass
 # _save_protondb_cache

class _ProtonDbBatchWorker(TrackedThread):
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
            except Exception:
                result[appid] = "pending"
            time.sleep(0.06)
        self.finished_all.emit(result)
 # _ProtonDbBatchWorker

