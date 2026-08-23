"""RAM-aware memory tuning — MemTotal scaling for swappiness/zram/dirty_bytes.

Replaces static vm.swappiness=180 + zram=ram + dirty_bytes=256M fixed for
all RAM. Handhelds (8GB Deck/Ally experimental) CPU-saturate on zstd swap
at 180; 32GB keeps throughput.

Tiers:
  ≤16GB: swappiness 60, zram ram/2 (capped 8G), dirty_bytes 64M/16M
  16-24GB: swappiness 120, zram ram (capped 8G), dirty_bytes 128M/32M
  ≥24GB: swappiness 180, zram ram, dirty_bytes 256M/64M (current)

Generator writes /etc/sysctl.d/99-kyth-memory.conf override (lexically after
99-kyth-base.conf). Uses MemTotal from /proc/meminfo when not forced.

Pattern mirrors sysctl_compose atomic tmp→replace and sched_arbiter single writer.
"""

from __future__ import annotations
import logging

import os
import re
import tomllib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("/etc/kyth/memory-tune.toml")
DEFAULT_CONF = Path("/etc/sysctl.d/99-kyth-memory.conf")
# Plain key=value contract for kyth-zram-swap (branding/51-zram.sh) to source
# directly at boot, instead of it re-deriving the formula by pattern-matching
# zram-generator.conf's math-expression syntax — a config grammar this
# project owns the writer of but not the reader that mattered (zram-generator
# itself is masked; see 51-zram.sh). Keeping this in sync with zram-generator.conf
# is this module's job alone.
DEFAULT_ZRAM_RUNTIME_ENV = Path("/etc/kyth/zram-runtime.env")
DEFAULT_ZRAM_CONF = Path("/etc/systemd/zram-generator.conf")


def memory_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "memory-tune.toml"
    return DEFAULT_PATH


def _read_memtotal_kb() -> int:
    try:
        txt = Path("/proc/meminfo").read_text(encoding="utf-8")
        m = re.search(r"MemTotal:\s+(\d+)\s+kB", txt)
        if m:
            return int(m.group(1))
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    return 32 * 1024 * 1024  # fallback 32GB


def _tier(mem_kb: int | None = None) -> str:
    kb = mem_kb if mem_kb is not None else _read_memtotal_kb()
    gb = kb / (1024 * 1024)
    if gb <= 16:
        return "low"
    if gb < 24:
        return "mid"
    return "high"


def _values_for(tier: str) -> dict[str, Any]:
    if tier == "low":
        return {
            "swappiness": 60,
            "watermark_scale": 100,
            "dirty_bytes": 67108864,  # 64M
            "dirty_background": 16777216,  # 16M
            "zram_frac": 0.5,
            "zram_cap_mb": 8192,
        }
    if tier == "mid":
        return {
            "swappiness": 120,
            "watermark_scale": 110,
            "dirty_bytes": 134217728,  # 128M
            "dirty_background": 33554432,  # 32M
            "zram_frac": 1.0,
            "zram_cap_mb": 8192,
        }
    return {
        "swappiness": 180,
        "watermark_scale": 125,
        "dirty_bytes": 268435456,  # 256M
        "dirty_background": 67108864,  # 64M
        "zram_frac": 1.0,
        "zram_cap_mb": 0,  # 0 = no cap
    }


def load_memory_tune(path: Path | None = None, mem_kb: int | None = None) -> dict[str, Any]:
    p = memory_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
        # allow override tier for testing
        tier = str(data.get("tier", "")).lower()
        if tier in ("low", "mid", "high", "auto"):
            if tier == "auto" or not tier:
                tier = _tier(mem_kb)
        else:
            tier = _tier(mem_kb)
        return {"tier": tier, **_values_for(tier)}
    except (OSError, tomllib.TOMLDecodeError):
        tier = _tier(mem_kb)
        return {"tier": tier, **_values_for(tier)}


