"""Reusable probes for post-update and suspend/resume diagnostics."""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

from .commands import CommandRunner, DEFAULT_RUNNER
from .diagnostics import DiagnosticReporter
from .system.gpu import loaded_kernel_modules, lspci_gpu_lines


SERVICE_LABELS = {
    "pipewire.service": "PipeWire",
    "wireplumber.service": "WirePlumber",
    "bluetooth.service": "Bluetooth service",
}


def is_live_image(cmdline: Path = Path("/proc/cmdline")) -> bool:
    """Return whether the current kernel command line marks a Kyth live image."""
    try:
        return "kyth.live" in cmdline.read_text(encoding="utf-8").split()
    except OSError:
        return False


def deployment_id(
    reporter: DiagnosticReporter,
    runner: CommandRunner = DEFAULT_RUNNER,
) -> str:
    """Return a stable identifier for the currently booted deployment."""
    if reporter.have("ostree"):
        result = runner.text(["ostree", "admin", "status"])
        if result is not None:
            for line in result.stdout.splitlines():
                if line.strip().startswith("*"):
                    parts = line.split()
                    if len(parts) >= 3:
                        return f"{parts[1]}.{parts[2]}"
    if reporter.have("bootc"):
        result = runner.text(["bootc", "status", "--format", "json"])
        if result is not None and result.returncode == 0:
            try:
                digest = json.loads(result.stdout).get("status", {}).get("booted", {}).get("image", {}).get(
                    "imageDigest", ""
                )
            except (json.JSONDecodeError, AttributeError):
                digest = ""
            if digest:
                return str(digest)
    return runner.stdout(["uname", "-r"])


def check_gpu_modules(reporter: DiagnosticReporter) -> None:
    """Report whether the expected kernel driver is loaded for the first GPU."""
    if not reporter.have("lspci"):
        reporter.warn_check("GPU drivers", "lspci is missing, so GPU drivers were not checked.")
        return
    gpus = lspci_gpu_lines()
    if not gpus:
        reporter.warn_check("GPU drivers", "No GPU was detected by lspci.")
        return
    gpu_line = gpus[0].lower()
    modules = loaded_kernel_modules()
    expectations = (
        ("nvidia", ("nvidia",), "NVIDIA"),
        ("amd", ("amdgpu",), "AMD"),
        ("ati", ("amdgpu",), "AMD"),
        ("intel", ("i915", "xe"), "Intel"),
    )
    for marker, expected, label in expectations:
        if marker not in gpu_line:
            continue
        if any(module in modules for module in expected):
            reporter.pass_check("GPU drivers", f"{'/'.join(expected)} loaded")
        else:
            reporter.warn_check(
                "GPU drivers",
                f"{label} GPU detected but {'/'.join(expected)} is not loaded.",
            )
        return
    reporter.pass_check("GPU drivers", "Generic display controller active")


def check_gpu_detected(reporter: DiagnosticReporter) -> None:
    """Report whether PCI probing can see a display controller."""
    if not reporter.have("lspci"):
        reporter.warn_check("GPU detected", "lspci command not found")
        return
    gpus = lspci_gpu_lines()
    if gpus:
        reporter.pass_check("GPU detected", gpus[0].strip())
    else:
        reporter.warn_check("GPU detected", "no GPU found via lspci")


def check_vulkan(
    reporter: DiagnosticReporter,
    *,
    warning: str,
    runner: CommandRunner = DEFAULT_RUNNER,
) -> None:
    """Run the bounded Vulkan summary probe and report its health."""
    if not reporter.have("vulkaninfo"):
        reporter.warn_check("Vulkan", "vulkaninfo unavailable")
        return
    try:
        result = runner.run(["vulkaninfo", "--summary"], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        reporter.warn_check("Vulkan", f"{warning} (timeout)")
        return
    except OSError:
        reporter.warn_check("Vulkan", warning)
        return
    if result.returncode == 0:
        reporter.pass_check("Vulkan", "responding")
    else:
        reporter.warn_check("Vulkan", warning)


def check_services(
    reporter: DiagnosticReporter,
    services: Iterable[tuple[str, bool]],
    runner: CommandRunner = DEFAULT_RUNNER,
) -> None:
    """Check systemd services, where the boolean selects the user manager."""
    if not reporter.have("systemctl"):
        return
    for service, user_service in services:
        command = ["systemctl"]
        if user_service:
            command.append("--user")
        command.extend(["is-active", service])
        result = runner.optional(command, capture_output=True)
        label = SERVICE_LABELS.get(service, service)
        if result is not None and result.returncode == 0:
            reporter.pass_check(label, "active")
        else:
            # Check Result for oneshot / exit success services
            show_cmd = ["systemctl"]
            if user_service:
                show_cmd.append("--user")
            show_cmd.extend(["show", "-p", "Result", "--value", service])
            show_res = runner.optional(show_cmd, capture_output=True)
            res_val = show_res.stdout.strip() if show_res else ""
            if res_val == "success":
                reporter.pass_check(label, "completed successfully")
            else:
                reporter.warn_check(label, "not active")



def check_deployment_rollback(
    reporter: DiagnosticReporter,
    runner: CommandRunner = DEFAULT_RUNNER,
) -> tuple[list[str], list[str]]:
    """Return failures and warnings for deployment/rollback availability."""
    failures: list[str] = []
    warnings: list[str] = []
    if reporter.have("ostree"):
        result = runner.text(["ostree", "admin", "status"])
        if result is None:
            warnings.append("Failed to query ostree admin status.")
        else:
            count = sum(
                1
                for line in result.stdout.splitlines()
                if re.match(r"^\*?\s+[A-Za-z0-9_-]+\s", line)
            )
            if count < 2:
                warnings.append("Rollback deployment not visible yet.")
    elif reporter.have("bootc"):
        result = runner.optional(["bootc", "status"], capture_output=True)
        if result is None or result.returncode != 0:
            warnings.append("bootc status needs root; rollback was not checked here.")
    else:
        failures.append("No deployment tool found.")
    return failures, warnings


def check_loginctl(
    reporter: DiagnosticReporter,
    runner: CommandRunner = DEFAULT_RUNNER,
) -> None:
    if not reporter.have("loginctl"):
        reporter.warn_check("Login session", "loginctl command not found")
        return
    session_id = os.environ.get("XDG_SESSION_ID", "self")
    result = runner.optional(["loginctl", "show-session", session_id], capture_output=True)
    if result is not None and result.returncode == 0:
        reporter.pass_check("Login session", "logind can see this session")
    else:
        reporter.warn_check("Login session", "session not visible through loginctl")
