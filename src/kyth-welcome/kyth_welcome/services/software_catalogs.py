"""Static App Store catalogs (starter packs, creator tools, familiar apps).

Kept out of page_software.py so the page shell stays orchestration-only and
catalog edits do not churn the lazy-compose shell module.
"""
from __future__ import annotations

# Each app tuple is (flatpak_id, label, selected_by_default, description).
# The description is a per-APP fallback shown on store cards/tooltips when
# live Flathub metadata hasn't been fetched yet — it must not be the
# pack-level "desc" below (that's a one-line summary of the whole pack,
# shown once on the pack's own panel; reusing it per-app previously made
# every unrelated app in a pack display identical placeholder text).
STARTER_PACKS = [
    {
        "name": "Gaming",
        "desc": "Steam, Epic/GOG, compatibility launchers, saves, and standalone .exe support.",
        "apps": [
            ("com.valvesoftware.Steam", "Steam", True, "Digital game store and library for Windows and Linux-native titles."),
            ("com.heroicgameslauncher.hgl", "Heroic Games Launcher", True, "Launcher for Epic Games Store and GOG libraries."),
            ("net.lutris.Lutris", "Lutris", True, "Open-source game manager for Windows, GOG, Amazon, and emulated titles."),
            ("com.usebottles.bottles", "Bottles", True, "Run Windows software and games in isolated, sandboxed prefixes."),
            ("com.github.mtkennerly.ludusavi", "Ludusavi", True, "Back up and restore PC game save files across hundreds of titles."),
            ("net.davidotek.pupgui2", "ProtonUp-Qt", True, "Install and manage custom Proton and Wine-GE compatibility builds."),
        ],
    },
    {
        "name": "Creator",
        "desc": "Streaming, editing, audio, images, and 3D creation.",
        "apps": [
            ("com.obsproject.Studio", "OBS Studio", True, "Screen recording and live streaming with obs-vkcapture-ready game capture."),
            ("org.kde.kdenlive", "Kdenlive", True, "Open-source non-linear video editor. Multi-track timeline, effects, and transitions."),
            ("org.audacityteam.Audacity", "Audacity", True, "Multi-track audio editor and recorder. Noise reduction, EQ, compression, and export."),
            ("org.gimp.GIMP", "GIMP", True, "GNU Image Manipulation Program. Photo editing, compositing, and graphic design."),
            ("org.inkscape.Inkscape", "Inkscape", True, "Vector graphics editor for illustrations, logos, and diagrams."),
            ("org.blender.Blender", "Blender", True, "3D modeling, animation, and rendering suite."),
        ],
    },
    {
        "name": "Everyday",
        "desc": "Browser, chat, media, passwords, app management, and local file sharing.",
        "apps": [
            ("com.brave.Browser", "Brave Browser", True, "Privacy-focused web browser with built-in ad and tracker blocking."),
            ("com.discordapp.Discord", "Discord", True, "Voice, video, and text chat for communities and friends."),
            ("org.videolan.VLC", "VLC", True, "Plays virtually any video or audio file format."),
            ("com.spotify.Client", "Spotify", True, "Stream music, podcasts, and playlists."),
            ("com.bitwarden.desktop", "Bitwarden", False, "Open-source password manager and secure vault."),
            ("org.localsend.localsend_app", "LocalSend", True, "Send files to nearby devices over the local network — no cloud required."),
            ("io.github.vikdevelop.WebApp", "WebApp Manager", True, "Turn any website into a standalone, launchable desktop app."),
            ("com.github.tchx84.Flatseal", "Flatseal", True, "Review and adjust Flatpak app permissions — filesystem, network, and devices."),
        ],
    },
]

CR_TOOLS = [
    {
        "flatpak": "com.obsproject.Studio",
        "name": "OBS Studio",
        "desc": "Screen recording and live streaming with obs-vkcapture-ready game capture.",
        "ujust": "install-obs",
        "launch": ["flatpak", "run", "com.obsproject.Studio"],
    },
    {
        "flatpak": "org.kde.kdenlive",
        "name": "Kdenlive",
        "desc": "Open-source non-linear video editor. Multi-track timeline, effects, and transitions.",
        "launch": ["flatpak", "run", "org.kde.kdenlive"],
    },
    {
        "flatpak": "org.audacityteam.Audacity",
        "name": "Audacity",
        "desc": "Multi-track audio editor and recorder. Noise reduction, EQ, compression, and export.",
        "launch": ["flatpak", "run", "org.audacityteam.Audacity"],
    },
    {
        "flatpak": "org.gimp.GIMP",
        "name": "GIMP",
        "desc": "GNU Image Manipulation Program. Photo editing, compositing, and graphic design.",
        "launch": ["flatpak", "run", "org.gimp.GIMP"],
    },
    {
        "flatpak": "me.amankhanna.opendeck",
        "name": "OpenDeck",
        "desc": "Stream Deck controller for Linux. Supports original Elgato plugins via Wine.",
        "launch": ["flatpak", "run", "me.amankhanna.opendeck"],
    },
]

