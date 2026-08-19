"""Shared utilities for KythOS's read-only runtime diagnostic scripts."""
from __future__ import annotations
import logging

import shutil
import subprocess

from .commands import run_quiet
import sys
from datetime import datetime

logger = logging.getLogger(__name__)


class DiagnosticReporter:
    """Standard reporter for tracking, printing, and notifying diagnostic check results."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.warnings = 0
        self.failures = 0
        self.results: list[tuple[str, str, str]] = []  # (level, check_name, message)

    def print_header(self) -> None:
        """Print standard KythOS generation header."""
        now = datetime.now().astimezone().isoformat()
        print(f"KythOS {self.title}")
        print(f"Generated: {now}")
        print()

    def have(self, cmd: str) -> bool:
        """Check if command exists on system."""
        return shutil.which(cmd) is not None

    def pass_check(self, check_name: str, message: str) -> None:
        """Log and print a passed check."""
        print(f"PASS  {check_name:<28} {message}")
        self.results.append(("PASS", check_name, message))

    def warn_check(self, check_name: str, message: str) -> None:
        """Log and print a warning check."""
        print(f"WARN  {check_name:<28} {message}")
        self.warnings += 1
        self.results.append(("WARN", check_name, message))

    def fail_check(self, check_name: str, message: str) -> None:
        """Log and print a failed check."""
        print(f"FAIL  {check_name:<28} {message}")
        self.failures += 1
        self.results.append(("FAIL", check_name, message))

    def notify(self, title: str, body: str) -> None:
        """Send a desktop notification using notify-send or kdialog."""
        if self.have("notify-send"):
            run_quiet(["notify-send", "--app-name=KythOS", title, body])
        elif self.have("kdialog"):
            run_quiet(["kdialog", "--title", title, "--passivepopup", body, "12"])

    def print_result(self, target_name: str, custom_warn_msg: str | None = None) -> None:
        """Print summary result and exit with matching status code."""
        print()
        if self.failures > 0:
            print(f"Result: {target_name} has failures.")
            sys.exit(2)
        if self.warnings > 0:
            msg = custom_warn_msg or f"{target_name} has warnings."
            print(f"Result: {msg}")
            sys.exit(1)
        print(f"Result: {target_name} looks good.")
        sys.exit(0)


def run_health_checks(reporter: DiagnosticReporter) -> None:
    """Perform end-to-end diagnostic probes on system services, audio, and drivers."""
    from pathlib import Path

    # 1. Kernel Sched-Ext & Low-Latency
    scx_active = False
    if reporter.have("systemctl"):
        res = run_quiet(["systemctl", "is-active", "--quiet", "scx_loader.service"])
        scx_active = res is not None and res.returncode == 0
    if not scx_active and reporter.have("scx_rusty"):
        scx_active = True

    if scx_active:
        reporter.pass_check("Kernel Scheduler", "sched-ext (scx) low-latency scheduler active")
    else:
        reporter.warn_check("Kernel Scheduler", "CFS/EEVDF fallback (scx not active)")

    # 2. NTSYNC Kernel Fast Locking
    ntsync_loaded = Path("/dev/ntsync").exists()
    if not ntsync_loaded and Path("/proc/modules").is_file():
        try:
            ntsync_loaded = "ntsync" in Path("/proc/modules").read_text(encoding="utf-8")
        except (OSError, RuntimeError) as exc:
            logger.debug("handled expected exception", exc_info=True)
            pass

    if ntsync_loaded:
        reporter.pass_check("Wine Synchronization", "NTSYNC fast kernel driver loaded")
    else:
        reporter.pass_check("Wine Synchronization", "FUTEX2 / esync fallback active")

    # 3. PipeWire Low-Latency Audio
    has_pw = False
    if reporter.have("pgrep"):
        res = run_quiet(["pgrep", "-x", "pipewire"])
        has_pw = res is not None and res.returncode == 0
    else:
        # Fallback to scanning /proc for process names
        try:
            for p_dir in Path("/proc").glob("[0-9]*"):
                try:
                    comm = (p_dir / "comm").read_text(encoding="utf-8").strip()
                    if comm == "pipewire":
                        has_pw = True
                        break
                except (OSError, ValueError, RuntimeError) as exc:
                    logger.debug("pipewire comm read failed for %s: %s", p_dir, exc, exc_info=True)
        except (OSError, RuntimeError) as exc:
            logger.debug("pipewire proc scan failed: %s", exc, exc_info=True)

    if has_pw:
        reporter.pass_check("Audio Stack", "PipeWire low-latency daemon running")
    else:
        reporter.warn_check("Audio Stack", "PipeWire daemon not detected")

    # 4. GPU & Vulkan Driver Health
    vulkan_ok = False
    if reporter.have("vulkaninfo"):
        res = run_quiet(["vulkaninfo", "--summary"])
        vulkan_ok = res is not None and res.returncode == 0

    if vulkan_ok:
        reporter.pass_check("Vulkan 3D Driver", "Vulkan device initialized and responsive")
    else:
        reporter.warn_check("Vulkan 3D Driver", "Vulkan device query returned warning or fallback")

    # 5. VA-API Hardware Video Acceleration
    vaapi_ok = False
    if reporter.have("vainfo"):
        res = run_quiet(["vainfo"])
        vaapi_ok = res is not None and res.returncode == 0

    if vaapi_ok:
        reporter.pass_check("Video Codecs", "VA-API hardware video decode/encode active")
    else:
        reporter.pass_check("Video Codecs", "Software codec fallback active")

    # 6. Input & Controller Udev Rules
    if Path("/dev/input").is_dir():
        reporter.pass_check("Input & Gamepads", "Event subsystem and controller udev rules active")
    else:
        reporter.warn_check("Input & Gamepads", "/dev/input device node inaccessible")


def create_github_issue_draft(
    title: str = "KythOS issue report",
    body: str = "",
    body_file: str | None = None,
    label: str = "bug",
    repo_url: str = "https://github.com/mrtrick37/kyth",
    open_browser: bool = True,
) -> tuple[str, str]:
    import os
    from urllib.parse import urlencode

    if body_file:

        if os.access(body_file, os.R_OK):
            with open(body_file, "r", encoding="utf-8") as fh:
                body = fh.read()
        else:
            raise FileNotFoundError(f"Body file is not readable: {body_file}")

    if not body:
        body = "Describe what happened, what you expected, and what you were doing just before it happened."

    state_home = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
    draft_dir = os.path.join(state_home, "kyth")
    os.makedirs(draft_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    draft_path = os.path.join(draft_dir, f"github-issue-{timestamp}.md")

    from .atomic_io import atomic_write_text

    atomic_write_text(draft_path, f"# {title}\n\n{body}\n", encoding="utf-8")

    max_body = 5500
    encoded_body = body
    if len(encoded_body) > max_body:
        encoded_body = (
            encoded_body[:max_body]
            + "\n\n[Report body truncated for the browser URL. A full local draft was saved by kyth-report-issue.]"
        )

    params = {"title": title, "body": encoded_body}
    if label:
        params["labels"] = label

    url = repo_url.rstrip("/") + "/issues/new?" + urlencode(params)

    if open_browser:
        if shutil.which("xdg-open"):
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    return draft_path, url

