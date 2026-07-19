"""Shared on-disk probe cache for expensive read-only system queries.

``kyth-probe`` (user/system oneshot) refreshes the cache; System Hub and other
CLI tools read it before spawning ``bootc`` / ``flatpak`` / ``lspci``.

Cache layout (JSON, atomic replace)::

    {
      "version": 1,
      "generated_at": 1710000000.0,
      "sections": {
        "bootc-status-data": {"ts": 1710000000.0, "data": {...}},
        "flatpak-apps": {"ts": 1710000000.0, "data": ["org.foo.Bar", ...]},
        ...
      }
    }

Paths (first existing / writable wins for writes; readers merge all):

* user runtime: ``$XDG_RUNTIME_DIR/kyth/probe-cache.json``
* user cache:   ``~/.cache/kyth/probe-cache.json``
* system:       ``/var/cache/kyth/probe-cache.json`` (root probe)

No Qt. Safe to import from ``kyth-probe`` and update-watcher.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable

CACHE_VERSION = 1

# How long a disk section remains usable for Hub cold-start (seconds).
# In-process TTLs in process.py stay short for post-action accuracy.
DISK_TTL: dict[str, float] = {
    "bootc-status-data": 90.0,
    "bootc-status-text": 90.0,
    "bootc-branch": 90.0,
    "kernel-flavor": 600.0,
    "flatpak-apps": 180.0,
    "flatpak-updates": 180.0,
    "nvidia-detect": 300.0,
    "controllers-detect": 120.0,
}

# Sections the oneshot collector always refreshes.
COLLECT_SECTIONS: tuple[str, ...] = tuple(DISK_TTL.keys())

# Keys to drop after mutations (flatpak install, bootc upgrade, …).
MUTATION_KEYS_FLATPAK = frozenset({"flatpak-apps", "flatpak-updates"})
MUTATION_KEYS_BOOTC = frozenset({
    "bootc-status-data",
    "bootc-status-text",
    "bootc-branch",
    "kernel-flavor",
})


def user_runtime_cache_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "kyth" / "probe-cache.json"
    return Path(f"/run/user/{os.getuid()}") / "kyth" / "probe-cache.json"


def user_home_cache_path() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "probe-cache.json"
    return Path.home() / ".cache" / "kyth" / "probe-cache.json"


def system_cache_path() -> Path:
    return Path("/var/cache/kyth/probe-cache.json")


def default_write_path(*, system: bool = False) -> Path:
    """Preferred path for the current process to write."""
    if system or os.geteuid() == 0:
        return system_cache_path()
    # Prefer runtime dir (tmpfs, multi-reader, gone on logout) then home cache.
    runtime = user_runtime_cache_path()
    try:
        runtime.parent.mkdir(parents=True, exist_ok=True)
        return runtime
    except OSError:
        return user_home_cache_path()


def cache_read_paths(*, system: bool = False) -> list[Path]:
    """Paths to consult, newest section wins (see read_section)."""
    if system or os.geteuid() == 0:
        return [system_cache_path(), user_runtime_cache_path(), user_home_cache_path()]
    return [user_runtime_cache_path(), user_home_cache_path(), system_cache_path()]


def _empty_doc() -> dict[str, Any]:
    return {"version": CACHE_VERSION, "generated_at": 0.0, "sections": {}}


def load_cache_file(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    sections = data.get("sections")
    if not isinstance(sections, dict):
        return None
    return data


def write_cache_file(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
    # Atomic replace so readers never see a partial file.
    fd, tmp_name = tempfile.mkstemp(prefix=".probe-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_section(
    key: str,
    *,
    max_age: float | None = None,
    paths: Iterable[Path] | None = None,
) -> Any | None:
    """Return section data if any cache file has a fresh entry for *key*."""
    ttl = max_age if max_age is not None else DISK_TTL.get(key)
    if ttl is None:
        return None
    now = time.time()
    best: tuple[float, Any] | None = None
    for path in paths if paths is not None else cache_read_paths():
        doc = load_cache_file(path)
        if doc is None:
            continue
        entry = doc.get("sections", {}).get(key)
        if not isinstance(entry, dict) or "ts" not in entry or "data" not in entry:
            continue
        try:
            ts = float(entry["ts"])
        except (TypeError, ValueError):
            continue
        age = now - ts
        if age < 0 or age > ttl:
            continue
        if best is None or ts > best[0]:
            best = (ts, entry["data"])
    if best is None:
        return None
    return best[1]


def update_sections(
    sections: dict[str, Any],
    *,
    path: Path | None = None,
    system: bool = False,
) -> Path:
    """Merge *sections* into the on-disk cache and return the path written."""
    target = path or default_write_path(system=system)
    doc = load_cache_file(target) or _empty_doc()
    now = time.time()
    store = doc.setdefault("sections", {})
    for key, data in sections.items():
        store[key] = {"ts": now, "data": data}
    doc["version"] = CACHE_VERSION
    doc["generated_at"] = now
    write_cache_file(target, doc)
    return target


def invalidate_disk_sections(keys: Iterable[str] | None = None) -> None:
    """Drop section(s) from all writable caches (call after mutations)."""
    drop = set(keys) if keys is not None else set(DISK_TTL)
    for path in cache_read_paths():
        doc = load_cache_file(path)
        if doc is None:
            continue
        sections = doc.get("sections") or {}
        changed = False
        for key in list(sections):
            if key in drop:
                del sections[key]
                changed = True
        if not changed:
            continue
        try:
            # Only rewrite if we can open for write.
            if path.exists() and not os.access(path, os.W_OK):
                continue
            if not path.exists() and not os.access(path.parent, os.W_OK):
                continue
            doc["generated_at"] = time.time()
            write_cache_file(path, doc)
        except OSError:
            continue


def _count_flatpak_updates() -> int | None:
    """Pending flatpak app updates (system + user). None if flatpak missing."""
    from .process import _run_command

    total = 0
    saw_ok = False
    for scope in ("--system", "--user"):
        result = _run_command(
            ["flatpak", "remote-ls", "--updates", scope, "--columns=application"],
            timeout=30,
        )
        if result is None:
            continue
        if result.returncode != 0:
            continue
        saw_ok = True
        total += len([ln for ln in result.stdout.splitlines() if ln.strip()])
    return total if saw_ok else None


def collect_snapshot() -> dict[str, Any]:
    """Run live probes and return a sections map (no disk I/O)."""
    from .bootc import (
        _branch_from_ref,
        _current_kernel_flavor,
        _fetch_bootc_status_data,
        _fetch_bootc_status_text,
        image_reference_from_status,
    )
    from .process import _run_command

    sections: dict[str, Any] = {}

    data = _fetch_bootc_status_data()
    sections["bootc-status-data"] = data
    text = _fetch_bootc_status_text()
    sections["bootc-status-text"] = text

    ref = image_reference_from_status(data or {}, status_text=text)
    sections["bootc-branch"] = _branch_from_ref(ref)
    try:
        sections["kernel-flavor"] = _current_kernel_flavor()
    except Exception:
        sections["kernel-flavor"] = "fedora"

    result = _run_command(["flatpak", "list", "--app", "--columns=application"], timeout=15)
    if result is not None and result.returncode == 0:
        apps = sorted({ln.strip() for ln in result.stdout.splitlines() if ln.strip()})
        sections["flatpak-apps"] = apps
    else:
        sections["flatpak-apps"] = None

    sections["flatpak-updates"] = _count_flatpak_updates()

    try:
        r = _run_command(["lspci"], timeout=5)
        sections["nvidia-detect"] = bool(r and "nvidia" in (r.stdout or "").lower())
    except Exception:
        sections["nvidia-detect"] = False

    try:
        # Live detect — avoid nested disk cache while we are refreshing it.
        from .hardware import drives as drives_mod
        # Call the inner fetch by going through _probe_cached key with empty mem
        # would write-through mid-collect; invoke detect via private path:
        sections["controllers-detect"] = drives_mod._detect_controllers()
    except Exception:
        sections["controllers-detect"] = None

    return sections


def invalidate_after_flatpak_change() -> None:
    """Drop flatpak-related sections after install/uninstall."""
    invalidate_disk_sections(MUTATION_KEYS_FLATPAK)


def invalidate_after_bootc_change() -> None:
    """Drop bootc/branch sections after upgrade/switch/rollback."""
    invalidate_disk_sections(MUTATION_KEYS_BOOTC)


def refresh_cache(*, system: bool = False, path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Collect live probes, write cache, return (path, sections)."""
    sections = collect_snapshot()
    written = update_sections(sections, path=path, system=system)
    return written, sections


def disk_probe(
    key: str,
    ttl: float,
    fetch: Callable[[], Any],
    *,
    use_disk: bool = True,
) -> Any:
    """Memory-less helper: prefer disk, else *fetch*, then write-through disk.

    Used by process._probe_cached after an in-process miss.
    """
    if use_disk and key in DISK_TTL:
        hit = read_section(key, max_age=max(ttl, DISK_TTL[key]))
        if hit is not None:
            # flatpak-apps None means "listing failed" — treat as miss
            if not (key == "flatpak-apps" and hit is None):
                return hit
    value = fetch()
    if use_disk and key in DISK_TTL:
        try:
            # Don't persist failed flatpak listing as empty list confusion:
            # software treats None specially.
            update_sections({key: value})
        except OSError:
            pass
    return value
