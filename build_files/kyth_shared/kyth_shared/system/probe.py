"""Shared on-disk probe cache for expensive read-only system queries.

``kyth-probe`` (user/system oneshot) refreshes the cache; System Hub and other
CLI tools read it before spawning ``bootc`` / ``flatpak`` / ``lspci``.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")
_logger = logging.getLogger(__name__)

CACHE_VERSION = 2


class ProbeStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class ProbeResult:
    key: str
    status: ProbeStatus
    data: Any = None
    error: str = ""


@dataclass(frozen=True)
class ProbeCollector:
    name: str
    keys: tuple[str, ...]
    collect: Callable[[], dict[str, Any]]

DISK_TTL: dict[str, float] = {
    "bootc-status-data": 90.0,
    "bootc-status-text": 90.0,
    "bootc-branch": 90.0,
    "kernel-flavor": 600.0,
    "flatpak-apps": 180.0,
    "flatpak-updates": 180.0,
    "nvidia-detect": 300.0,
    "controllers-detect": 120.0,
    "hardware-probes": 30.0,
    "ntfs-drives": 30.0,
    "secureboot-state": 300.0,
    "hardware-view": 30.0,
}

COLLECT_SECTIONS: tuple[str, ...] = tuple(DISK_TTL.keys())

# Unified mem+disk cache keys — single source of truth for the hybrid cache.
DISK_BACKED_KEYS = frozenset(DISK_TTL.keys())

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
    if system or os.geteuid() == 0:
        return system_cache_path()
    runtime = user_runtime_cache_path()
    try:
        runtime.parent.mkdir(parents=True, exist_ok=True)
        return runtime
    except OSError:
        return user_home_cache_path()


def cache_read_paths(*, system: bool = False) -> list[Path]:
    if system or os.geteuid() == 0:
        return [system_cache_path(), user_runtime_cache_path(), user_home_cache_path()]
    return [user_runtime_cache_path(), user_home_cache_path(), system_cache_path()]


def _empty_doc() -> dict[str, Any]:
    return {"version": CACHE_VERSION, "generated_at": 0.0, "sections": {}}


_FILE_CACHE: dict[Path, tuple[float, dict[str, Any]]] = {}
_FILE_CACHE_LOCK = threading.Lock()


def load_cache_file(path: Path) -> dict[str, Any] | None:
    try:
        st = path.stat()
        mtime = st.st_mtime
    except OSError:
        return None
    with _FILE_CACHE_LOCK:
        cached = _FILE_CACHE.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
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
    with _FILE_CACHE_LOCK:
        # LRU cap: keep at most 16 file entries
        if len(_FILE_CACHE) >= 16 and path not in _FILE_CACHE:
            oldest = min(_FILE_CACHE, key=lambda p: _FILE_CACHE[p][0])
            _FILE_CACHE.pop(oldest, None)
        _FILE_CACHE[path] = (mtime, data)
    return data


def write_cache_file(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(prefix=".probe-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
        with _FILE_CACHE_LOCK:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = time.time()
            if len(_FILE_CACHE) >= 16 and path not in _FILE_CACHE:
                oldest = min(_FILE_CACHE, key=lambda p: _FILE_CACHE[p][0])
                _FILE_CACHE.pop(oldest, None)
            _FILE_CACHE[path] = (mtime, doc)
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
    # Invalidate file-level mtime cache alongside disk
    with _FILE_CACHE_LOCK:
        if keys is None:
            _FILE_CACHE.clear()
        else:
            # Drop any cached file that may contain dropped keys — conservative
            _FILE_CACHE.clear()
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
            if path.exists() and not os.access(path, os.W_OK):
                continue
            if not path.exists() and not os.access(path.parent, os.W_OK):
                continue
            doc["generated_at"] = time.time()
            write_cache_file(path, doc)
        except OSError:
            continue


def _count_flatpak_updates() -> int | None:
    from kyth_shared.system.process import run_command

    total = 0
    saw_ok = False
    for scope in ("--system", "--user"):
        result = run_command(
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


def _collect_bootc() -> dict[str, Any]:
    from kyth_shared.system.bootc import (
        branch_from_ref,
        current_kernel_flavor,
        fetch_bootc_status_data,
        fetch_bootc_status_text,
        image_reference_from_status,
    )
    data = fetch_bootc_status_data()
    text = fetch_bootc_status_text()
    ref = image_reference_from_status(data or {}, status_text=text)
    try:
        kernel = current_kernel_flavor()
    except Exception:
        kernel = "fedora"
    return {
        "bootc-status-data": data,
        "bootc-status-text": text,
        "bootc-branch": branch_from_ref(ref),
        "kernel-flavor": kernel,
    }


def _collect_flatpak_apps() -> dict[str, Any]:
    from kyth_shared.system.process import run_command

    result = run_command(["flatpak", "list", "--app", "--columns=application"], timeout=15)
    if result is not None and result.returncode == 0:
        apps = sorted({ln.strip() for ln in result.stdout.splitlines() if ln.strip()})
        return {"flatpak-apps": apps}
    return {"flatpak-apps": None}


def _collect_flatpak_updates() -> dict[str, Any]:
    return {"flatpak-updates": _count_flatpak_updates()}


def _collect_nvidia() -> dict[str, Any]:
    from kyth_shared.system.process import run_command

    try:
        result = run_command(["lspci"], timeout=5)
        value = bool(result and "nvidia" in (result.stdout or "").lower())
    except Exception:
        value = False
    return {"nvidia-detect": value}


def _collect_controllers() -> dict[str, Any]:
    from kyth_shared.system.controllers import detect_controllers

    return {"controllers-detect": detect_controllers()}


def _collect_display() -> dict[str, Any]:
    try:
        from kyth_shared.hardware_policy import evaluate_system

        ev = evaluate_system()
        return {"display-detect": {"capabilities": ev.capabilities[:8], "profiles": [p.id for p in ev.profiles[:3]]}}
    except Exception:
        return {"display-detect": None}


def _collect_hardware_view() -> dict[str, Any]:
    from kyth_shared.system.hardware_view import get_hardware_view

    try:
        view = get_hardware_view()
        return {"hardware-view": view}
    except Exception:
        return {"hardware-view": None}


def default_collectors() -> tuple[ProbeCollector, ...]:
    # Slice 2: async pool already uses ThreadPoolExecutor in collect_probe_results();
    # DISK_TTL below gates disk re-read so repeated Hub nav doesn't re-spawn lspci.
    return (
        ProbeCollector("bootc", ("bootc-status-data", "bootc-status-text", "bootc-branch", "kernel-flavor"), _collect_bootc),
        ProbeCollector("flatpak-apps", ("flatpak-apps",), _collect_flatpak_apps),
        ProbeCollector("flatpak-updates", ("flatpak-updates",), _collect_flatpak_updates),
        ProbeCollector("nvidia", ("nvidia-detect",), _collect_nvidia),
        ProbeCollector("controllers", ("controllers-detect",), _collect_controllers),
        ProbeCollector("display", ("display-detect",), _collect_display),
        ProbeCollector("hardware-view", ("hardware-view",), _collect_hardware_view),
    )


def _run_collector(collector: ProbeCollector) -> dict[str, ProbeResult]:
    try:
        values = collector.collect()
    except Exception as exc:
        return {
            key: ProbeResult(key, ProbeStatus.FAILED, error=str(exc))
            for key in collector.keys
        }
    return {
        key: ProbeResult(
            key,
            ProbeStatus.AVAILABLE if values.get(key) is not None else ProbeStatus.UNAVAILABLE,
            data=values.get(key),
        )
        for key in collector.keys
    }


def collect_probe_results(
    collectors: Iterable[ProbeCollector] | None = None,
) -> dict[str, ProbeResult]:
    """Run independent probe groups concurrently and retain failure state."""
    selected = tuple(collectors or default_collectors())
    results: dict[str, ProbeResult] = {}
    # Cap workers to avoid oversubscription on tiny systems; selected is at most 7
    workers = min(len(selected), 8) if selected else 1
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="kyth-probe") as pool:
        for group in pool.map(_run_collector, selected):
            results.update(group)
    return results


def collect_snapshot() -> dict[str, Any]:
    """Compatibility snapshot containing values while typed results retain errors."""
    return {key: result.data for key, result in collect_probe_results().items()}


_FLATPAK_INVALIDATE_CBS: list[Callable[[], None]] = []  # S14: welcome registers cache_clear


def register_flatpak_invalidate(cb: Callable[[], None]) -> None:
    _FLATPAK_INVALIDATE_CBS.append(cb)


def invalidate_after_flatpak_change() -> None:
    invalidate_disk_sections(MUTATION_KEYS_FLATPAK)
    for cb in list(_FLATPAK_INVALIDATE_CBS):
        try:
            cb()
        except Exception:
            pass


def invalidate_after_bootc_change() -> None:
    invalidate_disk_sections(MUTATION_KEYS_BOOTC)


# R6: central helpers so pages don't scatter key lists (led to 3 duplicate blocks)
def invalidate_bootc() -> None:
    invalidate_probe_caches(["bootc-status-data", "bootc-status-text", "bootc-branch"])


def invalidate_nvidia() -> None:
    invalidate_probe_caches(["nvidia-detect", "hardware-view"])


def refresh_cache(*, system: bool = False, path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    target = path or default_write_path(system=system)
    sections = collect_snapshot()
    update_sections(sections, path=target, system=system)
    return target, sections


# ── Unified probe cache service (mem + disk) ─────────────────────────────────
# System Hub and CLI tools previously owned two separate caches:
#   process.py: PROBE_CACHE (in-memory, per-process, short TTL)
#   probe.py:   disk JSON cache (cross-process, longer DISK_TTL, written by kyth-probe)
# ProbeService merges them into one facade so callers do one `cached()` call
# and get the hierarchy: mem hit → disk hit → fetch() → populate both.

def _disk_section_usable(key: str, data: object) -> bool:
    if data is None:
        return False
    if key == "bootc-status-text" and data == "":
        return False
    if key == "bootc-branch" and data == "":
        return False
    return True


class ProbeService:
    """Owns the hybrid in-memory + on-disk probe cache.

    The service is intentionally small: it does not know how to *collect* any
    section, only how to cache/serve values produced by a caller-supplied
    ``fetch()``. Collection stays in ``default_collectors`` / ``collect_probe_results``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mem: dict[str, tuple[float, object]] = {}

    _MEM_CAP = 64

    def cached(self, key: str, ttl: float, fetch: Callable[[], T]) -> T:
        with self._lock:
            hit = self._mem.get(key)
            if hit is not None and time.monotonic() - hit[0] < ttl:
                # Move to end for LRU
                self._mem[key] = self._mem.pop(key)
                return hit[1]  # type: ignore[return-value]

        if key in DISK_BACKED_KEYS:
            try:
                disk_hit = read_section(key, max_age=max(ttl, DISK_TTL.get(key, ttl)))
                if _disk_section_usable(key, disk_hit):
                    with self._lock:
                        mem = self._mem.get(key)
                        if mem is not None and time.monotonic() - mem[0] < ttl:
                            self._mem[key] = self._mem.pop(key)
                            return mem[1]  # type: ignore[return-value]
                        if len(self._mem) >= self._MEM_CAP:
                            oldest = next(iter(self._mem))
                            self._mem.pop(oldest, None)
                        self._mem[key] = (time.monotonic(), disk_hit)
                    return disk_hit  # type: ignore[return-value]
            except Exception:
                _logger.debug("ProbeService.cached: disk read for %r failed", key, exc_info=True)

        value = fetch()
        # Do not cache empty bootc results — a transient `sudo -n` failure or
        # missing digest would otherwise poison the mem+disk cache for 90s and
        # make the Hub appear "up to date" while bootc is actually unreachable.
        if key in DISK_BACKED_KEYS and not _disk_section_usable(key, value):
            return value  # type: ignore[return-value]
        with self._lock:
            hit = self._mem.get(key)
            if hit is not None and time.monotonic() - hit[0] < ttl:
                self._mem[key] = self._mem.pop(key)
                return hit[1]  # type: ignore[return-value]
            if len(self._mem) >= self._MEM_CAP:
                # Evict oldest
                oldest = next(iter(self._mem))
                self._mem.pop(oldest, None)
            self._mem[key] = (time.monotonic(), value)

        if key in DISK_BACKED_KEYS:
            try:
                update_sections({key: value})
            except Exception:
                _logger.debug("ProbeService.cached: disk write for %r failed", key, exc_info=True)
        return value

    def invalidate(self, keys: Iterable[str] | None = None) -> None:
        if keys is None:
            with self._lock:
                self._mem.clear()
            try:
                invalidate_disk_sections()
            except Exception:
                _logger.warning("ProbeService.invalidate: disk invalidation failed", exc_info=True)
            return
        drop = set(keys)
        with self._lock:
            for key in list(self._mem):
                if key in drop:
                    self._mem.pop(key, None)
        try:
            invalidate_disk_sections(drop)
        except Exception:
            _logger.warning("ProbeService.invalidate: disk invalidation failed", exc_info=True)

    def clear_mem(self) -> None:
        with self._lock:
            self._mem.clear()


# Singleton used by the module-level helpers below and by callers that want
# to hold a reference (tests may instantiate their own ProbeService).
_service = ProbeService()


def probe_cached(key: str, ttl: float, fetch: Callable[[], T]) -> T:
    return _service.cached(key, ttl, fetch)


def invalidate_probe_caches(keys: Iterable[str] | None = None) -> None:
    """Invalidate both mem and disk caches — drop-in replacement for process.invalidate_probe_caches."""
    _service.invalidate(keys)
