"""Application database lookup services for KythOS installer / exe-handler."""
from __future__ import annotations

import json
import os
import re

# Fallback default database if the external JSON file is missing or corrupted.
_DEFAULT_APP_DB: list[tuple[str, str, str, str | None]] = [
    # Microsoft Office
    ("word|winword", "Microsoft Word", "Use LibreOffice Writer — fully compatible with .docx files.", "org.libreoffice.LibreOffice"),
    ("excel", "Microsoft Excel", "Use LibreOffice Calc — reads and writes .xlsx files.", "org.libreoffice.LibreOffice"),
    ("powerpnt|powerpoint", "Microsoft PowerPoint", "Use LibreOffice Impress — reads and writes .pptx files.", "org.libreoffice.LibreOffice"),
    ("outlook", "Microsoft Outlook", "Use Betterbird for desktop email and calendar.", "eu.betterbird.Betterbird"),
    ("onenote", "Microsoft OneNote", "Access OneNote at onenote.com, or use Obsidian for local notes.", None),
    ("teams", "Microsoft Teams", "Use Teams in the browser, or pin it as a Web App via WebApp Manager.", "io.github.vikdevelop.WebApp"),
    ("onedrive", "OneDrive", "Access OneDrive through KDE's Online Accounts in System Settings.", None),
    ("visio", "Microsoft Visio", "Use diagrams.net in the browser, or install LibreOffice Draw.", "org.libreoffice.LibreOffice"),
    ("project", "Microsoft Project", "Use ProjectLibre or browser-based project tools for project plans.", None),
    # Communication
    ("discord", "Discord", "Install the native Linux Discord app.", "com.discordapp.Discord"),
    ("slack", "Slack", "Install Slack from Flathub.", "com.slack.Slack"),
    ("zoom", "Zoom", "Install Zoom from Flathub.", "us.zoom.Zoom"),
    ("skype", "Skype", "Install Skype from Flathub.", "com.skype.Skype"),
    ("signal", "Signal", "Install Signal from Flathub.", "org.signal.Signal"),
    ("telegram", "Telegram", "Install Telegram from Flathub.", "org.telegram.desktop"),
    ("whatsapp", "WhatsApp", "Pin WhatsApp Web as a desktop app via WebApp Manager.", "io.github.vikdevelop.WebApp"),
    ("messenger", "Messenger", "Use Messenger in the browser, or pin it with WebApp Manager.", "io.github.vikdevelop.WebApp"),
    # Browsers
    ("chrome|googlechrome", "Google Chrome", "Install Chrome from Flathub.", "com.google.Chrome"),
    ("firefox", "Firefox", "Firefox is available from Flathub.", "org.mozilla.firefox"),
    ("brave", "Brave", "Install Brave from Flathub.", "com.brave.Browser"),
    ("opera", "Opera", "Install Opera from Flathub.", "com.opera.Opera"),
    # Adobe Creative Cloud
    ("photoshop", "Adobe Photoshop", "Use GIMP for photo editing — it handles many Photoshop files.", "org.gimp.GIMP"),
    ("premiere", "Adobe Premiere", "Use Kdenlive or DaVinci Resolve for video editing.", "org.kde.kdenlive"),
    ("after.?e?f?fects|afterfx", "Adobe After Effects", "Use Blender for motion graphics and visual effects.", "org.blender.Blender"),
    ("audition", "Adobe Audition", "Use Audacity for audio editing.", "org.audacityteam.Audacity"),
    ("lightroom", "Adobe Lightroom", "Use Darktable for raw photo processing.", "org.darktable.Darktable"),
    ("illustrator", "Adobe Illustrator", "Use Inkscape for vector graphics.", "org.inkscape.Inkscape"),
    # Gaming launchers
    ("steam", "Steam", "Steam is already installed on KythOS.", "com.valvesoftware.Steam"),
    ("epicgames|epicinstaller", "Epic Games Launcher", "Use Heroic Games Launcher to access your Epic library.", "com.heroicgameslauncher.hgl"),
    ("galaxyclient|gog", "GOG Galaxy", "Use Heroic Games Launcher to access your GOG library.", "com.heroicgameslauncher.hgl"),
    ("battle.?net|blizzard", "Battle.net", "Run Battle.net through Lutris or Bottles.", "net.lutris.Lutris"),
    ("origin|eaapp|ea.?app", "EA App / Origin", "Use Heroic Games Launcher to access your EA library.", "com.heroicgameslauncher.hgl"),
    ("uplay|ubisoft.?connect", "Ubisoft Connect", "Use Heroic Games Launcher to access your Ubisoft library.", "com.heroicgameslauncher.hgl"),
    ("curseforge", "CurseForge", "Use Prism Launcher for Minecraft modpacks when possible.", "org.prismlauncher.PrismLauncher"),
    ("minecraft", "Minecraft Launcher", "Use Prism Launcher for Minecraft and modpacks.", "org.prismlauncher.PrismLauncher"),
    ("vortex|nexusmods?", "Vortex / Nexus Mods", "Use SteamTinkerLaunch for per-game MO2, or Bottles for standalone mod tools.", None),
    ("modorganizer|mo2", "Mod Organizer 2", "Install MO2 per game through SteamTinkerLaunch, or isolate it in Bottles.", None),
    # Productivity / tools
    ("notepad\\+\\+|npp\\b", "Notepad++", "Use Kate (already installed) or VS Code for text editing.", None),
    ("code|vscode|visual.?studio.?code", "Visual Studio Code", "VS Code is available from the app menu or Kyth Pulse.", None),
    ("visual.?studio(?!.*code)", "Visual Studio", "Use VS Code, JetBrains Toolbox, or a Windows VM for full Visual Studio projects.", None),
    ("putty", "PuTTY", "Use Konsole with ssh, or search Flathub if you specifically want PuTTY.", None),
    ("winscp", "WinSCP", "Use Dolphin's sftp:// support or FileZilla from Flathub.", "org.filezillaproject.Filezilla"),
    ("7z|7-?zip", "7-Zip", "p7zip is already installed — right-click any archive in Dolphin.", None),
    ("winrar", "WinRAR", "p7zip is already installed — right-click any archive in Dolphin.", None),
    ("obs.?studio|obs64", "OBS Studio", "Install OBS Studio from Flathub.", "com.obsproject.Studio"),
    ("vlc", "VLC", "Install VLC from Flathub.", "org.videolan.VLC"),
    ("spotify", "Spotify", "Install Spotify from Flathub.", "com.spotify.Client"),
    ("bitwarden", "Bitwarden", "Install Bitwarden from Flathub.", "com.bitwarden.desktop"),
    ("1password", "1Password", "Install 1Password from Flathub.", "com.onepassword.OnePassword"),
    ("obsidian", "Obsidian", "Install Obsidian from Flathub.", "md.obsidian.Obsidian"),
    ("notion", "Notion", "Use Notion in the browser, or pin it as a Web App.", "io.github.vikdevelop.WebApp"),
    ("qbittorrent", "qBittorrent", "Install qBittorrent from Flathub.", "org.qbittorrent.qBittorrent"),
    ("plex", "Plex", "Install Plex Desktop from Flathub.", "tv.plex.PlexDesktop"),
    ("calibre", "Calibre", "Install Calibre from Flathub.", "com.calibre_ebook.calibre"),
    ("audacity", "Audacity", "Install Audacity from Flathub.", "org.audacityteam.Audacity"),
    ("resolve|davinci", "DaVinci Resolve", "Install DaVinci Resolve via Pulse > Apps.", None),
    ("gimp", "GIMP", "Install GIMP from Flathub.", "org.gimp.GIMP"),
    ("inkscape", "Inkscape", "Install Inkscape from Flathub.", "org.inkscape.Inkscape"),
    ("blender", "Blender", "Install Blender from Flathub.", "org.blender.Blender"),
    # Hardware utilities
    ("logi|logitech|ghub|g.?hub", "Logitech G HUB", "Use Piper or OpenRGB when your device is supported.", "org.freedesktop.Piper"),
    ("razer|synapse", "Razer Synapse", "Use OpenRGB for lighting and OpenRazer-supported tools where available.", "org.openrgb.OpenRGB"),
    ("elgato|stream.?deck", "Elgato / Stream Deck", "Use OpenDeck from Pulse > Apps for Stream Deck workflows.", None),
    ("voicemeeter|go.?xlr", "Audio routing utility", "Use PipeWire audio routing tools; check System Settings > Audio first.", None),
]

_DB_PATH = "/usr/share/kyth/exe-handler-apps.json"


def load_app_db(path: str = _DB_PATH) -> list[tuple[str, str, str, str | None]]:
    """Load the applications database from a JSON file, falling back to defaults."""
    if not os.path.exists(path):
        return _DEFAULT_APP_DB
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            res = []
            for item in data:
                if len(item) == 4:
                    res.append((item[0], item[1], item[2], item[3]))
            return res
    except (OSError, json.JSONDecodeError, ValueError, UnicodeError, AttributeError):
        return _DEFAULT_APP_DB


def suggest_app(stem: str, path: str = _DB_PATH) -> tuple[str | None, str | None, str | None]:
    """Look up stem in the application database and return (display_name, suggestion, flathub_id)."""
    db = load_app_db(path)
    for pattern, app_name, suggestion, flatpak_id in db:
        if re.search(pattern, stem, re.IGNORECASE):
            return app_name, suggestion, flatpak_id
    return None, None, None
