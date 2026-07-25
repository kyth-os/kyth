"""Entry point: generates the one-time bootstrap token, starts the HTTP
server in a background thread, and launches Chromium in app/kiosk mode
pointed at it.
"""

import os
import secrets
import shutil
import threading
import time

from . import config
from .config import PORT
from .runner import spawn_command
from .server import Handler, _Server


def run_headless() -> None:
    import argparse
    import sys
    from kyth_installer.context import InstallerContext, InstallLifecycle
    from kyth_installer.services import InstallerService

    parser = argparse.ArgumentParser(description="KythOS Installer Headless CLI")
    parser.add_argument("--headless", action="store_true", required=True)
    parser.add_argument("--disk", required=True, help="Target disk path (e.g. /dev/sda)")
    parser.add_argument("--install-mode", default="wipe", choices=["wipe", "alongside", "resize_ntfs", "free_space", "manual"])
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--hostname", default="kyth")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--kernel", default="fedora")
    parser.add_argument("--mok-password", default="")
    parser.add_argument("--confirm-backup", action="store_true")
    parser.add_argument("--confirm-erase", action="store_true")
    parser.add_argument("--confirm-current", action="store_true")

    args, _ = parser.parse_known_args()

    context = InstallerContext()
    service = InstallerService(context)

    body = {
        "disk": args.disk,
        "install_mode": args.install_mode,
        "username": args.username,
        "password": args.password,
        "hostname": args.hostname,
        "timezone": args.timezone,
        "kernel": args.kernel,
        "mok_password": args.mok_password,
        "confirm_backup": args.confirm_backup,
        "confirm_erase": args.confirm_erase,
        "confirm_current": args.confirm_current,
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
    import sys
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
