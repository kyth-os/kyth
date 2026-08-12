"""AppStore cache — wire kyth-probe flatpak-apps to cache."""
from pathlib import Path
import json

CACHE = Path.home() / ".cache" / "kyth-appstream.json"

def warm_appstream_cache() -> str:
    try:
        if CACHE.is_file():
            data = json.loads(CACHE.read_text())
            if data:
                return "cached"
    except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    # fallback to live probe
    return "live"

def appstore_status() -> str:
    if CACHE.is_file():
        return "UNAVAILABLE (cached)"
    return "empty"
