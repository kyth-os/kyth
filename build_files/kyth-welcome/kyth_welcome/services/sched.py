"""kyth-sched / kyth-scx status and control helpers (no Qt)."""
from __future__ import annotations

import glob
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def status_file_path() -> Path:
    uid = os.getuid()
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    return Path(runtime) / "kyth-sched-status.json"


def read_sched_status() -> dict[str, Any]:
    path = status_file_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def list_schedulers() -> list[str]:
    try:
        r = subprocess.run(
            ["kyth-scx", "list"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        schedulers = [s.strip() for s in r.stdout.splitlines() if s.strip()]
    except Exception:
        schedulers = []
    if not schedulers:
        try:
            schedulers = sorted(
                os.path.basename(p)
                for p in glob.glob("/usr/bin/scx_*")
                if os.path.isfile(p) and not p.endswith("scx_loader")
            )
        except Exception:
            pass
    return schedulers or ["scx_lavd", "scx_bpfland", "scx_rusty"]


def is_sched_daemon_active() -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "kyth-sched.service"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def apply_scheduler(name: str) -> None:
    if not name:
        return
    try:
        subprocess.Popen(
            ["sudo", "-n", "/usr/bin/kyth-scx", "set", name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def set_sched_daemon_enabled(enabled: bool) -> None:
    cmd = "start" if enabled else "stop"
    try:
        subprocess.Popen(
            ["systemctl", "--user", cmd, "kyth-sched.service"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
