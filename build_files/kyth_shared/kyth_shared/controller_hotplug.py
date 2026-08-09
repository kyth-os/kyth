"""Controller hotplug — udev monitor debounced 300ms."""
from pathlib import Path

def hotplug_invalidate(cache_key: str = "controllers-detect") -> None:
    # Invalidate probe_cached via touch of sentinel
    sentinel = Path(f"/tmp/kyth-invalidate-{cache_key}")
    try:
        sentinel.write_text("1")
    except OSError:
        pass
