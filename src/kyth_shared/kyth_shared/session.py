"""Shared utilities for user login session configuration, first-boot apps, and autostart tasks."""
from __future__ import annotations
import logging

import fcntl
import json
import shutil

from .commands import run as run_command
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def acquire_run_lock(lock_path: Path):
    """Take a best-effort exclusive, non-blocking lock at ``lock_path``.

    Returns the open file object on success — the caller MUST keep it alive for
    as long as the lock should be held (closing the file, or the process exiting,
    releases it). Returns ``None`` if another process already holds the lock or
    the lock file cannot be created. Never raises.

    Unlike the ``already_run``/``mark_run`` marker pair (a non-atomic
    check-then-touch), this gives real mutual exclusion between concurrent
    invocations racing the same first-login work.
    """
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "w")  # noqa: SIM115 — held open intentionally
    except OSError:
        return None
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def write_code_argv(path: Path) -> None:
    """Configure VS Code to use KWallet for credential storage."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError, KeyError) as exc:
        import logging; logging.getLogger(__name__).debug("handled %s: %s", "session.py", exc, exc_info=True)
        logger.debug("handled expected exception", exc_info=True)
        pass
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    data["password-store"] = "kwallet5"
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass


def write_chromium_flags(path: Path) -> None:
    """Configure password store to kwallet5 in Chromium/Brave flags file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    lines = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass

    updated = []
    wrote_password_store = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--password-store=") or stripped.startswith("password-store="):
            if not wrote_password_store:
                updated.append("--password-store=kwallet5")
                wrote_password_store = True
            continue
        updated.append(line)

    if not wrote_password_store:
        updated.append("--password-store=kwallet5")

    try:
        path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass


def disable_vscode_brave_wallet_prompts(home: Path) -> None:
    """Configure VS Code and Brave to use KWallet (replaces legacy basic store)."""
    # Kept for backward compatibility; now enables KWallet instead of basic.
    return enable_vscode_brave_wallet_prompts(home)


def enable_vscode_brave_wallet_prompts(home: Path) -> None:
    """Enable KWallet integration for VS Code and Brave browser."""
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


_DEFAULT_FLATPAKS_DIR = Path("/var/lib/kyth")
_DEFAULT_FLATPAKS_GLOB = "default-flatpaks-v*-done"


def default_flatpaks_sentinel(root: Path | None = None) -> Path | None:
    """Newest versioned first-run Flatpak sentinel (``v12``, ``v10``, …).

    The unit filename is bumped when the default app list changes, so callers
    must not hard-code a single version. Any matching stamp means setup ran.
    """
    directory = root if root is not None else _DEFAULT_FLATPAKS_DIR
    best: Path | None = None
    best_n = -1
    try:
        for path in directory.glob(_DEFAULT_FLATPAKS_GLOB):
            name = path.name
            try:
                version = int(name.split("-v", 1)[1].removesuffix("-done"))
            except (IndexError, ValueError):
                continue
            if version >= best_n:
                best_n = version
                best = path
    except OSError:
        return None
    return best


def default_flatpaks_done(root: Path | None = None) -> bool:
    """True when any ``default-flatpaks-v*-done`` sentinel exists."""
    return default_flatpaks_sentinel(root) is not None


def marker_path(name: str) -> Path:
    """Path to a ~/.local/share/kyth stamp file used to gate run-once-unless-force behavior."""
    return Path.home() / ".local/share/kyth" / name


def already_run(name: str) -> bool:
    """Check whether the named marker stamp exists."""
    return marker_path(name).is_file()


