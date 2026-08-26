"""bpftune status — read-only.

bpftune (oracle/bpftune) is an eBPF-based daemon that autonomously
retunes live kernel parameters (TCP buffers, neighbor tables, sysctls…)
based on observed system state. Unlike every tunable under kyth_shared
(io_tune, thp_tune, sched_latency, …) it is not declarative or offline —
it adjusts things continuously while running, which can quietly fight
whatever those tunables already set. It has no official Fedora/EPEL
package; `ujust enable-bpftune` installs it from a third-party COPR
(crono/bpftune-gaming) on request, never automatically.

This module only reads state — installing/enabling/disabling lives in
build_files/just/kyth/performance.just, on the same footing as any other
opt-in ujust recipe (install-asus-tools, install-nvidia-driver, …), not
behind a Hub toggle, since staging a COPR + package layer is a multi-step,
reboot-adjacent operation the Hub's other DataWorker-backed toggles (a
plain systemctl enable/disable) aren't shaped for.
"""
from __future__ import annotations

import logging
import subprocess

from .command import run_sync

_logger = logging.getLogger(__name__)


def bpftune_installed() -> bool:
    try:
        result = run_sync(["rpm", "-q", "bpftune"], capture_output=True, text=True, timeout=5, check=False)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.debug("bpftune rpm -q failed: %s", exc)
        return False


def bpftune_active() -> bool:
    try:
        result = run_sync(
            ["systemctl", "is-active", "bpftune.service"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        return result.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.debug("bpftune is-active check failed: %s", exc)
        return False
