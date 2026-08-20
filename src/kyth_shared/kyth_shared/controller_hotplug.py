"""Controller hotplug — udev monitor debounced 300ms."""

import os
from pathlib import Path


def hotplug_invalidate(cache_key: str = "controllers-detect") -> None:
    """Invalidate probe cache for *cache_key* with 300ms debounce.

    Called by udev monitor on add/remove; invalidates both mem and disk
    ProbeService entries so next Hub navigation re-probes without poll.
    Supports controllers-detect (default), ntfs-drives, hardware-view,
    secureboot-state via templated kyth-hotplug-invalidate@.service.
    """
    try:
        from kyth_shared.system.probe import invalidate_probe_caches

        invalidate_probe_caches([cache_key])
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    # Sentinel for tests without probe plumbing — O_NOFOLLOW so a pre-created
    # symlink at this predictable /tmp path can't redirect the write elsewhere
    # (this runs from a udev rule, typically as root).
    sentinel = Path(f"/tmp/kyth-invalidate-{cache_key}")  # nosec B108 -- opened with O_NOFOLLOW below
    try:
        fd = os.open(sentinel, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, b"1")
        finally:
            os.close(fd)
    except OSError:
        pass


def hotplug_invalidate_all() -> None:
    """Invalidate all hotplug-sensitive keys (block/usb add/remove)."""
    # Both hardware keys: "hardware-view" is the typed in-process memo,
    # "hardware-summary" its disk-backed projection. Dropping only one would
    # leave a stale answer behind whichever survived.
    for key in (
        "controllers-detect", "ntfs-drives",
        "hardware-view", "hardware-summary",
        "secureboot-state",
    ):
        hotplug_invalidate(key)
