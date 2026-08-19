"""Commands and window identities for browser-hosted web applications."""

from __future__ import annotations

import shutil
from urllib.parse import urlsplit

from .flatpak import is_installed

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


def chromium_app_window_id(browser: str, url: str) -> str:
    parts = urlsplit(url)
    name = f"{parts.hostname or ''}_{parts.path or '/'}".replace("/", "_")
    return f"{_CHROMIUM_APP_ID_PREFIX[browser]}-{name}-Default"


def chromium_app_window_command(url: str) -> tuple[list[str], str] | None:
    args = [f"--app={url}"]
    for binary in (
        "chromium-browser",
        "chromium",
        "brave-browser",
        "microsoft-edge",
        "google-chrome",
    ):
        if shutil.which(binary):
            return [binary, *args], chromium_app_window_id(binary, url)
    for app_id in (
        "com.brave.Browser",
        "org.chromium.Chromium",
        "com.microsoft.Edge",
        "com.google.Chrome",
    ):
        if is_installed(app_id):
            return (
                ["flatpak", "run", app_id, *args],
                chromium_app_window_id(app_id, url),
            )
    if shutil.which("firefox"):
        return ["firefox", "--new-window", url], "firefox"
    if is_installed("org.mozilla.firefox"):
        return (
            ["flatpak", "run", "org.mozilla.firefox", "--new-window", url],
            "org.mozilla.firefox",
        )
    return None


_chromium_app_window_id = chromium_app_window_id
_chromium_app_window_cmd = chromium_app_window_command
