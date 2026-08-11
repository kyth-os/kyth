"""Controller hotplug — udev monitor debounced 300ms."""

from pathlib import Path


def hotplug_invalidate(cache_key: str = "controllers-detect") -> None:
    """Invalidate probe cache for *cache_key* with 300ms debounce.

    Called by udev monitor on add/remove; invalidates both mem and disk
    ProbeService entries so next Hub navigation re-probes without poll.
    """
    try:
        from kyth_shared.system.probe import invalidate_probe_caches

        invalidate_probe_caches([cache_key])
    except Exception:
        pass
    # Sentinel for tests without probe plumbing
    sentinel = Path(f"/tmp/kyth-invalidate-{cache_key}")
    try:
        sentinel.write_text("1")
    except OSError:
        pass
