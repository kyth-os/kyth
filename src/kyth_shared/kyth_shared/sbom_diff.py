"""Offline SBOM/CVE diff — Hub Supply-Chain tab (no network fetch)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_SBOM_PATH = Path("/usr/share/kyth/sbom.json")
DEFAULT_CVE_PATH = Path("/var/cache/kyth/cve/osv.json")


def sbom_path(path: Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_SBOM_PATH


def cve_path(path: Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_CVE_PATH


def load_sbom(path: Path | None = None) -> dict[str, Any]:
    p = sbom_path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"artifacts": []}


def load_cve(path: Path | None = None) -> dict[str, Any]:
    p = cve_path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"results": []}


def sbom_diff(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    cur = {a.get("name"): a for a in current.get("artifacts", []) if isinstance(a, dict)}
    prev = {a.get("name"): a for a in previous.get("artifacts", []) if isinstance(a, dict)}
    added = [cur[k] for k in cur if k not in prev]
    removed = [prev[k] for k in prev if k not in cur]
    changed = []
    for k in cur:
        if k in prev and cur[k].get("version") != prev[k].get("version"):
            changed.append({"name": k, "from": prev[k].get("version"), "to": cur[k].get("version")})
    return {"added": added, "removed": removed, "changed": changed}


def cve_summary(cve_data: dict[str, Any] | None = None) -> dict[str, Any]:
    if cve_data is None:
        cve_data = load_cve()
    results = cve_data.get("results", [])
    total = 0
    high = 0
    for r in results:
        vulns = r.get("vulnerabilities", []) if isinstance(r, dict) else []
        total += len(vulns)
        for v in vulns:
            sev = str(v.get("severity", "")).upper()
            if sev in ("HIGH", "CRITICAL"):
                high += 1
    return {"total": total, "high": high, "results": len(results)}
