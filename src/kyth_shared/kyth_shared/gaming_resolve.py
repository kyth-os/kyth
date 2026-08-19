"""Single gaming resolver — one source for COPRs + Umu + Proton versions.

Build-time `packages-static.sh` + `thirdparty.sh` + `proton-cachyos.sh`
previously each re-resolved “latest” or relied on env-only `UMU_VERSION` /
`PROTON_CACHYOS_VER`. Runtime `services/gaming/*` and Hub pages read the same
tools from different code paths, so the Hub could offer a Proton the image
never baked.

This module is the canonical re-export: build scripts `python3 -c
"from kyth_shared.gaming_resolve import GAMING_COPRS"` and Hub pages
`from kyth_shared.gaming_resolve import gaming_versions` share one file.
"""

from __future__ import annotations
import logging

import json
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Re-export the canonical COPR list — `repos.py` is the only place that
# enumerates them; `packages-static.sh` must not duplicate the list.

_GAMING_VERSIONS_PATHS = (
    Path(__file__).resolve().parents[2] / "config" / "gaming-versions.json",
    Path("/ctx/config/gaming-versions.json"),
    Path("/usr/share/kyth/config/gaming-versions.json"),
    Path("/etc/kyth/config/gaming-versions.json"),
)


@dataclass(frozen=True, slots=True)
class GamingVersions:
    umu_version: str = ""
    proton_cachyos_version: str = ""
    proton_cachyos_repo: str = "CachyOS/proton-cachyos"
    mesa_git_copr: str = ""  # empty = disabled (ENABLE_MESA_GIT=0)

    def is_pinned(self) -> bool:
        return bool(self.umu_version and self.proton_cachyos_version)


def _load_file_versions() -> dict[str, str]:
    for path in _GAMING_VERSIONS_PATHS:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
            except Exception:
                continue
    return {}


def gaming_versions() -> GamingVersions:
    file_vals = _load_file_versions()
    # Offline cache — once resolved, persist to /var/lib/kyth/gaming-versions.json so Hub
    # can show Proton/umu versions even when offline or env vars are unset. Hash-gated like RPM cache.
    cache_path = Path("/var/lib/kyth/gaming-versions.json")
    if not file_vals and cache_path.is_file():
        try:
            cache_vals = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cache_vals, dict):
                file_vals = {str(k): str(v) for k, v in cache_vals.items()}
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass
    gv = GamingVersions(
        umu_version=os.environ.get("UMU_VERSION") or file_vals.get("umu_version", ""),
        proton_cachyos_version=os.environ.get("PROTON_CACHYOS_VER") or file_vals.get("proton_cachyos_version", ""),
        proton_cachyos_repo=file_vals.get("proton_cachyos_repo", "CachyOS/proton-cachyos"),
        mesa_git_copr=file_vals.get("mesa_git_copr", ""),
    )
    # Write back to cache when we have a pinned version and cache is missing/stale
    if gv.is_pinned() and not cache_path.is_file():
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"umu_version": gv.umu_version, "proton_cachyos_version": gv.proton_cachyos_version}, indent=2), encoding="utf-8")
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass
    return gv


def gaming_versions_label() -> str:
    """Value for OCI label `org.kyth.gaming-versions` (human-readable)."""
    gv = gaming_versions()
    parts = []
    if gv.umu_version:
        parts.append(f"umu@{gv.umu_version}")
    if gv.proton_cachyos_version:
        parts.append(f"proton-cachyos@{gv.proton_cachyos_version}")
    if gv.mesa_git_copr:
        parts.append(f"mesa-git:{gv.mesa_git_copr}")
    return ", ".join(parts) if parts else "unpinned"
