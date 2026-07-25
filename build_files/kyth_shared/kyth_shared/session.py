"""Shared utilities for user login session configuration, first-boot apps, and autostart tasks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path


def write_code_argv(path: Path) -> None:
    """Disable keyring prompt in VS Code argv.json."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            pass
    data["password-store"] = "basic"
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def write_chromium_flags(path: Path) -> None:
    """Configure password store to basic in Chromium/Brave flags file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    lines = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            pass

    updated = []
    wrote_password_store = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--password-store=") or stripped.startswith("password-store="):
            if not wrote_password_store:
                updated.append("--password-store=basic")
                wrote_password_store = True
            continue
        updated.append(line)

    if not wrote_password_store:
        updated.append("--password-store=basic")

    try:
        path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    except Exception:
        pass


def disable_vscode_brave_wallet_prompts(home: Path) -> None:
    """Disable keyring integrations for VS Code and Brave browser to stop KWallet prompts."""
    write_code_argv(home / ".config" / "Code" / "argv.json")
    for flags_path in (
        home / ".config" / "brave-flags.conf",
        home / ".config" / "BraveSoftware" / "Brave-Browser" / "brave-flags.conf",
        home / ".config" / "BraveSoftware" / "Brave-Browser" / "chrome-flags.conf",
        home / ".var" / "app" / "com.brave.Browser" / "config" / "brave-flags.conf",
        home / ".var" / "app" / "com.brave.Browser" / "config" / "chrome-flags.conf",
        home / ".var" / "app" / "com.brave.Browser" / "config" / "BraveSoftware" / "Brave-Browser" / "brave-flags.conf",
        home / ".var" / "app" / "com.brave.Browser" / "config" / "BraveSoftware" / "Brave-Browser" / "chrome-flags.conf",
    ):
        write_chromium_flags(flags_path)


def write_app_status(status_file: Path, state: str, message: str) -> None:
    """Write firstboot setup status variables to a file."""
    status_file.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime_now_iso()
    content = (
        f"state={state}\n"
        f"message={message}\n"
        f"updated={now_str}\n"
    )
    try:
        status_file.write_text(content, encoding="utf-8")
    except Exception:
        pass


def datetime_now_iso() -> str:
    from datetime import datetime
    try:
        return datetime.now().astimezone().isoformat()
    except Exception:
        return str(time.time())


def check_firstboot_app_status(force: bool = False, delay: int = 20, notify_ready: bool = False) -> int:
    """Determine setup progress of default flatpak packages, notifying users and updating status logs."""
    from kyth_shared.diagnostics import DiagnosticReporter

    home = Path.home()
    stamp_dir = home / ".local/share/kyth"
    stamp = stamp_dir / "firstboot-app-status-v1"
    status_file = stamp_dir / "first-run-apps.status"
    default_done = Path("/var/lib/kyth/default-flatpaks-v10-done")

    # Read proc cmdline
    try:
        cmdline = Path("/proc/cmdline").read_text(encoding="utf-8")
        if "kyth.live" in cmdline.split():
            return 0
    except Exception:
        pass

    if not force and stamp.is_file() and default_done.is_file():
        return 0

    time.sleep(delay)

    reporter = DiagnosticReporter("Firstboot Status")

    if not shutil.which("flatpak"):
        write_app_status(status_file, "needs_attention", "Flatpak is not available. Open System Hub > Repair for details.")
        return 2

    missing_ids = []
    for app in (
        "com.valvesoftware.Steam",
        "net.lutris.Lutris",
        "com.heroicgameslauncher.hgl",
        "com.usebottles.bottles",
        "com.github.mtkennerly.ludusavi",
    ):
        res = subprocess.run(["flatpak", "info", app], capture_output=True, check=False)
        if res.returncode != 0:
            missing_ids.append(app)

    if not missing_ids:
        write_app_status(status_file, "ready", "Steam, launchers, Bottles, and save backup tools are installed.")
        if force or notify_ready:
            reporter.notify("KythOS apps are ready", "Steam, launchers, Bottles, and save backup tools are installed.")
        try:
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.touch(exist_ok=True)
        except Exception:
            pass
        return 0

    # Query systemd service status
    service_state = "unknown"
    if shutil.which("systemctl"):
        res = subprocess.run(
            ["systemctl", "is-active", "kyth-default-flatpaks.service"],
            capture_output=True,
            text=True,
            check=False,
        )
        service_state = res.stdout.strip()

    if service_state in ("active", "activating"):
        write_app_status(status_file, "setting_up", "Game launchers and migration tools are installing in the background.")
    elif service_state == "failed":
        write_app_status(status_file, "failed", "Some default apps are missing. Open System Hub > Repair and retry Game Apps.")
    else:
        # Try starting
        started = False
        if shutil.which("sudo"):
            res = subprocess.run(
                ["sudo", "-n", "systemctl", "start", "kyth-default-flatpaks.service"],
                capture_output=True,
                check=False,
            )
            if res.returncode == 0:
                started = True

        if started:
            write_app_status(
                status_file,
                "setting_up",
                "Game launchers and migration tools have started installing in the background.",
            )
        else:
            write_app_status(
                status_file,
                "needs_attention",
                "Some default apps are missing. Connect to the network, then open System Hub > Repair and retry Game Apps.",
            )

    return 0
