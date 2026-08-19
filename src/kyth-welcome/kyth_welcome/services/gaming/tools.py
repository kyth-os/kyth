"""Installed gaming tooling checks, tool catalog, and command builders."""
from __future__ import annotations

import glob
import os
import shutil

from ..process import run_command


def _mangohud_installed() -> bool:
    return shutil.which("mangohud") is not None
 # _mangohud_installed

def _gamescope_installed() -> bool:
    return shutil.which("gamescope") is not None
 # _gamescope_installed

def _vkbasalt_installed() -> bool:
    return any(
        os.path.exists(p) for p in (
            "/usr/lib64/vkbasalt/libvkbasalt.so",
            "/usr/lib/vkbasalt/libvkbasalt.so",
            "/usr/lib64/libvkbasalt.so",
            "/usr/lib/libvkbasalt.so",
        )
    )
 # _vkbasalt_installed

def _proton_cachyos_version() -> str | None:
    """Return the latest installed Proton-CachyOS directory name, or None."""
    found: list[str] = []
    for base in (
        "/usr/share/steam/compatibilitytools.d",
        "/var/lib/kyth/proton-cachyos",
    ):
        try:
            found.extend(e for e in os.listdir(base) if e.startswith("proton-cachyos"))
        except OSError:
            pass
    return sorted(found)[-1] if found else None
 # _proton_cachyos_version

def _compat_tool_version(prefix: str) -> str | None:
    """Return the latest installed Steam compatibility tool matching prefix."""
    bases = [
        "/usr/share/steam/compatibilitytools.d",
        "/var/lib/kyth/proton-cachyos",
        os.path.expanduser("~/.steam/root/compatibilitytools.d"),
        os.path.expanduser("~/.steam/steam/compatibilitytools.d"),
        os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    ]
    found: list[str] = []
    for base in bases:
        try:
            found.extend(e for e in os.listdir(base) if e.lower().startswith(prefix.lower()))
        except OSError:
            pass
    return sorted(found)[-1] if found else None
 # _compat_tool_version

def _ntsync_state() -> tuple[str, str]:
    if os.path.exists("/dev/ntsync"):
        return "ok", "/dev/ntsync is present."
    module_probe = run_command(["modprobe", "-n", "ntsync"], timeout=5)
    if module_probe is not None and module_probe.returncode == 0:
        return "warn", "ntsync module exists but /dev/ntsync is not present yet."
    return "warn", "ntsync device not detected; Proton will fall back to fsync/esync."
 # _ntsync_state

def _vulkan_state() -> tuple[str, str]:
    if shutil.which("vulkaninfo"):
        result = run_command(["vulkaninfo", "--summary"], timeout=12)
        if result is not None and result.returncode == 0:
            gpus = [
                line.split("=", 1)[1].strip()
                for line in result.stdout.splitlines()
                if "deviceName" in line and "=" in line
            ]
            return "ok", "Vulkan ready" + (f": {', '.join(gpus[:2])}" if gpus else ".")
        return "err", "vulkaninfo is installed but Vulkan probing failed."
    render_nodes = glob.glob("/dev/dri/renderD*")
    if render_nodes:
        return "warn", "Render device exists, but vulkaninfo is not installed for a full check."
    return "err", "No Vulkan render device detected."
 # _vulkan_state


