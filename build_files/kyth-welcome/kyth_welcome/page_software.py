# __KYTH_GENERATED_IMPORTS__
from .core_base import _restyle
from .lazy_page import compose_on_first_init
from .services.software import Worker
from .qt import QHBoxLayout, QPushButton, QWidget
from .widgets import Page, _divider


def _load_software_mixins() -> tuple[type, ...]:
    from .page_software_appimages import _AppImageTabMixin
    from .page_software_creator import _CreatorTabMixin
    from .page_software_developer import _DeveloperTabMixin
    from .page_software_flatpak import _FlatpakStoreTabMixin
    from .page_software_installed import _InstalledTabMixin
    from .page_software_security import _SecurityTabMixin
    from .page_software_starter import _StarterPackTabMixin
    return (
        _StarterPackTabMixin,
        _FlatpakStoreTabMixin,
        _AppImageTabMixin,
        _InstalledTabMixin,
        _DeveloperTabMixin,
        _SecurityTabMixin,
        _CreatorTabMixin,
    )


# ── Page: Software ────────────────────────────────────────────────────────────
# Tab mixins load on first construction; individual tabs build on first visit.
@compose_on_first_init(_load_software_mixins)
class SoftwarePage(Page):
    """App store — Starter Packs | Store | AppImages | Installed."""

    _STARTER_PACKS = [
        {
            "name": "Gaming",
            "desc": "Steam, Epic/GOG, compatibility launchers, saves, and standalone .exe support.",
            "apps": [
                ("com.valvesoftware.Steam", "Steam", True),
                ("com.heroicgameslauncher.hgl", "Heroic Games Launcher", True),
                ("net.lutris.Lutris", "Lutris", True),
                ("com.usebottles.bottles", "Bottles", True),
                ("com.github.mtkennerly.ludusavi", "Ludusavi", True),
                ("net.davidotek.pupgui2", "ProtonUp-Qt", True),
            ],
        },
        {
            "name": "Creator",
            "desc": "Streaming, editing, audio, images, and 3D creation.",
            "apps": [
                ("com.obsproject.Studio", "OBS Studio", True),
                ("org.kde.kdenlive", "Kdenlive", True),
                ("org.audacityteam.Audacity", "Audacity", True),
                ("org.gimp.GIMP", "GIMP", True),
                ("org.inkscape.Inkscape", "Inkscape", True),
                ("org.blender.Blender", "Blender", True),
            ],
        },
        {
            "name": "Everyday",
            "desc": "Browser, chat, media, passwords, app management, and local file sharing.",
            "apps": [
                ("com.brave.Browser", "Brave Browser", True),
                ("com.discordapp.Discord", "Discord", True),
                ("org.videolan.VLC", "VLC", True),
                ("com.spotify.Client", "Spotify", True),
                ("com.bitwarden.desktop", "Bitwarden", False),
                ("org.localsend.localsend_app", "LocalSend", True),
                ("io.github.vikdevelop.WebApp", "WebApp Manager", True),
                ("com.github.tchx84.Flatseal", "Flatseal", True),
            ],
        },
    ]

    _CR_TOOLS = [
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

    _SEC_BOX_NAME = "kali"
    _SEC_BOX_IMAGE = "docker.io/kalilinux/kali-rolling"
    _SEC_HOST_TOOLS = [
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

    _CURATED_APPIMAGES = [
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

    _FAMILIAR_APPS = [
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

    _STORE_CATEGORIES = [
        ("Internet", "Network"),
        ("Gaming", "Game"),
        ("Productivity", "Office"),
        ("Create", "Graphics AudioVideo"),
        ("Develop", "Development"),
        ("Security", "Security"),
        ("Utilities", "Utility"),
    ]

    _TRENDING_APPS = [
        "com.brave.Browser",
        "com.discordapp.Discord",
        "com.spotify.Client",
        "com.obsproject.Studio",
        "com.valvesoftware.Steam",
        "com.heroicgameslauncher.hgl",
        "com.github.tchx84.Flatseal",
        "org.localsend.localsend_app",
    ]

    _STORE_SHELVES = [
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

    def __init__(self, initial_tab: int = 0, store_landing: bool = False):
        super().__init__()
        self._initial_tab = initial_tab
        self._store_landing = store_landing

        # Worker references
        self._starter_worker: Worker | None = None
        self._uninstall_worker: Worker | None = None
        self._uninstall_buttons: list[QPushButton] = []
        self._fp_search_worker: Worker | None = None
        self._fp_catalog_worker: Worker | None = None
        self._fp_refresh_worker: Worker | None = None
        self._fp_install_worker: Worker | None = None
        self._fp_uninstall_worker: Worker | None = None
        self._fp_search_lines: list[str] = []
        self._fp_catalog_lines: list[str] = []
        self._fp_catalog_entries: list[dict] = []
        self._fp_appstream_cache: dict[str, dict] | None = None
        self._fp_installing: str | None = None
        self._cr_tool_worker: Worker | None = None
        self._cr_active_tool_refs: dict | None = None
        self._cr_tool_refs: list[dict] = []
        self._dv_worker: Worker | None = None
        self._dv_selected_zip: str | None = None
        self._dev_worker: Worker | None = None
        self._sec_worker: Worker | None = None
        self._sec_host_tool_worker: Worker | None = None
        self._sec_active_host_refs: dict | None = None
        self._sec_host_tool_refs: list[dict] = []
        self._ms_fonts_worker: Worker | None = None
        self._ai_icon_path: str = ""

        # Starter pack per-pack state
        self._starter_pack_checks: dict = {}
        self._starter_pack_buttons: dict = {}
        self._starter_pack_details: dict = {}

        if store_landing:
            self._page_header(
                "Apps",
                "App Store",
                "Discover useful Flatpaks for KythOS, install them directly, and manage what you have.",
            )
        else:
            self._page_header(
                "Apps",
                "Software",
                "Starter packs, app migration helpers, AppImages, developer tools, and installed apps.",
            )

        # Tab bar — inserted into _outer between the page-header divider and the
        # scroll area. After _page_header(), _outer contains [hdr, div, scroll].
        tab_bar = QWidget()
        tab_bar.setObjectName("sw-tab-bar")
        tab_bar_layout = QHBoxLayout(tab_bar)
        tab_bar_layout.setContentsMargins(56, 0, 56, 0)
        tab_bar_layout.setSpacing(0)
        self._tab_btns: list[QPushButton] = []
        for i, label in enumerate(("Start", "Create", "Develop", "Security", "App Store", "AppImages", "Installed")):
            btn = QPushButton(label)
            btn.setObjectName("sw-tab-active" if i == self._initial_tab else "sw-tab")
            btn.clicked.connect(lambda _=False, idx=i: self._switch_tab(idx))
            tab_bar_layout.addWidget(btn)
            self._tab_btns.append(btn)
        tab_bar_layout.addStretch()
        self._outer.insertWidget(2, tab_bar)
        self._outer.insertWidget(3, _divider())

        self._current_tab = self._initial_tab
        self._tab_builders = (
            self._build_starter_tab,
            self._build_creator_tab,
            self._build_developer_tab,
            self._build_security_tab,
            self._build_flatpak_tab,
            self._build_appimage_tab,
            self._build_installed_tab,
        )
        # Build only the initial tab; other tabs on first visit.
        self._tab_widgets: list[QWidget | None] = [None] * len(self._tab_builders)
        self._ensure_tab(self._current_tab)
        self._stretch()

    def _ensure_tab(self, idx: int) -> QWidget:
        """Build tab *idx* on first visit and return its widget."""
        existing = self._tab_widgets[idx]
        if existing is not None:
            return existing
        tab_widget = self._tab_builders[idx]()
        self._add(tab_widget)
        tab_widget.setVisible(idx == self._current_tab)
        self._tab_widgets[idx] = tab_widget
        return tab_widget

    # ── Tab switching ──────────────────────────────────────────────────────────

    def _switch_tab(self, idx: int):
        if idx == self._current_tab:
            return
        self._ensure_tab(idx)
        for i, btn in enumerate(self._tab_btns):
            active = i == idx
            btn.setObjectName("sw-tab-active" if active else "sw-tab")
            _restyle(btn)
            widget = self._tab_widgets[i]
            if widget is not None:
                widget.setVisible(active)
        self._current_tab = idx
        if idx == 3:
            self._refresh_sec_status()
        elif idx == 6:
            self._refresh_installed_list()

