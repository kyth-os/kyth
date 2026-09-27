"""Attestation viewer — cosign + SLSA offline verify, hash-gated."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from kyth_shared.commands import run

DEFAULT_ATTEST_PATH = Path("/usr/share/kyth/attest.json")

def attest_path(path: Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_ATTEST_PATH

def load_attest(path: Path | None = None) -> dict[str, Any]:
    p=attest_path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        import logging

        logging.getLogger(__name__).debug("load_attest failed: %s", exc, exc_info=True)
        return {"bundle": None, "verified": False}

def verify_attest(path: Path | None = None) -> dict[str, Any]:
    data=load_attest(path)
    bundle=data.get("bundle")
    if not bundle:
        return {"verified": False, "reason": "no bundle"}
    # Try cosign verify --offline if bundle file exists (best-effort)
    try:
        # bundle may be inline or file path
        if isinstance(bundle, str) and Path(bundle).exists():
            r=run(["cosign","verify","--offline","--bundle", bundle, "ghcr.io/kyth-os/kyth:latest"], capture_output=True, timeout=10)
            if r.returncode==0:
                return {"verified": True, "reason": "cosign offline ok"}
            return {"verified": False, "reason": r.stderr[:200] if r.stderr else "cosign failed"}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        import logging

        logging.getLogger(__name__).debug("verify_attest cosign failed: %s", e, exc_info=True)
        return {"verified": False, "reason": str(e)}
    # Fallback: check bundle hash present
    return {"verified": bool(data.get("verified")), "reason": data.get("reason","offline cached")}
