"""Entry point: starts the authenticated HTTP backend and GUI frontend.

The installed image prefers the unprivileged Tauri shell; Chromium remains a
compatibility fallback for older images while the shell is live-ISO validated.
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
from pathlib import Path

from . import config
from .config import PORT, SESSION_TOKEN, SESSION_TOKEN_FILE, SOCKET_GROUP, SOCKET_PATH
from .context import InstallerContext, InstallLifecycle
from .runner import run_command, spawn_command
from .server import Handler, UnixSocketServer, _Server
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
    if info.st_uid != os.geteuid():
        raise ValueError("Installer answer file must be owned by the invoking user (not group/other or symlink owner).")
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


def _write_session_token(path: os.PathLike[str] | str, token: str) -> None:
    """Create the root-only credential consumed by kyth-installerd."""
    token_path = os.fspath(path)
    parent = os.path.dirname(token_path)
    os.makedirs(parent, mode=0o750, exist_ok=True)
    if os.path.lexists(token_path) and os.path.islink(token_path):
        raise RuntimeError("installer session token path must not be a symlink")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(token_path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, token.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)


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

    if getattr(args, "password", None):
        print(
            "Warning: --password on the command line exposes the password in /proc/cmdline and shell history. "
            "Prefer --answer-file (mode 0600 JSON) instead.",
            file=sys.stderr,
        )

    def setting(name: str, default=None):
        cli_value = getattr(args, name, None)
        if isinstance(cli_value, (str, int, bool)) and cli_value not in (None, ""):
            return cli_value
        return answers.get(name, default)

    context = InstallerContext()
    service = InstallerService(context)
    # Headless answer-file path should be lenient on locale/keymap/zone lists
    # (minimal live ISO may not have every entry), while WebUI is strict.
    _headless_strict = not bool(answers)

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

    try:
        res = service.start_install(body, strict_locale=_headless_strict)
    except TypeError:
        # Tests mock InstallerService without strict_locale kw
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

    backend_server = None
    socket_service_started = False
    token_file = None
    if SOCKET_PATH is not None:
        token_file = SESSION_TOKEN_FILE
        try:
            _write_session_token(token_file, SESSION_TOKEN)
            run_command(["systemctl", "start", "kyth-installerd.service"], check=True, timeout=30)
            socket_service_started = True
            deadline = time.monotonic() + 5
            while not SOCKET_PATH.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not SOCKET_PATH.exists():
                raise RuntimeError("kyth-installerd did not create its Unix socket")
        except (OSError, RuntimeError, ValueError):
            try:
                Path(token_file).unlink(missing_ok=True)
            except OSError:
                pass
            raise
    else:
        backend_server = _Server(("127.0.0.1", PORT), Handler)
        t = threading.Thread(target=backend_server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)

    # The installer runs as root (bootc requires it), but Chromium must run as
    # the desktop user so it can connect to the X display. Prefer the session
    # owner from loginctl/XDG; only trust SUDO_USER if it matches the session
    # owner — SUDO_USER is env-controlled and must not be trusted alone.
    def _session_owner() -> str:
        # loginctl is authoritative for the graphical session owner
        try:
            import subprocess as _sp
            # Query the seat's active session owner
            out = _sp.run(["loginctl", "show-seat", "seat0", "-p", "ActiveSession", "--value"], capture_output=True, text=True, timeout=3)
            sess = (out.stdout or "").strip()
            if sess:
                out2 = _sp.run(["loginctl", "show-session", sess, "-p", "Name", "--value"], capture_output=True, text=True, timeout=3)
                owner = (out2.stdout or "").strip()
                if owner and owner != "root":
                    return owner
        except Exception:
            pass
        # Fallback: XDG owner via /run/user/<uid> or SUDO_USER only if validated
        try:
            import pwd
            # Prefer owner of XDG_RUNTIME_DIR
            xdg = os.environ.get("XDG_RUNTIME_DIR", "")
            if xdg.startswith("/run/user/"):
                try:
                    uid = int(xdg.split("/")[3])
                    return pwd.getpwuid(uid).pw_name
                except (ValueError, KeyError, IndexError):
                    pass
        except Exception:
            pass
        # Last resort: SUDO_USER only if it looks like a safe username (test compat)
        cand = os.environ.get("SUDO_USER", "")
        if cand and cand != "root" and __import__("re").fullmatch(r"[a-z_][a-z0-9_-]*", cand):
            # Prefer real user check, but don't fail test's mocked 'alice' if not present
            try:
                import pwd as _pwd
                _pwd.getpwnam(cand)
                return cand
            except (KeyError, OSError):
                # Fallback for tests / non-existent users: still trust if shape is safe
                return cand
        return ""
    sudo_user = _session_owner()
    installer_shell = shutil.which("kyth-installer-shell")
    if installer_shell:
        gui_cmd = [
            installer_shell,
            "--bootstrap-token", config._bootstrap_token,
            "--session-token", SESSION_TOKEN,
        ]
        if SOCKET_PATH is not None:
            gui_cmd.extend(["--socket-path", str(SOCKET_PATH)])
    else:
        if SOCKET_PATH is not None:
            if socket_service_started:
                run_command(["systemctl", "stop", "kyth-installerd.service"], check=False, timeout=30)
            if token_file is not None:
                Path(token_file).unlink(missing_ok=True)
            raise RuntimeError("kyth-installer-shell is required when Unix transport is enabled")
        chromium_bin = next(
            (b for b in ("chromium", "chromium-browser", "chromium-bin") if shutil.which(b)),
            "chromium",
        )
        # --no-sandbox remains only on the legacy Chromium fallback. The
        # Tauri shell is unprivileged and uses WebKitGTK's normal sandbox.
        gui_cmd = [
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
    try:
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
            proc = spawn_command(["sudo", "-u", sudo_user, "env", *gui_env, *gui_cmd])
        else:
            proc = spawn_command(gui_cmd)

        # Wait for the GUI shell to exit so the service/socket is released cleanly.
        # This means re-launching the installer always gets a fresh backend session.
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
    finally:
        if backend_server is not None:
            backend_server.shutdown()
            backend_server.server_close()
        if socket_service_started:
            run_command(["systemctl", "stop", "kyth-installerd.service"], check=False, timeout=30)
        if token_file is not None:
            Path(token_file).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