def mark_run(name: str) -> None:
    """Create (or touch) the named marker stamp, creating its parent directory if needed."""
    path = marker_path(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass


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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass


def datetime_now_iso() -> str:
    from datetime import datetime
    try:
        return datetime.now().astimezone().isoformat()
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return str(time.time())


def check_firstboot_app_status(force: bool = False, delay: int = 2, notify_ready: bool = False) -> int:
    """Determine setup progress of default flatpak packages, notifying users and updating status logs."""
    from kyth_shared.diagnostics import DiagnosticReporter

    home = Path.home()
    stamp_dir = home / ".local/share/kyth"
    status_file = stamp_dir / "first-run-apps.status"
    default_done = default_flatpaks_done()

    # Read proc cmdline
    try:
        cmdline = Path("/proc/cmdline").read_text(encoding="utf-8")
        if "kyth.live" in cmdline.split():
            return 0
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass

    if not force and already_run("firstboot-app-status-v1") and default_done:
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
        res = run_command(["flatpak", "info", app], capture_output=True, check=False)
        if res.returncode != 0:
            missing_ids.append(app)

    if not missing_ids:
        write_app_status(status_file, "ready", "Steam, launchers, Bottles, and save backup tools are installed.")
        if force or notify_ready:
            reporter.notify("KythOS apps are ready", "Steam, launchers, Bottles, and save backup tools are installed.")
        mark_run("firstboot-app-status-v1")
        return 0

    # Query systemd service status
    service_state = "unknown"
    if shutil.which("systemctl"):
        res = run_command(
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
            res = run_command(
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


def generate_session_snapshot(out_dir: Path | None = None) -> Path:
    """Collect environment diagnostics, configurations, and write a session snapshot file."""
    import socket
    import getpass
    from datetime import datetime

    if out_dir is None:
        out_dir = Path.home() / "Documents" / "KythOS"
    
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"kyth-session-snapshot-{ts}.txt"

    def write_section(title: str) -> None:
        try:
            with out.open("a", encoding="utf-8") as f:
                f.write(f"\n== {title} ==\n")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass

    def run_cmd(args: list[str]) -> None:
        try:
            with out.open("a", encoding="utf-8") as f:
                f.write(f"$ {' '.join(args)}\n")
            res = run_command(args, capture_output=True, text=True, check=False)
            output = res.stdout
            if res.stderr:
                output += res.stderr
            with out.open("a", encoding="utf-8") as f:
                f.write(output)
                if not output.endswith("\n"):
                    f.write("\n")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
            try:
                with out.open("a", encoding="utf-8") as f:
                    f.write(f"Execution failed: {e}\n")
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                logger.debug("handled expected exception", exc_info=True)
                pass

    # Header
    now_iso = datetime.now().astimezone().isoformat()
    user = getpass.getuser() or "unknown"
    try:
        host = socket.gethostname()
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        host = "unknown"

    try:
        with out.open("w", encoding="utf-8") as f:
            f.write("KythOS Session Snapshot\n")
            f.write(f"Generated: {now_iso}\n")
            f.write(f"User: {user}\n")
            f.write(f"Host: {host}\n")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass

    # System Section
    write_section("System")
    run_cmd(["cat", "/etc/os-release"])
    run_cmd(["uname", "-a"])
    run_cmd(["bootc", "status"])

    # Desktop Section
    write_section("Desktop")
    run_cmd(["xdg-user-dir"])
    run_cmd(["xdg-mime", "query", "default", "application/x-ms-dos-executable"])
    run_cmd(["xdg-mime", "query", "default", "application/x-msi"])

    # Installed Flatpaks Section
    write_section("Installed Flatpaks")
    run_cmd(["flatpak", "list", "--app", "--columns=application,name,version,branch"])

    # Gaming Paths Section
    write_section("Gaming Paths")
    gaming_paths = [
        Path.home() / ".local/share/Steam/steamapps",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps",
        Path.home() / "Games",
        Path.home() / "Applications",
    ]
    try:
        with out.open("a", encoding="utf-8") as f:
            for p in gaming_paths:
                if p.exists():
                    f.write(f"{p}\n")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass

    # KythOS Checks Section
    write_section("KythOS Checks")
    for cmd in ("kyth-controller-check", "kyth-resume-check", "kyth-nvidia-status"):
        if shutil.which(cmd):
            run_cmd([cmd])

    # Restore Notes Section
    write_section("Restore Notes")
    notes = (
        "- Reinstall Flatpaks with: flatpak install flathub APP_ID\n"
        "- Keep source code, saves, and documents in /home or synced storage.\n"
        "- System image changes are handled through KythOS updates and bootc rollback.\n"
        "- Do not paste this file publicly without reviewing paths and usernames.\n"
    )
    try:
        with out.open("a", encoding="utf-8") as f:
            f.write(notes)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass

    return out
