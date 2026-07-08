import glob
import os
import re
import shlex
import shutil
from urllib.parse import urlsplit

from ..qt import Signal, QPushButton
from ..core_base import (
    Worker, _probe_cached, _run_command, _finish_worker,
    _IS_LIVE, _command_stdout
)

_CHROMIUM_APP_ID_PREFIX = {
    "chromium-browser": "chromium",
    "chromium": "chromium",
    "org.chromium.Chromium": "chromium",
    "brave-browser": "brave",
    "com.brave.Browser": "brave",
    "microsoft-edge": "msedge",
    "com.microsoft.Edge": "msedge",
    "google-chrome": "chrome",
    "com.google.Chrome": "chrome",
}

_DEFAULT_FIRST_RUN_APPS = (
    ("com.valvesoftware.Steam", "Steam"),
    ("net.lutris.Lutris", "Lutris"),
    ("com.heroicgameslauncher.hgl", "Heroic"),
    ("com.usebottles.bottles", "Bottles"),
    ("com.github.mtkennerly.ludusavi", "Ludusavi"),
    ("com.dec05eba.gpu_screen_recorder", "GPU Screen Recorder"),
    ("io.github.benjamimgois.goverlay", "GOverlay"),
    ("dev.vencord.Vesktop", "Vesktop"),
)

_FLATPAK_CACHE_TTL = 10.0

def _installed_flatpak_ids() -> frozenset | None:
    """One `flatpak list` snapshot instead of a `flatpak info` spawn per app.
    Returns None when the listing itself fails (flatpak missing/broken)."""
    def fetch() -> frozenset | None:
        result = _run_command(["flatpak", "list", "--app", "--columns=application"], timeout=10)
        if result is None or result.returncode != 0:
            return None
        return frozenset(ln.strip() for ln in result.stdout.splitlines() if ln.strip())

    return _probe_cached("flatpak-apps", _FLATPAK_CACHE_TTL, fetch)
 # _installed_flatpak_ids

def _is_flatpak_installed(app_id: str) -> bool:
    ids = _installed_flatpak_ids()
    if ids is not None:
        return app_id in ids
    result = _run_command(["flatpak", "info", app_id], timeout=8)
    return result is not None and result.returncode == 0
 # _is_flatpak_installed

def _chromium_app_window_id(browser: str, url: str) -> str:
    """Wayland app id / X11 WM_CLASS a Chromium-family browser gives a window
    opened with --app=url: <prefix>-<host>_<path with / as _>-<profile>.
    --class/--name are ignored on Wayland, so StartupWMClass must carry this
    generated id for the task bar to match the window to its .desktop file."""
    parts = urlsplit(url)
    name = f"{parts.hostname or ''}_{parts.path or '/'}".replace("/", "_")
    return f"{_CHROMIUM_APP_ID_PREFIX[browser]}-{name}-Default"
 # _chromium_app_window_id

def _chromium_app_window_cmd(url: str) -> tuple[list[str], str] | None:
    """Build a command that opens url as a dedicated app window, plus the
    window class the browser will assign to it, or None.

    KythOS ships Brave as a Flatpak, not a native chromium-browser binary, so
    native binaries are only found on systems where the user installed one.
    """
    args = [f"--app={url}"]
    for binary in ("chromium-browser", "chromium", "brave-browser",
                   "microsoft-edge", "google-chrome"):
        if shutil.which(binary):
            return [binary, *args], _chromium_app_window_id(binary, url)
    for app_id in ("com.brave.Browser", "org.chromium.Chromium",
                   "com.microsoft.Edge", "com.google.Chrome"):
        if _is_flatpak_installed(app_id):
            return (["flatpak", "run", app_id, *args],
                    _chromium_app_window_id(app_id, url))
    return None
 # _chromium_app_window_cmd