SEC_BOX_NAME = "kali"
SEC_BOX_IMAGE = "docker.io/kalilinux/kali-rolling"
SEC_HOST_TOOLS = [
    {
        "flatpak": "org.wireshark.Wireshark",
        "name": "Wireshark",
        "desc": "Network packet capture and protocol analyser. Live capture and deep inspection of hundreds of protocols.",
        "launch": ["flatpak", "run", "org.wireshark.Wireshark"],
    },
    {
        "flatpak": "com.portswigger.BurpSuite",
        "name": "Burp Suite Community",
        "desc": "Web application security testing — proxy, scanner, intruder, repeater, and decoder.",
        "launch": ["flatpak", "run", "com.portswigger.BurpSuite"],
    },
]

CURATED_APPIMAGES = [
    {
        "name": "Obsidian",
        "desc": "Markdown note-taking and knowledge base with graph view.",
        "url": "https://obsidian.md/download",
    },
    {
        "name": "Cursor",
        "desc": "AI-first code editor built on VS Code.",
        "url": "https://cursor.sh",
    },
    {
        "name": "Zed",
        "desc": "High-performance multi-player code editor.",
        "url": "https://zed.dev/download",
    },
    {
        "name": "Beeper",
        "desc": "Universal messenger — iMessage, WhatsApp, Telegram, Signal, and more.",
        "url": "https://www.beeper.com/download",
    },
    {
        "name": "Joplin",
        "desc": "Open-source Markdown note-taking with end-to-end encryption.",
        "url": "https://joplinapp.org/download/",
    },
    {
        "name": "Figma for Linux",
        "desc": "Collaborative UI design tool (unofficial Linux wrapper).",
        "url": "https://github.com/Figma-Linux/figma-linux/releases",
    },
    {
        "name": "AppImageHub",
        "desc": "Browse the full community catalog of AppImages.",
        "url": "https://www.appimagehub.com",
    },
]

