"""Entry point: generates the one-time bootstrap token, starts the HTTP
server in a background thread, and launches Chromium in app/kiosk mode
pointed at it.
"""

import os
import secrets
import shutil
import subprocess
import threading
import time

from . import config
from .config import PORT
from .server import Handler, _Server


def main() -> None:
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
        proc = subprocess.Popen(["sudo", "-u", sudo_user, "env", *gui_env, *chromium_cmd])
    else:
        proc = subprocess.Popen(chromium_cmd)

    # Wait for Chromium to exit so the process and port are released cleanly.
    # This means re-launching the installer from the desktop always gets a fresh server.
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
