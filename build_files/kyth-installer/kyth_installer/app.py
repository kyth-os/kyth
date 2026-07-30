"""Entry point: generates the one-time bootstrap token, starts the HTTP
server in a background thread, and launches Chromium in app/kiosk mode
pointed at it.
"""

import argparse
import json
import os
import secrets
import shutil
import stat
import sys
import threading
import time

from . import config
from .config import PORT
from .context import InstallerContext, InstallLifecycle
from .runner import spawn_command
from .server import Handler, _Server
from .services.installer_service import InstallerService


_ANSWER_FILE_FIELDS = frozenset({
    "disk", "install_mode", "target_partition", "resize_partition", "resize_gib",
    "free_region_start", "free_region_end", "efi_partition", "username", "password",
    "hostname", "timezone", "locale", "keymap", "kernel", "mok_password",
    "confirm_backup", "confirm_erase", "confirm_current",
})


def _load_answer_file(path_value: str) -> dict:
    path = os.path.abspath(path_value)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("Installer answer file must be a regular file, not a symlink.")
    if info.st_mode & 0o077:
        raise ValueError("Installer answer file must not be readable or writable by group/others (use chmod 600).")
    if info.st_size > 64 * 1024:
        raise ValueError("Installer answer file is too large (maximum 64 KiB).")
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Installer answer file must contain one JSON object.")
    unknown = sorted(set(payload) - _ANSWER_FILE_FIELDS)
    if unknown:
        raise ValueError(f"Unknown installer answer-file fields: {', '.join(unknown)}")
    return payload


def run_headless() -> None:
    parser = argparse.ArgumentParser(description="KythOS Installer Headless CLI")
    parser.add_argument("--headless", action="store_true", required=True)
    parser.add_argument("--answer-file", help="Root-only JSON response file (must be mode 0600)")
    parser.add_argument("--disk", help="Target disk path (e.g. /dev/sda)")
    parser.add_argument("--install-mode", choices=["wipe", "alongside", "resize_ntfs", "free_space", "manual"])
    parser.add_argument("--target-partition")
    parser.add_argument("--resize-partition")
    parser.add_argument("--resize-gib", type=int)
    parser.add_argument("--free-region-start", type=int)
    parser.add_argument("--free-region-end", type=int)
    parser.add_argument("--efi-partition")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--hostname")
    parser.add_argument("--timezone")
    parser.add_argument("--locale")
    parser.add_argument("--keymap")
    parser.add_argument("--kernel")
    parser.add_argument("--mok-password")
    parser.add_argument("--confirm-backup", action="store_true", default=None)
    parser.add_argument("--confirm-erase", action="store_true", default=None)
    parser.add_argument("--confirm-current", action="store_true", default=None)

    args, _ = parser.parse_known_args()

    try:
        answer_file = getattr(args, "answer_file", None)
        answers = _load_answer_file(answer_file) if isinstance(answer_file, str) and answer_file else {}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    def setting(name: str, default=None):
        cli_value = getattr(args, name, None)
        if isinstance(cli_value, (str, int, bool)) and cli_value not in (None, ""):
            return cli_value
        return answers.get(name, default)

    context = InstallerContext()
    service = InstallerService(context)

    body = {
        "disk": setting("disk", ""),
        "install_mode": setting("install_mode", "wipe"),
        "target_partition": setting("target_partition", ""),
        "resize_partition": setting("resize_partition", ""),
        "resize_gib": setting("resize_gib", 0),
        "free_region_start": setting("free_region_start", 0),
        "free_region_end": setting("free_region_end", 0),
        "efi_partition": setting("efi_partition", ""),
        "username": setting("username", ""),
        "password": setting("password", ""),
        "hostname": setting("hostname", "kyth"),
        "timezone": setting("timezone", "UTC"),
        "locale": setting("locale", "en_US.UTF-8"),
        "keymap": setting("keymap", "us"),
        "kernel": setting("kernel", "fedora"),
        "mok_password": setting("mok_password", ""),
        "confirm_backup": setting("confirm_backup", False),
        "confirm_erase": setting("confirm_erase", False),
        "confirm_current": setting("confirm_current", False),
    }

    res = service.start_install(body)
    if not res.get("started"):
        print(f"Error: {res.get('message')}")
        sys.exit(1)

    print("Installation started...")
    last_idx = 0
    while True:
        with context.events.condition:
            context.events.condition.wait_for(
                lambda: len(context.events.events) > last_idx or context.lifecycle in (InstallLifecycle.DONE, InstallLifecycle.FAILED),
                timeout=1.0
            )
            events = list(context.events.events)
        
        while last_idx < len(events):
            evt = events[last_idx]
            last_idx += 1
            if evt.get("type") == "log":
                print(evt.get("text"))
            elif evt.get("type") == "progress":
                print(f"Progress: {evt.get('value')}%")
            elif evt.get("type") == "error":
                print(f"Error: {evt.get('message')}")
                sys.exit(1)
            elif evt.get("type") == "done":
                print(f"Installation finished successfully. MOK state: {evt.get('mok_state')}")
                sys.exit(0)

        if context.lifecycle == InstallLifecycle.DONE:
            sys.exit(0)
        if context.lifecycle == InstallLifecycle.FAILED:
            sys.exit(1)


def main() -> None:
    if "--headless" in sys.argv:
        run_headless()
        return

    config._bootstrap_token = secrets.token_urlsafe(32)

    server = _Server(("127.0.0.1", PORT), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    # The installer runs as root (bootc requires it), but Chromium must run as
    # the desktop user so it can connect to the X display. sudo sets $SUDO_USER
    # to the original user; fall back to running Chromium directly if not set
    # (e.g. when testing as root without sudo).
    sudo_user = os.environ.get("SUDO_USER", "")
    chromium_bin = next(
        (b for b in ("chromium", "chromium-browser", "chromium-bin") if shutil.which(b)),
        "chromium",
    )
    # --no-sandbox is required in the live ISO's overlayfs environment where
    # unprivileged user namespaces (needed by Chromium's sandbox) may be
    # unavailable. --disable-gpu is intentionally omitted: it kills the renderer
    # in Fedora's Chromium build (blank gray window). Software GL is provided by
    # Mesa llvmpipe via LIBGL_ALWAYS_SOFTWARE forwarded from the live session env.
    chromium_cmd = [
        chromium_bin,
        f"--app=http://127.0.0.1:{PORT}/?bootstrap_token={config._bootstrap_token}",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-translate",
        "--no-first-run",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--test-type",
        "--password-store=basic",
        "--window-size=1280,800",
        "--window-position=0,0",
    ]
    if sudo_user:
        gui_env = []
        for key in (
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XAUTHORITY",
            "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS",
            "XDG_SESSION_TYPE",
            "QT_QUICK_BACKEND",
            "LIBGL_ALWAYS_SOFTWARE",
            "GALLIUM_DRIVER",
            "MESA_LOADER_DRIVER_OVERRIDE",
        ):
            value = os.environ.get(key)
            if value:
                gui_env.append(f"{key}={value}")
        proc = spawn_command(["sudo", "-u", sudo_user, "env", *gui_env, *chromium_cmd])
    else:
        proc = spawn_command(chromium_cmd)

    # Wait for Chromium to exit so the process and port are released cleanly.
    # This means re-launching the installer from the desktop always gets a fresh server.
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
