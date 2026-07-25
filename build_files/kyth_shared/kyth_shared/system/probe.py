"""Shared on-disk probe cache for expensive read-only system queries.

``kyth-probe`` (user/system oneshot) refreshes the cache; System Hub and other
CLI tools read it before spawning ``bootc`` / ``flatpak`` / ``lspci``.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

CACHE_VERSION = 1

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

COLLECT_SECTIONS: tuple[str, ...] = tuple(DISK_TTL.keys())

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
    from kyth_shared.system.process import _run_command

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
    from kyth_shared.system.bootc import (
        _branch_from_ref,
        _current_kernel_flavor,
        _fetch_bootc_status_data,
        _fetch_bootc_status_text,
        image_reference_from_status,
    )
    from kyth_shared.system.process import _run_command

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
        # Avoid circular dependencies by dynamically importing drives module from kyth-welcome
        # or kyth_welcome.services.hardware.drives if it can be found.
        # But wait! Can we import kyth_welcome here?
        # Yes, kyth-welcome is allowed to import from kyth_shared, and since collect_snapshot
        # is run during oneshot refresh, we can dynamically look it up.
        try:
            from kyth_welcome.services.hardware import drives as drives_mod
            sections["controllers-detect"] = drives_mod._detect_controllers()
        except ImportError:
            # Fallback when running outside welcome environment
            sections["controllers-detect"] = None
    except Exception:
        sections["controllers-detect"] = None

    return sections


def invalidate_after_flatpak_change() -> None:
    invalidate_disk_sections(MUTATION_KEYS_FLATPAK)


def invalidate_after_bootc_change() -> None:
    invalidate_disk_sections(MUTATION_KEYS_BOOTC)


def refresh_cache(*, system: bool = False, path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    target = path or default_write_path(system=system)
    sections = collect_snapshot()
    update_sections(sections, path=target, system=system)
    return target, sections
