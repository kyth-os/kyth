"""kyth-sched / kyth-scx status and control helpers (no Qt)."""
from __future__ import annotations

import glob
import json
import logging
import os
import subprocess

from kyth_shared.commands import APPLICATION_RUNNER, command_spec

from kyth_welcome.services.command import run_sync
from pathlib import Path
from typing import Any

from .privileged import scheduler_action

_logger = logging.getLogger(__name__)


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
        r = run_sync(
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
            _logger.debug("list_schedulers: /usr/bin/scx_* glob scan failed", exc_info=True)
    return schedulers or ["scx_rusty"]


def is_sched_daemon_active() -> bool:
    try:
        r = run_sync(
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
        APPLICATION_RUNNER.spawn(
            scheduler_action(name),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        _logger.warning("apply_scheduler: failed to launch kyth-scx set %s", name, exc_info=True)


def set_sched_daemon_enabled(enabled: bool) -> None:
    cmd = "start" if enabled else "stop"
    try:
        APPLICATION_RUNNER.spawn(
            command_spec(
                ["systemctl", "--user", cmd, "kyth-sched.service"],
                name="scheduler-daemon", timeout=None,
            ),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        _logger.warning("set_sched_daemon_enabled: failed to %s kyth-sched.service", cmd, exc_info=True)