FAMILIAR_APPS = [
    # Productivity
    ("Microsoft Office", "Use LibreOffice locally, or pin Microsoft 365 as a Web App.", "org.libreoffice.LibreOffice"),
    ("Word / Excel / PowerPoint", "LibreOffice Writer, Calc, and Impress are drop-in replacements. Install below.", "org.libreoffice.LibreOffice"),
    ("Outlook", "Use Betterbird for mail/calendar, or pin Outlook Web as a Web App.", "eu.betterbird.Betterbird"),
    ("Teams", "Use Teams in the browser and pin it with WebApp Manager.", "io.github.vikdevelop.WebApp"),
    ("OneDrive", "Use the OneDrive web app, KDE Online Accounts, or the Cloud Storage page for sync-style workflows.", ""),
    ("Zoom", "Install the Zoom Flatpak — full video calls, screen share, and breakout rooms.", "us.zoom.Zoom"),
    ("Slack", "Install Slack from Flatpak.", "com.slack.Slack"),
    ("Notepad++", "Use Kate (already installed — find it in the app menu) or VS Code.", ""),
    ("Notepad", "Kate is already installed and handles plain text, code, and tabs.", ""),
    # Browsers
    ("Chrome", "Use Brave Browser (already installed) or install Chromium from Flatpak.", "com.brave.Browser"),
    ("Firefox", "Install Firefox from Flatpak — all extensions and sync work.", "org.mozilla.firefox"),
    ("Edge", "Pin any web app with WebApp Manager, or use Brave Browser.", "com.brave.Browser"),
    # Creative
    ("Photoshop", "Use GIMP for raster editing; Krita is excellent for painting.", "org.gimp.GIMP"),
    ("Adobe Creative Cloud", "Most Adobe desktop apps do not run cleanly here. Use web apps, native alternatives, or keep a VM or dual boot for those projects.", ""),
    ("Paint.NET / MS Paint", "Use GIMP for editing or Krita for painting. Kolourpaint is simpler.", "org.gimp.GIMP"),
    ("Illustrator", "Use Inkscape for vector graphics.", "org.inkscape.Inkscape"),
    ("Premiere", "Use Kdenlive or install DaVinci Resolve from Creator tools.", "org.kde.kdenlive"),
    ("After Effects", "Use Kdenlive or Blender's compositor for motion graphics.", "org.kde.kdenlive"),
    # Gaming
    ("Game Pass / Xbox app", "Use Xbox Cloud Gaming in the browser. Local PC Game Pass installs still need the original platform.", "com.brave.Browser"),
    ("Battle.net", "Use Lutris for Battle.net and Blizzard games.", "net.lutris.Lutris"),
    ("Epic Games", "Use Heroic Games Launcher for Epic, GOG, and Amazon libraries.", "com.heroicgameslauncher.hgl"),
    ("Vortex / MO2", "Use SteamTinkerLaunch per game, or Bottles for standalone mod tools.", ""),
    # File & archive tools
    ("7-Zip / WinRAR", "Ark is already installed — right-click any archive in Dolphin to extract.", ""),
    ("WinSCP", "Use Dolphin's built-in sftp:// support, or install FileZilla.", "org.filezillaproject.Filezilla"),
    # Remote & networking
    ("AnyDesk", "Install AnyDesk from Flatpak for remote desktop.", "com.anydesk.Anydesk"),
    ("TeamViewer / Quick Assist", "Use RustDesk for remote help with a temporary ID and password.", "com.rustdesk.RustDesk"),
    ("Nearby Share / Quick Share", "Use LocalSend across PCs and phones, or KDE Connect for paired devices.", "org.localsend.localsend_app"),
    ("PuTTY", "Use Konsole with built-in SSH: open a terminal and type ssh user@host.", ""),
    # System tools
    ("Task Manager", "Mission Center looks and works like a familiar task manager. Installing it here also moves Ctrl+Shift+Esc to open it. (System Monitor is the built-in alternative.)", "io.missioncenter.MissionCenter"),
    ("VirtualBox", "Use GNOME Boxes from Flatpak — simpler VM setup for most use cases.", "org.gnome.Boxes"),
    ("CCleaner", "Not needed — KythOS is immutable and self-maintaining. Run 'ujust kyth-upgrade' to update.", ""),
    # Communication & social
    ("Discord", "Install Discord from Flatpak.", "com.discordapp.Discord"),
    ("Signal", "Install Signal from Flatpak.", "org.signal.Signal"),
    ("Telegram", "Install Telegram from Flatpak.", "org.telegram.desktop"),
    ("WhatsApp", "Pin WhatsApp Web as an app with WebApp Manager.", "io.github.vikdevelop.WebApp"),
    # Media
    ("Spotify", "Install Spotify from Flatpak.", "com.spotify.Client"),
    ("VLC", "Install VLC from Flatpak — plays everything.", "org.videolan.VLC"),
    ("iTunes", "Use Spotify or a local music player like Lollypop or Elisa.", "com.spotify.Client"),
    # Hardware / peripherals
    ("Logitech G HUB", "Use Piper or OpenRGB when your device is supported; some cloud profiles and onboard memory flows still need the original platform.", "org.freedesktop.Piper"),
    ("Corsair iCUE", "Use OpenRGB for lighting where supported. Advanced fan, macro, and ecosystem profiles may still need the original platform.", ""),
    ("Razer Synapse", "Use OpenRGB and OpenRazer-compatible tools where supported. Some device features remain vendor-only.", ""),
    ("SteelSeries GG", "Use OpenRGB or per-device onboard profiles where supported. Sonar and cloud features remain vendor-first.", ""),
    ("iCUE / Razer Synapse", "Use OpenRGB for unified RGB control across most brands, with vendor-tool gaps for advanced features.", ""),
    # Fonts & documents
    ("Microsoft fonts", "Run 'ujust install-ms-fonts' to install Times New Roman, Arial, and other core fonts for LibreOffice.", ""),
    ("LibreOffice", "LibreOffice is the drop-in Office suite. Install it from Flatpak if not already present.", "org.libreoffice.LibreOffice"),
]

STORE_CATEGORIES = [
    ("Internet", "Network"),
    ("Gaming", "Game"),
    ("Productivity", "Office"),
    ("Create", "Graphics AudioVideo"),
    ("Develop", "Development"),
    ("Security", "Security"),
    ("Utilities", "Utility"),
]

TRENDING_APPS = [
    "com.brave.Browser",
    "com.discordapp.Discord",
    "com.spotify.Client",
    "com.obsproject.Studio",
    "com.valvesoftware.Steam",
    "com.heroicgameslauncher.hgl",
    "com.github.tchx84.Flatseal",
    "org.localsend.localsend_app",
]

STORE_SHELVES = [
    {
        "name": "Game Night",
        "query": "Game",
        "apps": [
            "com.valvesoftware.Steam",
            "com.heroicgameslauncher.hgl",
            "net.lutris.Lutris",
            "com.usebottles.bottles",
        ],
    },
    {
        "name": "Creator Studio",
        "query": "Graphics AudioVideo",
        "apps": [
            "com.obsproject.Studio",
            "org.kde.kdenlive",
            "org.gimp.GIMP",
            "org.blender.Blender",
        ],
    },
    {
        "name": "Everyday Essentials",
        "query": "Network Office Utility",
        "apps": [
            "com.brave.Browser",
            "org.videolan.VLC",
            "com.bitwarden.desktop",
            "org.localsend.localsend_app",
        ],
    },
    {
        "name": "Tinker & Tune",
        "query": "Utility",
        "apps": [
            "com.github.tchx84.Flatseal",
            "io.github.flattool.Warehouse",
            "com.mattjakeman.ExtensionManager",
            "org.freedesktop.Piper",
        ],
    },
]

