"""ProtonDB cache helpers (pure). Batch worker: services.workers.protondb."""
from __future__ import annotations

import json
import os

from .constants import _PROTONDB_CACHE_PATH


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


def __getattr__(name: str):
    if name == "_ProtonDbBatchWorker":
        from ..workers.protondb import ProtonDbBatchWorker
        return ProtonDbBatchWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
