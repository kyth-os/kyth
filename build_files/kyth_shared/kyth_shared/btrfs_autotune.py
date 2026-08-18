"""Btrfs autotune — btrfs-autotune.toml, weekly timer if needed."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_BTRFS_AUTOTUNE_PATH = Path("/etc/kyth/btrfs-autotune.toml")
AUTOTUNE_SCRIPT = Path("/usr/libexec/kyth-btrfs-autotune")


def btrfs_autotune_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "btrfs-autotune.toml"
    return DEFAULT_BTRFS_AUTOTUNE_PATH


def load_btrfs_autotune(path: Path | None = None) -> dict[str, Any]:
    p = btrfs_autotune_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": True, "threshold": 80}
    return {"enabled": bool(data.get("enabled", True)), "threshold": max(50, min(95, int(data.get("threshold", 80))))}


def save_btrfs_autotune(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = btrfs_autotune_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", True))
    thr = max(50, min(95, int(cfg.get("threshold", 80))))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(f"# Kyth btrfs autotune — offline\nenabled = {str(en).lower()}\nthreshold = {thr}\n", encoding="utf-8")
    tmp.replace(p)
    return p


def generate_btrfs_autotune(cfg: dict[str, Any] | None = None, script: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_btrfs_autotune()
    script = script or AUTOTUNE_SCRIPT
    if not cfg.get("enabled"):
        try:
            if script.exists():
                script.unlink()
        except OSError:
            pass
        return None
    thr = int(cfg.get("threshold", 80))
    content = f"""#!/usr/bin/env bash
set -euo pipefail
# Kyth btrfs autotune — generated, runs weekly
th={thr}
for mp in / /var; do
  [[ -d $mp ]] || continue
  fst=$(findmnt -no FSTYPE -T $mp 2>/dev/null || echo "")
  [[ $fst == btrfs ]] || continue
  used=$(btrfs filesystem usage -b $mp 2>/dev/null | awk '/Used:/ {{print $2}}' | head -n1 || echo 0)
  total=$(btrfs filesystem usage -b $mp 2>/dev/null | awk '/Device size:/ {{print $4}}' | head -n1 || echo 0)
  if [[ $total -gt 0 ]]; then
    pct=$(( used * 100 / total ))
    if (( pct > th )); then
      btrfs balance start -dusage=50 -musage=50 $mp 2>&1 | logger -t kyth-btrfs-autotune || true
      btrfs filesystem defragment -r -czstd $mp 2>&1 | logger -t kyth-btrfs-autotune || true
    fi
  fi
done
"""
    script.parent.mkdir(parents=True, exist_ok=True)
    tmp = script.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.chmod(0o755)
    tmp.replace(script)
    return script