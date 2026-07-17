"""Repair-page command builders and pure helpers.

UI stays in page_repair*; this module owns paths, bootc ops, and fix commands.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .process import _command_stdout, _with_idle_inhibit


def read_sys_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


_read_sys_text = read_sys_text


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
    return ["sudo", "-A", "bash", "-c", "echo deep > /sys/power/mem_sleep"]


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
        ["sudo", "bootc", "rollback"],
        "KythOS is staging a rollback",
    )


def reset_command() -> list[str]:
    return _with_idle_inhibit(
        ["sudo", "bootc", "reset"],
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
        ["sudo", "systemctl", "enable", "--now", "cups"],
    ]
    for binary in ("kcmshell6", "systemsettings"):
        if binary == "kcmshell6" and shutil.which("kcmshell6"):
            cmds.append(["kcmshell6", "kcm_printer_manager"])
        elif binary == "systemsettings" and shutil.which("systemsettings"):
            cmds.append(["systemsettings"])
    return cmds