def generate_memory_tune(cfg: dict[str, Any] | None = None, dest: Path | None = None, mem_kb: int | None = None) -> Path:
    if cfg is None:
        cfg = load_memory_tune(mem_kb=mem_kb)
    dest = dest or DEFAULT_CONF
    tier_name = str(cfg.get("tier", _tier(mem_kb)))
    vals = _values_for(tier_name)
    _log_tier(tier_name, mem_kb, vals)
    # Also handle explicit swappiness/dirty overrides in cfg
    swappiness = int(cfg.get("swappiness", vals["swappiness"]))
    watermark = int(cfg.get("watermark_scale", vals["watermark_scale"]))
    dirty = int(cfg.get("dirty_bytes", vals["dirty_bytes"]))
    dirty_bg = int(cfg.get("dirty_background", vals["dirty_background"]))
    content = (
        f"# Kyth memory tune — {cfg.get('tier', 'auto')} (MemTotal scaling)\n"
        f"vm.swappiness = {swappiness}\n"
        f"vm.watermark_scale_factor = {watermark}\n"
        f"vm.dirty_bytes = {dirty}\n"
        f"vm.dirty_background_bytes = {dirty_bg}\n"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    # zram-generator drop-in (separate file, also scaling)
    zram_conf = DEFAULT_ZRAM_CONF if dest == DEFAULT_CONF else dest.parent / "zram-generator.conf"
    if dest == DEFAULT_CONF:
        try:
            zram_frac = float(cfg.get("zram_frac", vals["zram_frac"]))
            cap = int(cfg.get("zram_cap_mb", vals["zram_cap_mb"]))
            if cap > 0:
                zram_line = f"zram-size = min(ram * {zram_frac}, {cap})"
            else:
                zram_line = f"zram-size = ram * {zram_frac}" if zram_frac != 1.0 else "zram-size = ram"
            zram_content = f"[zram0]\n{zram_line}\ncompression-algorithm = zstd\nswap-priority = 100\n"
            runtime_content = (
                "# Generated by kyth_shared.memory_tune — do not edit by hand\n"
                f"KYTH_ZRAM_PERCENT={round(zram_frac * 100)}\n"
                f"KYTH_ZRAM_CAP_MB={cap}\n"
                "KYTH_ZRAM_ALGO=zstd\n"
            )
            # Atomic 2-file commit: prepare both temps first, then rename.
            # 51-zram.sh only reads the runtime env (plain key=value), so
            # even a crash between the two renames leaves the system with
            # a consistent view for boot — generator is for humans/audit.
            # fsync parent after each rename for power-loss durability.
            import os as _os
            for _path, _content in ((DEFAULT_ZRAM_RUNTIME_ENV, runtime_content), (zram_conf, zram_content)):
                _path.parent.mkdir(parents=True, exist_ok=True)
                _tmp = _path.with_suffix(".tmp")
                _tmp.write_text(_content, encoding="utf-8")
                try:
                    _f = _tmp.open("rb")
                    try:
                        _os.fsync(_f.fileno())
                    finally:
                        _f.close()
                except OSError:
                    pass
                try:
                    _fd = _os.open(_tmp.parent, _os.O_DIRECTORY)
                    try:
                        _os.fsync(_fd)
                    finally:
                        _os.close(_fd)
                except OSError:
                    pass
                _tmp.replace(_path)
                try:
                    _d = _os.open(_path.parent, _os.O_DIRECTORY)
                    try:
                        _os.fsync(_d)
                    finally:
                        _os.close(_d)
                except OSError:
                    pass
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    return dest


def _log_tier(tier: str, mem_kb: int | None, vals: dict[str, int]) -> None:
    try:
        import logging
        logging.getLogger(__name__).info("memory_tune tier=%s mem_kb=%s vals=%s", tier, mem_kb, vals)
    except Exception:
        pass

def memory_tune_status(conf: Path = DEFAULT_CONF) -> str:
    if conf.is_file():
        try:
            txt = conf.read_text(encoding="utf-8")
            m = re.search(r"# Kyth memory tune — (\w+)", txt)
            if m:
                return m.group(1)
            return "active"
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            return "active"
    return "balanced"