# Static gaming tool definitions used by GamingPage.
GAMING_TOOLS = [
    {
        "flatpak": "com.valvesoftware.Steam",
        "name": "Steam",
        "desc": "Valve's gaming platform plus PC games through Proton.",
        "ujust": "install-steam",
        "launch": ["flatpak", "run", "com.valvesoftware.Steam"],
    },
    {
        "flatpak": "net.lutris.Lutris",
        "name": "Lutris",
        "desc": "Battle.net, EA App, Ubisoft Connect, and other compatibility launchers.",
        "ujust": "install-lutris",
        "launch": ["flatpak", "run", "net.lutris.Lutris"],
    },
    {
        "flatpak": "com.heroicgameslauncher.hgl",
        "name": "Heroic Games Launcher",
        "desc": "Epic Games, GOG, and Amazon Games library in one place.",
        "ujust": "install-heroic",
        "launch": ["flatpak", "run", "com.heroicgameslauncher.hgl"],
    },
    {
        "flatpak": "com.usebottles.bottles",
        "name": "Bottles",
        "desc": "Best for running standalone .exe and .msi installers in isolated app environments.",
        "ujust": "install-bottles",
        "launch": ["flatpak", "run", "com.usebottles.bottles"],
    },
    {
        "flatpak": "com.github.mtkennerly.ludusavi",
        "name": "Ludusavi",
        "desc": "Back up and restore game saves across Steam, Heroic, Lutris, and PC migrations.",
        "ujust": "install-ludusavi",
        "launch": ["flatpak", "run", "com.github.mtkennerly.ludusavi"],
    },
    {
        "flatpak": "org.prismlauncher.PrismLauncher",
        "name": "Prism Launcher",
        "desc": "Minecraft launcher with modpacks, multiple instances, and Java version control.",
        "ujust": "install-prismlauncher",
        "launch": ["flatpak", "run", "org.prismlauncher.PrismLauncher"],
    },
    {
        "flatpak": "io.itch.itch",
        "name": "Itch.io",
        "desc": "Indie game store and library manager.",
        "ujust": "install-itch",
        "launch": ["flatpak", "run", "io.itch.itch"],
    },
    {
        "flatpak": "org.libretro.RetroArch",
        "name": "RetroArch",
        "desc": "Multi-system emulator frontend (NES, SNES, PS1, N64, …).",
        "ujust": "install-retroarch",
        "launch": ["flatpak", "run", "org.libretro.RetroArch"],
    },
    {
        "flatpak": "org.freedesktop.Piper",
        "name": "Piper",
        "desc": "GUI for configuring gaming mice — DPI, buttons, and LEDs.",
        "ujust": "install-piper",
        "launch": ["flatpak", "run", "org.freedesktop.Piper"],
    },
    {
        "flatpak": "org.openrgb.OpenRGB",
        "name": "OpenRGB",
        "desc": "Unified RGB lighting control for motherboards, RAM, GPUs, and peripherals. Pre-installed — RGB profiles are applied automatically at login.",
        "ujust": "install-openrgb",
        "launch": ["openrgb"],
    },
    {
        "flatpak": "io.github.benjamimgois.goverlay",
        "name": "GOverlay",
        "desc": "Graphical tuning for MangoHud and vkBasalt overlays — adjust metrics, colors, and presets without editing config files.",
        "ujust": "install-goverlay",
        "launch": ["flatpak", "run", "io.github.benjamimgois.goverlay"],
    },
    {
        "flatpak": "io.github.radiolamp.mangojuice",
        "name": "MangoJuice",
        "desc": "Lightweight MangoHud configuration editor for overlay layout and metrics.",
        "ujust": "install-mangojuice",
        "launch": ["flatpak", "run", "io.github.radiolamp.mangojuice"],
    },
    {
        "flatpak": "com.dec05eba.gpu_screen_recorder",
        "name": "GPU Screen Recorder",
        "desc": "Near-zero overhead gameplay capture and instant replay using AMD/NVIDIA GPU encoding.",
        "ujust": "install-gpu-screen-recorder",
        "launch": ["flatpak", "run", "com.dec05eba.gpu_screen_recorder"],
    },
    {
        "flatpak": "dev.vencord.Vesktop",
        "name": "Vesktop",
        "desc": "Discord client with native Wayland support, better screenshare, and no telemetry.",
        "ujust": "install-vesktop",
        "launch": ["flatpak", "run", "dev.vencord.Vesktop"],
    },
]

# Gaming action command builders extracted from GamingPage.
def discord_screenshare_fix_command():
    return [
        "bash", "-c",
        "flatpak override --user com.discordapp.Discord "
        "--env=ELECTRON_OZONE_PLATFORM_HINT=auto "
        "--socket=wayland --socket=fallback-x11 --device=dri "
        "--talk-name=org.freedesktop.portal.Desktop "
        "--talk-name=org.kde.StatusNotifierWatcher",
    ]

def obs_pipewire_fix_command():
    return [
        "bash", "-c",
        "flatpak override --user com.obsproject.Studio "
        "--socket=wayland --socket=pulseaudio --device=dri "
        "--talk-name=org.freedesktop.portal.Desktop",
    ]

# Parameterized gaming action command builders extracted from GamingPage.
def opticscaler_deploy_command(game_dir):
    return ["ujust", "deploy-opticscaler", game_dir]

def heroic_epic_launcher_command():
    return ["flatpak", "run", "com.heroicgameslauncher.hgl"]

def lutris_installer_command(lutris_target):
    return ["flatpak", "run", "net.lutris.Lutris", lutris_target]

# Scheduler command builder extracted from GamingPage.
def scx_scheduler_command(scheduler):
    if scheduler == "stop":
        return ["kyth-scx", "stop"]
    return ["kyth-scx", "set", scheduler]

# Page-level gaming helpers extracted from GamingPage.
def command_details(cmd: list[str], result=None, exc: Exception | None = None) -> str:
    lines = ["Command:", "  " + " ".join(cmd)]
    if exc is not None:
        lines.extend(["", "Error:", str(exc)])
        return "\n".join(lines)
    if result is None:
        return "\n".join(lines)
    lines.extend(["", f"Exit code: {result.returncode}"])

    def _as_text(value) -> str:
        if not value:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip()
        return str(value).strip()

    stdout = _as_text(getattr(result, "stdout", None))
    stderr = _as_text(getattr(result, "stderr", None))
    if stdout:
        lines.extend(["", "stdout:", stdout])
    if stderr:
        lines.extend(["", "stderr:", stderr])
    return "\n".join(lines)

