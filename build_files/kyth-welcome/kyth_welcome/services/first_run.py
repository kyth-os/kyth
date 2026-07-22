"""First-run application setup state."""

from __future__ import annotations

import os
import shlex

from .flatpak import is_installed
from .process import _is_live_session, _run_command

DEFAULT_FIRST_RUN_APPS = (
    ("com.valvesoftware.Steam", "Steam"),
    ("net.lutris.Lutris", "Lutris"),
    ("com.heroicgameslauncher.hgl", "Heroic"),
    ("com.usebottles.bottles", "Bottles"),
    ("com.github.mtkennerly.ludusavi", "Ludusavi"),
    ("com.dec05eba.gpu_screen_recorder", "GPU Screen Recorder"),
    ("io.github.benjamimgois.goverlay", "GOverlay"),
    ("com.brave.Browser", "Brave"),
)


def app_setup_state() -> tuple[str, str, list[str]]:
    if _is_live_session():
        return (
            "live",
            "Live sessions include the KythOS tools and launcher defaults. Install to this PC for persistent app setup.",
            [],
        )
    missing = [name for app_id, name in DEFAULT_FIRST_RUN_APPS if not is_installed(app_id)]
    done = os.path.exists("/var/lib/kyth/default-flatpaks-v10-done")
    if not missing:
        return (
            "ready",
            "Steam, game launchers, Bottles, save backup, and gaming tools are ready.",
            [],
        )

    status_path = os.path.expanduser("~/.local/share/kyth/first-run-apps.status")
    status: dict[str, str] = {}
    if os.path.exists(status_path):
        try:
            with open(status_path, encoding="utf-8") as handle:
                for line in handle:
                    if "=" in line:
                        key, value = line.rstrip("\n").split("=", 1)
                        status[key] = shlex.split(value)[0] if value else ""
        except (OSError, ValueError):
            status = {}

    service = _run_command(
        ["systemctl", "is-active", "kyth-default-flatpaks.service"], timeout=3
    )
    service_state = service.stdout.strip() if service and service.stdout.strip() else ""
    pending = ", ".join(missing)
    if service_state in {"active", "activating"} or status.get("state") == "setting_up":
        return "setting_up", f"KythOS is finishing app setup in the background. Pending: {pending}.", missing
    if service_state == "failed" or status.get("state") == "failed":
        return "failed", f"Default app setup needs a retry. Pending: {pending}.", missing
    if done:
        return "partial", f"Setup finished, but these apps are still missing: {pending}.", missing
    return "pending", f"Connect to the network and let KythOS finish first-run app setup. Pending: {pending}.", missing


_first_run_app_setup_state = app_setup_state
