"""Repair-page command builders and pure helpers.

UI stays in page_repair*; this module owns paths, bootc ops, and fix commands.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .process import _command_stdout, _with_idle_inhibit
from .privileged import bootc_action, helper_action, systemctl_action


def read_sys_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


_read_sys_text = read_sys_text


def sleep_mode_label(mem_sleep: str) -> str:
    """Map /sys/power/mem_sleep's raw text to the label page_repair.py shows."""
    if "[deep]" in mem_sleep:
        return "S3 deep (good)"
    if "[s2idle]" in mem_sleep:
        return "s2idle (modern standby — may wake early)"
    if mem_sleep:
        return mem_sleep.strip()
    return "unknown"


def setup_transfer_helper() -> str:
    """Return path to kyth-setup-transfer (installed or repo checkout)."""
    installed = "/usr/bin/kyth-setup-transfer"
    if os.path.exists(installed):
        return installed
    # build_files/kyth-setup-transfer relative to this package
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "kyth-setup-transfer")
    )


_setup_transfer_helper = setup_transfer_helper


def session_snapshot_command() -> list[str]:
    return ["/usr/bin/kyth-session-snapshot"]


def setup_export_command(destination: str) -> list[str]:
    return [setup_transfer_helper(), "export", destination]


def setup_restore_command(archive: str) -> list[str]:
    return [setup_transfer_helper(), "restore", archive]


def setup_summary_command(archive: str) -> list[str]:
    return [setup_transfer_helper(), "summary", archive]


def force_deep_sleep_command() -> list[str]:
    return helper_action("sleep-mode", "deep").command()


def force_deep_sleep() -> tuple[bool, str]:
    """Apply deep sleep for this session. Returns (ok, error_text)."""
    from .process import _run_command

    result = _run_command(force_deep_sleep_command(), timeout=8)
    if result is None:
        return False, "command failed to start"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "").strip() or "unknown error"
    return True, ""


def set_exe_mime_defaults(bottles_desktop: str = "com.usebottles.bottles.desktop") -> None:
    from .process import _run_command

    for mime in (
        "application/x-ms-dos-executable",
        "application/x-msdos-program",
        "application/x-msi",
    ):
        _run_command(["xdg-mime", "default", bottles_desktop, mime], timeout=5)


def enable_clipboard_history(*, max_items: int = 25) -> None:
    from .plasma import kwriteconfig_command
    from .process import _run_command

    _run_command(
        kwriteconfig_command("klipperrc", ("General",), "KeepClipboardContents", "true"),
        timeout=5,
    )
    _run_command(
        kwriteconfig_command("klipperrc", ("General",), "MaxClipItems", str(max_items)),
        timeout=5,
    )
    _run_command(
        ["systemctl", "--user", "restart", "plasma-klipper.service"],
        timeout=5,
    )


def wakeup_sources_text(timeout: int = 5) -> str:
    return _command_stdout(
        [
            "bash",
            "-c",
            "grep -r . /sys/bus/*/devices/*/power/wakeup 2>/dev/null"
            " | grep ':enabled'"
            " | sed 's|/sys/bus/||;s|/devices/||;s|/power/wakeup:enabled||'"
            " | sort",
        ],
        timeout=timeout,
    )


def rollback_command() -> list[str]:
    return _with_idle_inhibit(
        bootc_action("rollback").command(),
        "KythOS is staging a rollback",
    )


def reset_command() -> list[str]:
    return _with_idle_inhibit(
        bootc_action("reset").command(),
        "KythOS is resetting the system",
    )


def exe_association_mimes() -> list[str]:
    return [
        "application/x-ms-dos-executable",
        "application/x-msdos-program",
        "application/x-msi",
    ]


def bottles_desktop_id() -> str:
    return "com.usebottles.bottles.desktop"


def task_manager_commands() -> list[list[str]]:
    cmds: list[list[str]] = []
    if shutil.which("plasma-systemmonitor"):
        cmds.append(["plasma-systemmonitor"])
    if shutil.which("ksysguard"):
        cmds.append(["ksysguard"])
    if shutil.which("konsole") and shutil.which("btop"):
        cmds.append(["konsole", "-e", "btop"])
    if shutil.which("konsole"):
        cmds.append(["konsole", "-e", "top"])
    return cmds


def volume_mixer_commands() -> list[list[str]]:
    cmds: list[list[str]] = []
    for binary in ("pavucontrol-qt", "pavucontrol", "plasma-pa"):
        if shutil.which(binary):
            cmds.append([binary])
    if shutil.which("kcmshell6"):
        cmds.append(["kcmshell6", "kcm_pulseaudio"])
    return cmds


def printer_setup_commands() -> list[list[str]]:
    cmds: list[list[str]] = [
        systemctl_action("enable", "cups.service", now=True).command(),
    ]
    for binary in ("kcmshell6", "systemsettings"):
        if binary == "kcmshell6" and shutil.which("kcmshell6"):
            cmds.append(["kcmshell6", "kcm_printer_manager"])
        elif binary == "systemsettings" and shutil.which("systemsettings"):
            cmds.append(["systemsettings"])
    return cmds