def _install_flatpak_inline(owner: object, btn: QPushButton, app_id: str, name: str,
                            extra_cmd: str = "", done_cb=None) -> None:
    """Install a Flathub app on a Worker thread, driving the button state.

    In-app replacement for terminal-popping installs: the button itself shows
    progress and outcome, and polkit/askpass handles any elevation. extra_cmd
    is shell appended after a successful install (e.g. a flatpak override).
    One worker per app id, kept on `owner` so concurrent clicks are ignored.
    """
    attr = "_inline_install_" + re.sub(r"\W", "_", app_id)
    existing = getattr(owner, attr, None)
    if existing is not None and existing.isRunning():
        return
    orig = btn.text()
    btn.setEnabled(False)
    btn.setText("Installing…")
    cmd = (
        "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
        f" && flatpak install -y --or-update flathub {shlex.quote(app_id)}"
    )
    if extra_cmd:
        cmd += f" && {extra_cmd}"
    worker = Worker(["bash", "-c", cmd])

    def _done(code: int):
        _finish_worker(owner, attr=attr)
        if code == 0:
            btn.setText("✓ Installed")
            btn.setToolTip(f"{name} is installed. Find it in the app launcher.")
        else:
            btn.setText(orig)
            btn.setEnabled(True)
            btn.setToolTip(f"Install failed (exit {code}). Check your network connection and try again.")
        if done_cb:
            done_cb(code)

    worker.done.connect(_done)
    setattr(owner, attr, worker)
    worker.start()
 # _install_flatpak_inline

def _first_run_app_setup_state() -> tuple[str, str, list[str]]:
    if _IS_LIVE:
        return (
            "live",
            "Live sessions include the KythOS tools and launcher defaults. Install to this PC for persistent app setup.",
            [],
        )
    missing = [name for app_id, name in _DEFAULT_FIRST_RUN_APPS if not _is_flatpak_installed(app_id)]
    done = os.path.exists("/var/lib/kyth/default-flatpaks-v8-done")
    if not missing:
        return "ready", "Steam, game launchers, Bottles, save backup, and gaming tools are ready.", []

    status_path = os.path.expanduser("~/.local/share/kyth/first-run-apps.status")
    status: dict[str, str] = {}
    if os.path.exists(status_path):
        try:
            with open(status_path, encoding="utf-8") as fh:
                for line in fh:
                    if "=" in line:
                        key, value = line.rstrip("\n").split("=", 1)
                        status[key] = shlex.split(value)[0] if value else ""
        except Exception:
            status = {}

    service = _run_command(["systemctl", "is-active", "kyth-default-flatpaks.service"], timeout=3)
    service_state = service.stdout.strip() if service and service.stdout.strip() else ""
    if service_state in {"active", "activating"} or status.get("state") == "setting_up":
        return (
            "setting_up",
            f"KythOS is finishing app setup in the background. Pending: {', '.join(missing)}.",
            missing,
        )
    if service_state == "failed" or status.get("state") == "failed":
        return (
            "failed",
            f"Default app setup needs a retry. Pending: {', '.join(missing)}.",
            missing,
        )
    if done:
        return (
            "partial",
            f"Setup finished, but these apps are still missing: {', '.join(missing)}.",
            missing,
        )
    return (
        "pending",
        f"Connect to the network and let KythOS finish first-run app setup. Pending: {', '.join(missing)}.",
        missing,
    )
 # _first_run_app_setup_state

def _davinci_flatpak_app_id() -> str | None:
    for app_id in (
        "com.blackmagic.Resolve",
        "com.blackmagic.ResolveStudio",
        "com.blackmagicdesign.resolve",
    ):
        if _is_flatpak_installed(app_id):
            return app_id
    return None
 # _davinci_flatpak_app_id

def _davinci_download_dir() -> str:
    candidate = _command_stdout(["xdg-user-dir", "DOWNLOAD"])
    if candidate:
        candidate = os.path.expanduser(candidate)
        if os.path.isdir(candidate):
            return candidate
    return os.path.expanduser("~/Downloads")
 # _davinci_download_dir

def _davinci_zip_candidates() -> list[str]:
    roots: list[str] = []
    for candidate in (_davinci_download_dir(), os.path.expanduser("~/Downloads")):
        expanded = os.path.abspath(os.path.expanduser(candidate))
        if os.path.isdir(expanded) and expanded not in roots:
            roots.append(expanded)

    patterns = (
        "DaVinci_Resolve*_Linux.zip",
        "DaVinci_Resolve_Studio*_Linux.zip",
        "*DaVinci*Resolve*Linux*.zip",
    )
    matches: dict[str, float] = {}
    for root in roots:
        for pattern in patterns:
            for base in (root, os.path.join(root, "*")):
                for path in glob.glob(os.path.join(base, pattern)):
                    if os.path.isfile(path):
                        try:
                            matches[path] = os.path.getmtime(path)
                        except OSError:
                            matches[path] = 0

    return sorted(matches, key=lambda item: (matches[item], item.lower()), reverse=True)
 # _davinci_zip_candidates
