import configparser
import glob
import locale
import os
import json
import re
import shlex
import shutil
import subprocess
import defusedxml.ElementTree as ET

# __KYTH_GENERATED_IMPORTS__
from .core_base import (
    _apply_install_badge, _restyle,
)
from .services.software import (
    Worker, _chromium_app_window_cmd, _davinci_download_dir, _davinci_flatpak_app_id, _davinci_zip_candidates,
    _finish_worker, _install_flatpak_inline, _is_flatpak_installed, load_appstream_catalog,
)
from .qt import (  # noqa: E501
    QButtonGroup, QCheckBox, QComboBox, QDesktopServices, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QIcon, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QRadioButton, QTextEdit, QUrl, QVBoxLayout, QWidget, Qt,
)
from .widgets import (  # noqa: E501
    AppImageDropCard, Page, _divider, _make_card, _set_log_panel,
)

# ── Page: Security ────────────────────────────────────────────────────────────
def _is_distrobox_container(name: str) -> bool:
    """Return True if a distrobox container with the given name exists."""
    try:
        result = subprocess.run(
            ["distrobox", "list", "--no-color"],
            capture_output=True, text=True, timeout=10,
        )
        return name in result.stdout
    except Exception:
        return False


def _is_socket_capable_kali_box(name: str) -> bool:
    """Return True when Kali is rootful, privileged, and outside SELinux container_t."""
    try:
        result = subprocess.run(
            [
                "sudo", "-n", "podman", "inspect", name,
                "--format",
                "{{.ImageName}}\n{{.HostConfig.Privileged}}\n{{range .HostConfig.SecurityOpt}}{{.}} {{end}}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False
        lines = result.stdout.splitlines()
        image = lines[0] if len(lines) > 0 else ""
        privileged = lines[1] if len(lines) > 1 else ""
        security_opts = lines[2] if len(lines) > 2 else ""
        return "kali" in image and privileged == "true" and "label=disable" in security_opts
    except Exception:
        return False


_INSTALL_VSCODE_CMD = [
    "bash", "-c",
    "set -euo pipefail\n"
    "kyth-vscode-wallet\n"
    "echo 'VS Code and Headroom are baked into the image. Password storage configured.'",
]

_SETUP_DEV_BOX_CMD = [
    "bash", "-c",
    r"""set -euo pipefail
box="kyth-dev"
image="${KYTH_DEV_IMAGE:-registry.fedoraproject.org/fedora-toolbox:44}"
packages=(
    git gh just jq yq skopeo podman buildah
    python3 python3-pip python3-virtualenv
    ShellCheck shfmt ripgrep fd-find
    vim-enhanced neovim
)

if ! command -v distrobox >/dev/null 2>&1; then
    echo "ERROR: distrobox is not installed on this system." >&2
    exit 1
fi

kyth-vscode-wallet

if distrobox list --no-color 2>/dev/null | grep -q "^${box}\b"; then
    echo "${box} dev box already exists."
    echo "Use 'Enter Dev Box' to open it."
    exit 0
fi

echo "Creating KythOS development box..."
echo "  Image: ${image}"
distrobox create --image "${image}" --name "${box}" --yes
distrobox enter "${box}" -- sudo dnf install -y "${packages[@]}"
echo ""
echo "Done. Use 'Enter Dev Box' to start developing."
""",
]

# ── Page: Software ────────────────────────────────────────────────────────────
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

        # Build each tab widget and add to the scroll area
        self._tab_widgets: list[QWidget] = []
        for builder in (
            self._build_starter_tab,
            self._build_creator_tab,
            self._build_developer_tab,
            self._build_security_tab,
            self._build_flatpak_tab,
            self._build_appimage_tab,
            self._build_installed_tab,
        ):
            tab_widget = builder()
            self._add(tab_widget)
            self._tab_widgets.append(tab_widget)

        for i, tab in enumerate(self._tab_widgets):
            tab.setVisible(i == self._current_tab)

        self._stretch()

    # ── Tab switching ──────────────────────────────────────────────────────────

    def _switch_tab(self, idx: int):
        if idx == self._current_tab:
            return
        for i, (btn, widget) in enumerate(zip(self._tab_btns, self._tab_widgets)):
            active = i == idx
            btn.setObjectName("sw-tab-active" if active else "sw-tab")
            _restyle(btn)
            widget.setVisible(active)
        self._current_tab = idx
        if idx == 3:
            self._refresh_sec_status()
        elif idx == 6:
            self._refresh_installed_list()

    # ── Tab 0: Starter Packs ──────────────────────────────────────────────────

    def _build_starter_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        intro = QLabel(
            "Install familiar app sets in one pass. "
            "These are Flatpak desktop apps — sandboxed and easy to remove later."
        )
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(self._make_install_hierarchy_card())
        layout.addWidget(self._make_familiar_app_finder())

        for pack in self._STARTER_PACKS:
            layout.addWidget(self._make_starter_pack_panel(pack))

        layout.addWidget(self._make_ms_fonts_card())
        layout.addWidget(self._make_m365_webapps_card())

        self._starter_status = QLabel()
        self._starter_status.setObjectName("subheading")
        self._starter_status.hide()
        layout.addWidget(self._starter_status)

        self._starter_progress = QProgressBar()
        self._starter_progress.setRange(0, 0)
        self._starter_progress.hide()
        layout.addWidget(self._starter_progress)

        self._starter_log_toggle = QPushButton("Show details")
        self._starter_log_toggle.setCheckable(True)
        self._starter_log_toggle.hide()
        layout.addWidget(self._starter_log_toggle)

        self._starter_log = QTextEdit()
        self._starter_log.document().setMaximumBlockCount(5000)
        self._starter_log.setReadOnly(True)
        self._starter_log.setMaximumHeight(130)
        self._starter_log.hide()
        layout.addWidget(self._starter_log)
        self._starter_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._starter_log_toggle, self._starter_log, checked)
        )
        return tab

    def _make_ms_fonts_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Microsoft Fonts — Fix Word/Excel document formatting")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "LibreOffice substitutes fonts when Microsoft's core fonts (Times New Roman, Arial, "
            "Courier New, Verdana, Georgia, Impact) are missing. If documents sent from another system "
            "users look wrong, install the fonts below — they are free to use under Microsoft's EULA."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._ms_fonts_btn = QPushButton("Install Microsoft Fonts")
        self._ms_fonts_btn.setObjectName("primary")
        self._ms_fonts_btn.setToolTip("Downloads and installs MS core fonts to ~/.local/share/fonts via ujust install-ms-fonts")
        self._ms_fonts_btn.clicked.connect(self._run_ms_fonts)
        btns.addWidget(self._ms_fonts_btn)
        libreoffice_btn = QPushButton("Install LibreOffice")
        libreoffice_btn.setToolTip("Install LibreOffice from Flatpak — Writer, Calc, Impress, and Draw.")
        libreoffice_btn.clicked.connect(
            lambda _=False: self._install_familiar_app("org.libreoffice.LibreOffice", "LibreOffice")
        )
        btns.addWidget(libreoffice_btn)
        btns.addStretch()
        layout.addLayout(btns)
        self._ms_fonts_status = QLabel("")
        self._ms_fonts_status.setObjectName("card-copy")
        self._ms_fonts_status.setWordWrap(True)
        self._ms_fonts_status.hide()
        layout.addWidget(self._ms_fonts_status)
        return card

    def _run_ms_fonts(self):
        if hasattr(self, "_ms_fonts_worker") and self._ms_fonts_worker and self._ms_fonts_worker.isRunning():
            return
        self._ms_fonts_btn.setEnabled(False)
        self._ms_fonts_btn.setText("Installing…")
        self._ms_fonts_status.setText("Downloading Microsoft fonts from SourceForge…")
        self._ms_fonts_status.show()
        self._ms_fonts_worker = Worker(["bash", "-c", "ujust install-ms-fonts"])
        self._ms_fonts_worker.done.connect(self._on_ms_fonts_done)
        self._ms_fonts_worker.start()

    def _on_ms_fonts_done(self, code: int):
        self._ms_fonts_btn.setEnabled(True)
        self._ms_fonts_btn.setText("Install Microsoft Fonts")
        if code == 0:
            self._ms_fonts_status.setText("✓ Fonts installed. Restart LibreOffice to apply them.")
        else:
            self._ms_fonts_status.setText("✗ Installation failed. Check your network connection and try again.")

    def _make_m365_webapps_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Microsoft 365 — Web App Shortcuts")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Microsoft 365 runs fully in the browser. These shortcuts open each app in a dedicated "
            "Chromium window so they feel like native apps — pinnable to the taskbar, no tab clutter."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        _M365_APPS = [
            ("Outlook",   "https://outlook.office.com/mail/",      "Email and calendar"),
            ("Word",      "https://office.live.com/start/Word.aspx",   "Documents"),
            ("Excel",     "https://office.live.com/start/Excel.aspx",  "Spreadsheets"),
            ("PowerPoint","https://office.live.com/start/PowerPoint.aspx", "Presentations"),
            ("OneNote",   "https://www.onenote.com/notebooks",     "Notes"),
            ("Teams",     "https://teams.microsoft.com/",           "Chat and meetings"),
        ]

        btns = QHBoxLayout()
        btns.setSpacing(8)
        for name, url, tip in _M365_APPS:
            btn = QPushButton(name)
            btn.setToolTip(f"{tip} — opens in a dedicated Chromium window")
            btn.clicked.connect(
                lambda _=False, u=url, n=name: self._open_m365_webapp(u, n)
            )
            btns.addWidget(btn)
        btns.addStretch()
        layout.addLayout(btns)

        note = QLabel(
            "Tip: right-click any open Chromium app window → "
            "\"More tools\" → \"Create shortcut…\" to pin it to the KDE application launcher."
        )
        note.setObjectName("card-copy")
        note.setWordWrap(True)
        note.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(note)
        return card

    def _open_m365_webapp(self, url: str, name: str) -> None:
        launch = _chromium_app_window_cmd(url)
        if launch is None:
            QMessageBox.warning(
                self, "No browser found",
                "Opening web app shortcuts needs a Chromium-family browser "
                "(Brave, Chromium, Edge, or Chrome), but none was found.\n\n"
                "Install one from the Flatpak tab and try again.",
            )
            return
        try:
            subprocess.Popen(launch[0])
        except OSError as exc:
            QMessageBox.warning(self, "Could not open web app", str(exc))

    def _make_install_hierarchy_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Coming from another system? Here's how software works here.")
        title.setObjectName("card-title")
        layout.addWidget(title)

        rows = [
            ("1. Flatpak", "Your new .exe — most desktop apps live here. Browse Flathub or use the Starter Packs below."),
            ("2. Distrobox", "For anything not on Flatpak. Creates a container where you can dnf/apt install as normal."),
            ("3. rpm-ostree", "System-level tools only, such as drivers. Random downloaded .rpm files are rarely the right answer."),
        ]
        for label, desc in rows:
            row = QHBoxLayout()
            row.setSpacing(10)
            lbl = QLabel(label)
            lbl.setObjectName("card-summary")
            lbl.setStyleSheet("font-weight: 700; min-width: 110px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.addWidget(lbl)
            desc_lbl = QLabel(desc)
            desc_lbl.setObjectName("card-copy")
            desc_lbl.setWordWrap(True)
            row.addWidget(desc_lbl, 1)
            layout.addLayout(row)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        distrobox_btn = QPushButton("Install BoxBuddy (Distrobox GUI)")
        distrobox_btn.setToolTip("BoxBuddy is a graphical front-end for Distrobox — create containers without a terminal.")
        distrobox_btn.clicked.connect(
            lambda _=False: self._install_familiar_app("io.github.dvlv.boxbuddyrs", "BoxBuddy")
        )
        btns.addWidget(distrobox_btn)
        flathub_btn = QPushButton("Browse Flathub")
        flathub_btn.clicked.connect(
            lambda _=False: QDesktopServices.openUrl(QUrl("https://flathub.org"))
        )
        btns.addWidget(flathub_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _make_familiar_app_finder(self) -> QFrame:
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Familiar App Finder")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Search by the app name you remember. KythOS will suggest the native, Flatpak, web-app, Bottles, or launcher path."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        row = QHBoxLayout()
        self._familiar_combo = QComboBox()
        self._familiar_combo.setEditable(True)
        for name, _, _ in self._FAMILIAR_APPS:
            self._familiar_combo.addItem(name)
        row.addWidget(self._familiar_combo, 1)
        btn = QPushButton("Find Path")
        btn.setObjectName("primary")
        btn.clicked.connect(self._find_familiar_app)
        row.addWidget(btn)
        layout.addLayout(row)
        self._familiar_result = QLabel("Try Office, Photoshop, Battle.net, Vortex, Notepad++, or G HUB.")
        self._familiar_result.setObjectName("card-copy")
        self._familiar_result.setWordWrap(True)
        layout.addWidget(self._familiar_result)
        btns = QHBoxLayout()
        self._familiar_install_btn = QPushButton("Install Suggested App")
        self._familiar_install_btn.hide()
        btns.addWidget(self._familiar_install_btn)
        flathub_btn = QPushButton("Search Flathub")
        flathub_btn.clicked.connect(lambda _=False: self._search_familiar_on_flathub())
        btns.addWidget(flathub_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _find_familiar_app(self):
        query = self._familiar_combo.currentText().strip()
        lower = query.lower()
        match = None
        for name, desc, app_id in self._FAMILIAR_APPS:
            if lower in name.lower() or name.lower() in lower:
                match = (name, desc, app_id)
                break
        if not match:
            self._familiar_result.setText(
                f"No curated path for “{query}” yet. Search Flathub first; use Bottles only when a native/web path does not exist."
            )
            self._familiar_install_btn.hide()
            return
        name, desc, app_id = match
        self._familiar_result.setText(f"{name}: {desc}")
        if app_id:
            self._familiar_install_btn.setText(f"Install {name.split('/')[0].strip()}")
            try:
                self._familiar_install_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._familiar_install_btn.clicked.connect(
                lambda _=False, aid=app_id, n=name: self._install_familiar_app(aid, n)
            )
            self._familiar_install_btn.show()
        else:
            self._familiar_install_btn.hide()

    # After Mission Center installs, hand it the Task Manager shortcut:
    # Ctrl+Shift+Esc launches it and the stock System Monitor binding clears
    # so the two never race for the key. kglobalaccel rereads on restart.
    _MISSION_CENTER_REBIND_CMD = (
        "kwriteconfig6 --file kglobalshortcutsrc"
        " --group services --group io.missioncenter.MissionCenter.desktop"
        " --key _launch 'Ctrl+Shift+Esc'"
        " && kwriteconfig6 --file kglobalshortcutsrc"
        " --group org.kde.plasma-systemmonitor.desktop"
        " --key _launch 'none,none,System Monitor'"
        " && (systemctl --user restart plasma-kglobalaccel.service || true)"
    )

    def _install_familiar_app(self, app_id: str, name: str):
        if app_id == "io.missioncenter.MissionCenter":
            _install_flatpak_inline(
                self, self._familiar_install_btn, app_id, name,
                extra_cmd=self._MISSION_CENTER_REBIND_CMD,
            )
            return
        self._switch_tab(4)
        self._fp_search_box.setText(app_id)
        self._fp_install(app_id, name, self._familiar_install_btn)

    def _search_familiar_on_flathub(self):
        query = self._familiar_combo.currentText().strip()
        self._switch_tab(4)
        self._fp_search_box.setText(query)
        self._run_fp_search()

    def _make_starter_pack_panel(self, pack: dict) -> QFrame:
        name = pack["name"]
        apps = pack["apps"]

        panel = QFrame()
        panel.setObjectName("starter-pack")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(10)

        header = QPushButton(f"▸  {name}")
        header.setObjectName("starter-pack-header")
        header.setCheckable(True)
        header.setCursor(Qt.CursorShape.PointingHandCursor)

        meta = QLabel(f"{len(apps)} apps")
        meta.setObjectName("starter-pack-meta")
        meta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        head_row = QHBoxLayout()
        head_row.setSpacing(10)
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        head_text.addWidget(header)
        desc_lbl = QLabel(pack["desc"])
        desc_lbl.setObjectName("card-copy")
        desc_lbl.setWordWrap(True)
        head_text.addWidget(desc_lbl)
        head_row.addLayout(head_text, 1)
        head_row.addWidget(meta)
        panel_layout.addLayout(head_row)

        details = QWidget()
        details.setObjectName("starter-pack-details")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(22, 0, 0, 0)
        details_layout.setSpacing(8)
        details.hide()

        checks = []
        for app_id, label, selected_by_default in apps:
            installed = _is_flatpak_installed(app_id)
            check = QCheckBox(label)
            check.setChecked(selected_by_default and not installed)
            check.setEnabled(not installed)
            check.setToolTip(app_id)
            state_text = "Installed" if installed else ("Available" if selected_by_default else "Optional")

            app_row = QHBoxLayout()
            app_row.setSpacing(10)
            app_row.addWidget(check, 1)
            state = QLabel(state_text)
            state.setObjectName("card-copy")
            state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            app_row.addWidget(state)
            checks.append((check, app_id, label, state))
            details_layout.addLayout(app_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        install_btn = QPushButton(f"Install {name}")
        install_btn.setObjectName("primary" if name == "Gaming" else "")
        install_btn.clicked.connect(lambda _=False, n=name: self._install_starter_pack(n))
        button_row.addWidget(install_btn)
        select_all_btn = QPushButton("Select Missing")
        select_all_btn.clicked.connect(lambda _=False, n=name: self._set_starter_pack_selection(n, True))
        button_row.addWidget(select_all_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda _=False, n=name: self._set_starter_pack_selection(n, False))
        button_row.addWidget(clear_btn)
        button_row.addStretch()
        details_layout.addLayout(button_row)
        panel_layout.addWidget(details)

        header.clicked.connect(
            lambda checked, h=header, d=details, n=name: self._toggle_starter_pack(n, h, d, checked)
        )

        self._starter_pack_checks[name] = checks
        self._starter_pack_buttons[name] = install_btn
        self._starter_pack_details[name] = details
        return panel

    def _toggle_starter_pack(self, name: str, header: QPushButton, details: QWidget, checked: bool):
        header.setText(f"{'▾' if checked else '▸'}  {name}")
        details.setVisible(checked)

    def _set_starter_pack_selection(self, name: str, selected: bool):
        for check, _, _, _ in self._starter_pack_checks.get(name, []):
            if check.isEnabled():
                check.setChecked(selected)

    def _selected_starter_pack_apps(self, name: str) -> list[tuple[str, str, QCheckBox]]:
        return [
            (app_id, label, check)
            for check, app_id, label, _ in self._starter_pack_checks.get(name, [])
            if check.isChecked() and check.isEnabled()
        ]

    def _set_starter_pack_controls_enabled(self, enabled: bool):
        for button in self._starter_pack_buttons.values():
            button.setEnabled(enabled)
        for checks in self._starter_pack_checks.values():
            for check, _, _, _ in checks:
                if not _is_flatpak_installed(check.toolTip()):
                    check.setEnabled(enabled)

    def _install_starter_pack(self, name: str):
        if self._starter_worker and self._starter_worker.isRunning():
            return
        selected = self._selected_starter_pack_apps(name)
        if not selected:
            self._starter_status.setText(f"No apps selected for {name}.")
            self._starter_status.setObjectName("status-dim")
            self._starter_status.show()
            _restyle(self._starter_status)
            return
        app_ids = [app_id for app_id, _, _ in selected]
        missing = [app_id for app_id in app_ids if not _is_flatpak_installed(app_id)]
        if not missing:
            self._starter_status.setText(f"Selected {name} apps are already installed.")
            self._starter_status.setObjectName("status-ok")
            self._starter_status.show()
            _restyle(self._starter_status)
            return
        cmd = [
            "bash", "-c",
            "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            " && flatpak install -y flathub " + " ".join(shlex.quote(app_id) for app_id in missing),
        ]
        self._starter_log.clear()
        self._starter_log.append(f"→ install selected {name} apps\n")
        for app_id in missing:
            self._starter_log.append(f"  {app_id}")
        self._starter_log_toggle.show()
        _set_log_panel(self._starter_log_toggle, self._starter_log, False)
        self._starter_progress.show()
        self._starter_status.setText(f"Installing {name} starter pack…")
        self._starter_status.setObjectName("subheading")
        self._starter_status.show()
        _restyle(self._starter_status)
        self._set_starter_pack_controls_enabled(False)
        self._starter_worker = Worker(cmd)
        self._starter_worker.line.connect(self._on_starter_line)
        self._starter_worker.done.connect(
            lambda code, n=name, ids=missing: self._on_starter_done(code, n, ids)
        )
        self._starter_worker.start()

    def _on_starter_line(self, ln: str):
        self._starter_log.append(ln)
        self._starter_log.ensureCursorVisible()

    def _on_starter_done(self, code: int, name: str, installed_ids: list[str]):
        self._starter_progress.hide()
        _finish_worker(self, attr="_starter_worker")
        self._set_starter_pack_controls_enabled(True)
        if code == 0:
            self._starter_status.setText(f"Selected {name} apps installed.")
            self._starter_status.setObjectName("status-ok")
            self._starter_log.append("\nDone.")
            installed_set = set(installed_ids)
            for check, app_id, _, state in self._starter_pack_checks.get(name, []):
                if app_id in installed_set:
                    check.setChecked(False)
                    check.setEnabled(False)
                    state.setText("Installed")
        else:
            self._starter_status.setText(f"{name} app install failed (exit {code}).")
            self._starter_status.setObjectName("status-err")
            _set_log_panel(self._starter_log_toggle, self._starter_log, True)
        _restyle(self._starter_status)

    # ── Tab 4: Flatpak Store ──────────────────────────────────────────────────

    def _build_flatpak_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("store-hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(18)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(6)
        kicker = QLabel("KYTH APP STORE")
        kicker.setObjectName("store-kicker")
        hero_text.addWidget(kicker)
        title = QLabel("Useful apps, ready to install")
        title.setObjectName("store-hero-title")
        title.setWordWrap(True)
        hero_text.addWidget(title)
        intro = QLabel(
            "Install trusted Flatpaks without leaving System Hub. Start with trending picks, browse curated shelves, or search the full Flathub catalog."
        )
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        hero_text.addWidget(intro)
        hero_layout.addLayout(hero_text, 1)
        hero_actions = QVBoxLayout()
        hero_actions.setSpacing(8)
        featured_btn = QPushButton("Show Featured")
        featured_btn.setObjectName("primary")
        featured_btn.clicked.connect(lambda _=False: self._render_store_landing())
        hero_actions.addWidget(featured_btn)
        browse_btn = QPushButton("Browse Catalog")
        browse_btn.clicked.connect(lambda _=False: self._load_fp_catalog())
        hero_actions.addWidget(browse_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_fp_metadata)
        hero_actions.addWidget(refresh_btn)
        hero_actions.addStretch()
        hero_layout.addLayout(hero_actions)
        layout.addWidget(hero)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._fp_refresh_btn = QPushButton("Refresh")
        self._fp_refresh_btn.clicked.connect(self._refresh_fp_metadata)
        action_row.addWidget(self._fp_refresh_btn)
        self._fp_catalog_btn = QPushButton("Browse All")
        self._fp_catalog_btn.clicked.connect(lambda _=False: self._load_fp_catalog())
        action_row.addWidget(self._fp_catalog_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        for label, query in self._STORE_CATEGORIES:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, q=query, l=label: self._show_fp_category(q, l))
            category_row.addWidget(btn)
        category_row.addStretch()
        layout.addLayout(category_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._fp_search_box = QLineEdit()
        self._fp_search_box.setPlaceholderText("Search Flathub...  e.g. firefox, obsidian, gimp")
        self._fp_search_box.returnPressed.connect(self._run_fp_search)
        search_row.addWidget(self._fp_search_box, 1)
        self._fp_search_btn = QPushButton("Search")
        self._fp_search_btn.setObjectName("primary")
        self._fp_search_btn.clicked.connect(self._run_fp_search)
        search_row.addWidget(self._fp_search_btn)
        layout.addLayout(search_row)

        self._fp_status = QLabel()
        self._fp_status.setObjectName("status-dim")
        self._fp_status.hide()
        layout.addWidget(self._fp_status)

        self._fp_progress = QProgressBar()
        self._fp_progress.setRange(0, 0)
        self._fp_progress.hide()
        layout.addWidget(self._fp_progress)

        self._fp_install_log_toggle = QPushButton("Show details")
        self._fp_install_log_toggle.setCheckable(True)
        self._fp_install_log_toggle.hide()
        layout.addWidget(self._fp_install_log_toggle)

        self._fp_install_log = QTextEdit()
        self._fp_install_log.document().setMaximumBlockCount(5000)
        self._fp_install_log.setReadOnly(True)
        self._fp_install_log.setMaximumHeight(130)
        self._fp_install_log.hide()
        layout.addWidget(self._fp_install_log)
        self._fp_install_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, checked)
        )

        self._fp_results_layout = QVBoxLayout()
        self._fp_results_layout.setSpacing(8)
        layout.addLayout(self._fp_results_layout)

        self._render_store_landing()
        return tab

    def _fallback_store_names(self) -> dict[str, tuple[str, str]]:
        names: dict[str, tuple[str, str]] = {}
        for pack in self._STARTER_PACKS:
            for app_id, label, _ in pack["apps"]:
                names[app_id] = (label, pack["desc"])
        for tool in self._CR_TOOLS + self._SEC_HOST_TOOLS:
            names[tool["flatpak"]] = (tool["name"], tool["desc"])
        for _, desc, app_id in self._FAMILIAR_APPS:
            if app_id:
                names.setdefault(app_id, (app_id.rsplit(".", 1)[-1], desc))
        names.update({
            "io.github.flattool.Warehouse": ("Warehouse", "Manage Flatpak apps, remotes, data, and leftover files."),
            "com.mattjakeman.ExtensionManager": ("Extension Manager", "Browse, install, and manage GNOME Shell extensions."),
            "org.freedesktop.Piper": ("Piper", "Configure gaming mice and supported peripherals."),
        })
        return names

    def _store_entry_for_app(self, app_id: str) -> dict:
        details = self._fp_appstream_details(app_id)
        fallback_name, fallback_summary = self._fallback_store_names().get(
            app_id, (app_id.rsplit(".", 1)[-1], "")
        )
        return {
            "application_id": app_id,
            "name": details.get("name") or fallback_name,
            "description": details.get("summary") or fallback_summary,
            "version": details.get("version", ""),
            "remote": "flathub",
        }

    def _render_store_landing(self):
        self._clear_fp_results()
        catalog = self._fp_appstream_catalog()
        self._fp_status.setText(
            "Featured Kyth picks. Search or browse the catalog for more."
            if catalog else
            "Featured Kyth picks. Refresh metadata for richer descriptions, icons, and categories."
        )
        self._fp_status.setObjectName("status-dim")
        self._fp_status.show()
        _restyle(self._fp_status)

        trending_label = QLabel("Trending on Kyth")
        trending_label.setObjectName("section-heading")
        self._fp_results_layout.addWidget(trending_label)

        rows = [self._TRENDING_APPS[:4], self._TRENDING_APPS[4:]]
        for app_ids in rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(10)
            for app_id in app_ids:
                row_layout.addWidget(self._make_store_app_card(self._store_entry_for_app(app_id)), 1)
            self._fp_results_layout.addLayout(row_layout)

        categories_label = QLabel("Browse by category")
        categories_label.setObjectName("section-heading")
        self._fp_results_layout.addWidget(categories_label)

        shelf_row = QHBoxLayout()
        shelf_row.setSpacing(10)
        for shelf in self._STORE_SHELVES:
            shelf_row.addWidget(self._make_store_category_card(shelf), 1)
        self._fp_results_layout.addLayout(shelf_row)

        for shelf in self._STORE_SHELVES[:3]:
            self._fp_results_layout.addWidget(self._make_store_shelf(shelf))

    def _make_store_app_card(self, entry: dict) -> QFrame:
        app_id = entry.get("application_id", "").strip()
        name = entry.get("name", app_id).strip() or app_id
        summary = entry.get("description", "").strip()
        details = self._fp_appstream_details(app_id)

        card = QFrame()
        card.setObjectName("store-app-card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(44, 44)
        icon_path = self._fp_icon_path(app_id)
        icon = QIcon(icon_path) if icon_path else QIcon.fromTheme("package-x-generic")
        icon_lbl.setPixmap(icon.pixmap(44, 44))
        top.addWidget(icon_lbl)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setObjectName("card-summary")
        name_lbl.setWordWrap(True)
        title_col.addWidget(name_lbl)
        meta = QLabel("Verified" if details.get("verified") else "Flatpak")
        meta.setObjectName("starter-pack-meta")
        title_col.addWidget(meta)
        top.addLayout(title_col, 1)
        layout.addLayout(top)

        summary_lbl = QLabel(summary or app_id)
        summary_lbl.setObjectName("card-copy")
        summary_lbl.setWordWrap(True)
        summary_lbl.setMinimumHeight(48)
        layout.addWidget(summary_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        details_btn = QPushButton("Details")
        details_btn.clicked.connect(lambda _=False, e=entry: self._show_fp_details(e))
        btn_row.addWidget(details_btn)
        open_btn = QPushButton("Open")
        install_btn = QPushButton()
        self._configure_fp_lifecycle_buttons(app_id, name, install_btn, open_btn)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(install_btn)
        layout.addLayout(btn_row)
        return card

    def _make_store_category_card(self, shelf: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("store-category-card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        title = QLabel(shelf["name"])
        title.setObjectName("card-title")
        title.setWordWrap(True)
        layout.addWidget(title)
        count = QLabel(f"{len(shelf['apps'])}+ picks")
        count.setObjectName("starter-pack-meta")
        layout.addWidget(count)
        btn = QPushButton("Open Shelf")
        btn.clicked.connect(lambda _=False, s=shelf: self._open_store_shelf(s))
        layout.addWidget(btn)
        return card

    def _make_store_shelf(self, shelf: dict) -> QFrame:
        panel, layout = _make_card()
        head = QHBoxLayout()
        title = QLabel(shelf["name"])
        title.setObjectName("card-title")
        head.addWidget(title, 1)
        all_btn = QPushButton("More")
        all_btn.clicked.connect(lambda _=False, q=shelf["query"], n=shelf["name"]: self._show_fp_category(q, n))
        head.addWidget(all_btn)
        layout.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(10)
        for app_id in shelf["apps"]:
            row.addWidget(self._make_store_app_card(self._store_entry_for_app(app_id)), 1)
        layout.addLayout(row)
        return panel

    def _open_store_shelf(self, shelf: dict):
        self._clear_fp_results()
        self._set_fp_task_state(f"{shelf['name']}: curated apps for Kyth users.", "idle")
        self._fp_results_layout.addWidget(self._make_store_shelf(shelf))
        more_btn = QPushButton(f"Browse more {shelf['name']} apps")
        more_btn.clicked.connect(lambda _=False, q=shelf["query"], n=shelf["name"]: self._show_fp_category(q, n))
        self._fp_results_layout.addWidget(more_btn)

    def _run_fp_search(self):
        if self._fp_search_worker and self._fp_search_worker.isRunning():
            return
        query = self._fp_search_box.text().strip()
        if not query:
            return
        self._clear_fp_results()
        self._fp_search_lines = []
        self._fp_progress.show()
        self._set_fp_task_state(f"Searching Flathub for “{query}”…", "running")
        self._fp_search_btn.setEnabled(False)
        self._fp_search_worker = Worker(
            ["flatpak", "search", "-j", query]
        )
        self._fp_search_worker.line.connect(self._on_fp_search_line)
        self._fp_search_worker.done.connect(self._on_fp_search_done)
        self._fp_search_worker.start()

    def _on_fp_search_line(self, ln: str):
        self._fp_search_lines.append(ln)

    def _on_fp_search_done(self, code: int):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_search_worker")
        self._fp_search_btn.setEnabled(True)
        self._clear_fp_results()
        output = "\n".join(self._fp_search_lines).strip()
        results = []
        if output.startswith("["):
            try:
                for item in json.loads(output):
                    app_id = (item.get("application_id") or item.get("application") or "").strip()
                    if app_id:
                        results.append({
                            "application_id": app_id,
                            "name": (item.get("name") or app_id).strip(),
                            "description": (item.get("description") or "").strip(),
                            "version": (item.get("version") or "").strip(),
                            "remote": (item.get("remotes") or item.get("remote") or "flathub").strip(),
                        })
            except (json.JSONDecodeError, TypeError):
                results = []
        else:
            for line in self._fp_search_lines:
                parts = line.split("\t")
                if len(parts) >= 2:
                    app_id = parts[0].strip()
                    name = parts[1].strip()
                    summary = parts[2].strip() if len(parts) >= 3 else ""
                    if app_id:
                        results.append({
                            "application_id": app_id,
                            "name": name or app_id,
                            "description": summary,
                            "version": "",
                            "remote": "flathub",
                        })
        if not results:
            detail = next((line.strip() for line in self._fp_search_lines if line.strip()), "")
            if code == 0:
                msg = "No results found."
            elif detail:
                msg = f"Search failed — {detail}"
            else:
                msg = "Search failed — check that Flatpak and Flathub are available."
            self._set_fp_task_state(msg, "idle" if code == 0 else "warn")
            return
        shown = results[:30]
        count_msg = f"{len(results)} result{'s' if len(results) != 1 else ''} found"
        if len(results) > 30:
            count_msg += " — showing top 30"
        self._set_fp_task_state(count_msg + ".", "idle")
        for entry in shown:
            self._fp_results_layout.addWidget(self._make_fp_result_row(entry))

    def _clear_fp_results(self):
        def clear_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                child_layout = item.layout()
                if widget:
                    widget.deleteLater()
                elif child_layout:
                    clear_layout(child_layout)
        while self._fp_results_layout.count():
            item = self._fp_results_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                clear_layout(child_layout)

    def _refresh_fp_metadata(self):
        if self._fp_refresh_worker and self._fp_refresh_worker.isRunning():
            return
        self._fp_search_lines = []
        self._fp_progress.show()
        self._set_fp_task_state("Refreshing Flathub metadata...", "running")
        self._fp_refresh_btn.setEnabled(False)
        self._fp_refresh_worker = Worker(["flatpak", "update", "--appstream"])
        self._fp_refresh_worker.line.connect(self._on_fp_search_line)
        self._fp_refresh_worker.done.connect(self._on_fp_refresh_done)
        self._fp_refresh_worker.start()

    def _on_fp_refresh_done(self, code: int):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_refresh_worker")
        self._fp_refresh_btn.setEnabled(True)
        self._fp_appstream_cache = None
        self._fp_catalog_entries = []
        if code == 0:
            self._set_fp_task_state("Flathub metadata refreshed.", "success")
        else:
            detail = next((line.strip() for line in self._fp_search_lines if line.strip()), "")
            self._set_fp_task_state(detail or f"Metadata refresh failed (exit {code}). Cached data can still be used.", "warn")

    def _load_fp_catalog(self):
        if self._fp_catalog_worker and self._fp_catalog_worker.isRunning():
            return
        self._clear_fp_results()
        self._fp_catalog_lines = []
        self._fp_progress.show()
        self._set_fp_task_state("Loading cached Flathub catalog...", "running")
        self._fp_catalog_btn.setEnabled(False)
        self._fp_catalog_worker = Worker([
            "flatpak", "remote-ls", "--cached", "--app",
            "--columns=application,name,description,version,download-size,installed-size",
            "-j", "flathub",
        ])
        self._fp_catalog_worker.line.connect(self._on_fp_catalog_line)
        self._fp_catalog_worker.done.connect(self._on_fp_catalog_done)
        self._fp_catalog_worker.start()

    def _on_fp_catalog_line(self, ln: str):
        self._fp_catalog_lines.append(ln)

    def _on_fp_catalog_done(self, code: int):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_catalog_worker")
        self._fp_catalog_btn.setEnabled(True)
        output = "\n".join(self._fp_catalog_lines).strip()
        entries = []
        if output.startswith("["):
            try:
                for item in json.loads(output):
                    app_id = (item.get("application_id") or item.get("application") or "").strip()
                    if app_id:
                        item["application_id"] = app_id
                        item["remote"] = "flathub"
                        entries.append(item)
            except (json.JSONDecodeError, TypeError):
                entries = []
        if code != 0 or not entries:
            detail = next((line.strip() for line in self._fp_catalog_lines if line.strip()), "")
            self._set_fp_task_state(detail or "Cached Flathub catalog could not be loaded.", "warn")
            return
        self._fp_catalog_entries = entries
        self._render_fp_entries(entries, "Cached Flathub catalog")

    def _render_fp_entries(self, entries: list[dict], title: str, limit: int = 60):
        self._clear_fp_results()
        shown = entries[:limit]
        count_msg = f"{title}: {len(entries)} app{'s' if len(entries) != 1 else ''}"
        if len(entries) > limit:
            count_msg += f" — showing first {limit}"
        self._set_fp_task_state(count_msg + ".", "idle")
        for entry in shown:
            self._fp_results_layout.addWidget(self._make_fp_result_row(entry))

    def _show_fp_category(self, category_query: str, label: str):
        catalog = self._fp_appstream_catalog()
        tokens = {token.strip().lower() for token in category_query.split() if token.strip()}
        matches = []
        for app_id, details in catalog.items():
            categories = {cat.lower() for cat in details.get("categories", [])}
            if not tokens.intersection(categories):
                continue
            entry = {
                "application_id": app_id,
                "name": details.get("name", app_id),
                "description": details.get("summary", ""),
                "version": details.get("version", ""),
                "remote": "flathub",
            }
            matches.append(entry)
        matches.sort(key=lambda item: (item.get("name") or item.get("application_id") or "").lower())
        self._render_fp_entries(matches, label)

    def _fp_icon_path(self, app_id: str) -> str:
        for size in ("128x128", "64x64"):
            path = f"/var/lib/flatpak/appstream/flathub/x86_64/active/icons/{size}/{app_id}.png"
            if os.path.exists(path):
                return path
        return ""

    def _fp_appstream_catalog(self) -> dict[str, dict]:
        if self._fp_appstream_cache is not None:
            return self._fp_appstream_cache
        self._fp_appstream_cache = load_appstream_catalog()
        return self._fp_appstream_cache

    def _fp_appstream_details(self, app_id: str) -> dict:
        return self._fp_appstream_catalog().get(app_id, {})

    def _show_fp_details(self, entry: dict):
        app_id = entry.get("application_id", "").strip()
        details = self._fp_appstream_details(app_id)
        name = details.get("name") or entry.get("name") or app_id
        dlg = QDialog(self)
        dlg.setWindowTitle(name)
        dlg.setMinimumWidth(640)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(64, 64)
        icon_path = self._fp_icon_path(app_id)
        icon = QIcon(icon_path) if icon_path else QIcon.fromTheme("package-x-generic")
        icon_lbl.setPixmap(icon.pixmap(64, 64))
        header.addWidget(icon_lbl)
        title_col = QVBoxLayout()
        title = QLabel(name)
        title.setObjectName("card-title")
        title_col.addWidget(title)
        meta = QLabel(app_id)
        meta.setObjectName("card-copy")
        title_col.addWidget(meta)
        header.addLayout(title_col, 1)
        layout.addLayout(header)

        summary = QLabel(details.get("summary") or entry.get("description") or "")
        summary.setObjectName("card-summary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        body_text = details.get("description") or "No extended AppStream description is available for this app yet."
        body = QTextEdit()
        body.setReadOnly(True)
        body.setMaximumHeight(180)
        body.setPlainText(body_text)
        layout.addWidget(body)

        facts = []
        if details.get("developer"):
            facts.append(f"Developer: {details['developer']}")
        version = entry.get("version") or details.get("version")
        if version:
            facts.append(f"Version: {version}")
        if entry.get("download_size"):
            facts.append(f"Download: {entry['download_size']}")
        if entry.get("installed_size"):
            facts.append(f"Installed size: {entry['installed_size']}")
        if details.get("license"):
            facts.append(f"License: {details['license']}")
        if details.get("categories"):
            facts.append("Categories: " + ", ".join(details["categories"][:6]))
        facts.append("Flathub verification: " + ("verified" if details.get("verified") else "not marked verified"))
        fact_lbl = QLabel("\n".join(facts))
        fact_lbl.setObjectName("card-copy")
        fact_lbl.setWordWrap(True)
        layout.addWidget(fact_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        homepage = details.get("homepage")
        if homepage:
            homepage_btn = QPushButton("Homepage")
            homepage_btn.clicked.connect(lambda _=False, url=homepage: QDesktopServices.openUrl(QUrl(url)))
            btn_row.addWidget(homepage_btn)
        screenshots = details.get("screenshots") or []
        if screenshots:
            shot_btn = QPushButton("Screenshot")
            shot_btn.clicked.connect(lambda _=False, url=screenshots[0]: QDesktopServices.openUrl(QUrl(url)))
            btn_row.addWidget(shot_btn)
        flathub_btn = QPushButton("Flathub Page")
        flathub_btn.clicked.connect(lambda _=False, aid=app_id: QDesktopServices.openUrl(QUrl(f"https://flathub.org/apps/{aid}")))
        btn_row.addWidget(flathub_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec()

    def _make_fp_result_row(self, entry: dict) -> QFrame:
        app_id = entry.get("application_id", "").strip()
        name = entry.get("name", app_id).strip() or app_id
        summary = entry.get("description", "").strip()
        version = entry.get("version", "").strip()
        download_size = entry.get("download_size", "").strip()
        details = self._fp_appstream_details(app_id)
        if details:
            name = details.get("name") or name
            summary = details.get("summary") or summary
            version = version or details.get("version", "")

        row = QFrame()
        row.setObjectName("stat-tile")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 10, 14, 10)
        row_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(48, 48)
        icon_path = self._fp_icon_path(app_id)
        icon = QIcon(icon_path) if icon_path else QIcon.fromTheme("package-x-generic")
        icon_lbl.setPixmap(icon.pixmap(48, 48))
        row_layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(name or app_id)
        name_lbl.setObjectName("card-summary")
        text_col.addWidget(name_lbl)
        meta_bits = [app_id]
        if version:
            meta_bits.append(version)
        if download_size:
            meta_bits.append(download_size)
        if details.get("verified"):
            meta_bits.append("Verified")
        id_lbl = QLabel("  •  ".join(meta_bits))
        id_lbl.setObjectName("card-copy")
        text_col.addWidget(id_lbl)
        if summary:
            summary_lbl = QLabel(summary)
            summary_lbl.setObjectName("card-copy")
            summary_lbl.setWordWrap(True)
            text_col.addWidget(summary_lbl)
        row_layout.addLayout(text_col, 1)

        details_btn = QPushButton("Details")
        details_btn.clicked.connect(lambda _=False, e=entry: self._show_fp_details(e))
        row_layout.addWidget(details_btn)

        open_btn = QPushButton("Open")
        row_layout.addWidget(open_btn)

        install_btn = QPushButton()
        self._configure_fp_lifecycle_buttons(app_id, name, install_btn, open_btn)
        row_layout.addWidget(install_btn)
        return row

    def _configure_fp_lifecycle_buttons(
        self,
        app_id: str,
        name: str,
        action_btn: QPushButton,
        open_btn: QPushButton | None = None,
        installed: bool | None = None,
    ) -> None:
        installed = _is_flatpak_installed(app_id) if installed is None else installed
        for btn in (action_btn, open_btn):
            if btn is None:
                continue
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass

        if open_btn is not None:
            open_btn.setVisible(installed)
            open_btn.setEnabled(installed)
            open_btn.setObjectName("primary" if installed else "")
            if installed:
                open_btn.clicked.connect(lambda _=False, aid=app_id: self._open_fp_app(aid))
            _restyle(open_btn)

        if installed:
            action_btn.setText("Uninstall")
            action_btn.setObjectName("danger")
            action_btn.clicked.connect(
                lambda _=False, aid=app_id, n=name, b=action_btn, ob=open_btn: self._fp_store_uninstall(aid, n, b, ob)
            )
        else:
            action_btn.setText("Install")
            action_btn.setObjectName("primary")
            action_btn.clicked.connect(
                lambda _=False, aid=app_id, n=name, b=action_btn, ob=open_btn: self._fp_install(aid, n, b, ob)
            )
        action_btn.setEnabled(True)
        _restyle(action_btn)

    def _open_fp_app(self, app_id: str) -> None:
        subprocess.Popen(["flatpak", "run", app_id])

    def _set_fp_task_state(self, message: str, state: str) -> None:
        styles = {
            "idle": "task-status-idle",
            "running": "task-status-running",
            "success": "task-status-ok",
            "warn": "task-status-warn",
            "error": "task-status-err",
        }
        self._fp_status.setText(message)
        self._fp_status.setObjectName(styles.get(state, "task-status-idle"))
        self._fp_status.show()
        _restyle(self._fp_status)

    def _fp_install(self, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        if self._fp_install_worker and self._fp_install_worker.isRunning():
            return
        self._fp_installing = app_id
        btn.setText("Installing…")
        btn.setEnabled(False)
        self._fp_install_log.clear()
        self._fp_install_log.append(f"→ flatpak install flathub {app_id}\n")
        self._fp_install_log_toggle.show()
        _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, False)
        self._fp_progress.show()
        self._set_fp_task_state(f"Installing {name or app_id}…", "running")
        cmd = [
            "bash", "-c",
            "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {shlex.quote(app_id)}",
        ]
        self._fp_install_worker = Worker(cmd)
        self._fp_install_worker.line.connect(self._on_fp_install_line)
        self._fp_install_worker.done.connect(
            lambda code, aid=app_id, n=name, b=btn, ob=open_btn: self._on_fp_install_done(code, aid, n, b, ob)
        )
        self._fp_install_worker.start()

    def _on_fp_install_line(self, ln: str):
        self._fp_install_log.append(ln)
        self._fp_install_log.ensureCursorVisible()

    def _on_fp_install_done(self, code: int, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_install_worker")
        self._fp_installing = None
        if code == 0:
            self._set_fp_task_state(f"{name or app_id} installed.", "success")
            self._fp_install_log.append("\nDone.")
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=True)
        else:
            self._set_fp_task_state(f"Install failed (exit {code}).", "error")
            _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, True)
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=False)

    def _fp_store_uninstall(self, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        if (self._fp_install_worker and self._fp_install_worker.isRunning()) or \
                (self._fp_uninstall_worker and self._fp_uninstall_worker.isRunning()):
            return
        reply = QMessageBox.question(
            self,
            f"Uninstall {name or app_id}",
            f"Remove {name or app_id}?\n\n{app_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        btn.setText("Uninstalling…")
        btn.setEnabled(False)
        self._fp_install_log.clear()
        self._fp_install_log.append(f"→ flatpak uninstall -y {app_id}\n")
        self._fp_install_log_toggle.show()
        _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, False)
        self._fp_progress.show()
        self._set_fp_task_state(f"Uninstalling {name or app_id}…", "running")
        self._fp_uninstall_worker = Worker(["flatpak", "uninstall", "-y", app_id])
        self._fp_uninstall_worker.line.connect(self._on_fp_uninstall_line)
        self._fp_uninstall_worker.done.connect(
            lambda code, aid=app_id, n=name, b=btn, ob=open_btn: self._on_fp_store_uninstall_done(code, aid, n, b, ob)
        )
        self._fp_uninstall_worker.start()

    def _on_fp_uninstall_line(self, ln: str):
        self._fp_install_log.append(ln)
        self._fp_install_log.ensureCursorVisible()

    def _on_fp_store_uninstall_done(self, code: int, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_uninstall_worker")
        if code == 0:
            self._set_fp_task_state(f"{name or app_id} uninstalled.", "success")
            self._fp_install_log.append("\nDone.")
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=False)
        else:
            self._set_fp_task_state(f"Uninstall failed (exit {code}).", "error")
            _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, True)
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=True)

    # ── Tab 2: AppImages ──────────────────────────────────────────────────────

    def _build_appimage_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        import_card = AppImageDropCard(self._import_appimage_path, self._set_appimage_icon_path)
        import_layout = QVBoxLayout(import_card)
        import_layout.setContentsMargins(24, 22, 24, 22)
        import_layout.setSpacing(16)

        import_top = QHBoxLayout()
        import_top.setSpacing(16)
        drop_glyph = QLabel("APP")
        drop_glyph.setObjectName("drop-glyph")
        drop_glyph.setFixedSize(58, 58)
        drop_glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        import_top.addWidget(drop_glyph)

        import_text = QVBoxLayout()
        import_text.setSpacing(5)
        import_title = QLabel("Import AppImages")
        import_title.setObjectName("drop-title")
        import_text.addWidget(import_title)
        import_body = QLabel(
            "Drop an AppImage here, or drop a PNG/SVG/JPG icon first. KythOS copies the app to ~/Applications, makes it executable, and can create a polished launcher."
        )
        import_body.setObjectName("card-copy")
        import_body.setWordWrap(True)
        import_text.addWidget(import_body)
        import_top.addLayout(import_text, 1)
        import_layout.addLayout(import_top)

        import_btn_row = QHBoxLayout()
        import_btn_row.setSpacing(10)
        self._ai_import_btn = QPushButton("Import .AppImage…")
        self._ai_import_btn.setObjectName("primary")
        self._ai_import_btn.clicked.connect(self._import_appimage)
        import_btn_row.addWidget(self._ai_import_btn)
        self._ai_icon_btn = QPushButton("Choose Icon…")
        self._ai_icon_btn.clicked.connect(self._choose_appimage_icon)
        import_btn_row.addWidget(self._ai_icon_btn)
        self._ai_icon_clear_btn = QPushButton("Clear Icon")
        self._ai_icon_clear_btn.clicked.connect(self._clear_appimage_icon)
        self._ai_icon_clear_btn.hide()
        import_btn_row.addWidget(self._ai_icon_clear_btn)
        import_btn_row.addStretch()
        import_layout.addLayout(import_btn_row)
        self._ai_icon_status = QLabel("No custom icon selected.")
        self._ai_icon_status.setObjectName("status-dim")
        import_layout.addWidget(self._ai_icon_status)
        self._ai_status = QLabel()
        self._ai_status.setObjectName("subheading")
        self._ai_status.hide()
        import_layout.addWidget(self._ai_status)
        layout.addWidget(import_card)

        curated_card, curated_layout = _make_card()
        curated_title = QLabel("Popular AppImages")
        curated_title.setObjectName("card-title")
        curated_layout.addWidget(curated_title)
        curated_body = QLabel(
            "Apps distributed only as AppImages. Download from their official site, "
            "then use Import above to register them in your app menu."
        )
        curated_body.setObjectName("card-copy")
        curated_body.setWordWrap(True)
        curated_layout.addWidget(curated_body)
        for entry in self._CURATED_APPIMAGES:
            row = QFrame()
            row.setObjectName("stat-tile")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            row_layout.setSpacing(12)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name_lbl = QLabel(entry["name"])
            name_lbl.setObjectName("card-summary")
            text_col.addWidget(name_lbl)
            desc_lbl = QLabel(entry["desc"])
            desc_lbl.setObjectName("card-copy")
            desc_lbl.setWordWrap(True)
            text_col.addWidget(desc_lbl)
            row_layout.addLayout(text_col, 1)
            dl_btn = QPushButton("Download Page")
            dl_btn.clicked.connect(
                lambda _=False, url=entry["url"]: QDesktopServices.openUrl(QUrl(url))
            )
            row_layout.addWidget(dl_btn)
            curated_layout.addWidget(row)
        layout.addWidget(curated_card)
        return tab

    def _import_appimage(self):
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Select AppImage",
            os.path.expanduser("~"),
            "AppImages (*.AppImage *.appimage);;All Files (*)",
        )
        if not src:
            return
        self._import_appimage_path(src)

    def _choose_appimage_icon(self):
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Select App Icon",
            os.path.expanduser("~"),
            "Images (*.png *.svg *.svgz *.jpg *.jpeg *.webp *.ico *.xpm);;All Files (*)",
        )
        if src:
            self._set_appimage_icon_path(src)

    def _set_appimage_icon_path(self, src: str):
        if not AppImageDropCard._is_icon_path(src) or not os.path.isfile(src):
            self._ai_icon_status.setText("That file does not look like a usable app icon.")
            self._ai_icon_status.setObjectName("status-warn")
            _restyle(self._ai_icon_status)
            return
        self._ai_icon_path = src
        self._ai_icon_status.setText(f"Icon ready: {os.path.basename(src)}")
        self._ai_icon_status.setObjectName("status-ok")
        self._ai_icon_clear_btn.show()
        _restyle(self._ai_icon_status)

    def _clear_appimage_icon(self):
        self._ai_icon_path = ""
        self._ai_icon_status.setText("No custom icon selected.")
        self._ai_icon_status.setObjectName("status-dim")
        self._ai_icon_clear_btn.hide()
        _restyle(self._ai_icon_status)

    def _import_appimage_path(self, src: str):
        if not re.search(r"\.[Aa]pp[Ii]mage$", src):
            self._ai_status.setText("That file does not look like an AppImage.")
            self._ai_status.setObjectName("status-warn")
            self._ai_status.show()
            _restyle(self._ai_status)
            return
        if not os.path.isfile(src):
            self._ai_status.setText("Dropped AppImage file was not found.")
            self._ai_status.setObjectName("status-err")
            self._ai_status.show()
            _restyle(self._ai_status)
            return
        apps_dir = os.path.expanduser("~/Applications")
        try:
            os.makedirs(apps_dir, exist_ok=True)
        except OSError as exc:
            self._ai_status.setText(f"Cannot create ~/Applications: {exc}")
            self._ai_status.setObjectName("status-err")
            self._ai_status.show()
            _restyle(self._ai_status)
            return

        basename = os.path.basename(src)
        dest = os.path.join(apps_dir, basename)
        if os.path.realpath(src) != os.path.realpath(dest):
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                self._ai_status.setText(f"Copy failed: {exc}")
                self._ai_status.setObjectName("status-err")
                self._ai_status.show()
                _restyle(self._ai_status)
                return
        try:
            os.chmod(dest, 0o700)  # nosemgrep
        except OSError:
            pass

        name = re.sub(r"\.[Aa]pp[Ii]mage$", "", basename)
        reply = QMessageBox.question(
            self,
            "Add to App Menu?",
            f"Add “{name}” to your application menu?\n\n"
            "This creates a launcher in ~/.local/share/applications/.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._create_appimage_launcher(name, dest, self._ai_icon_path)

        self._ai_status.setText(f"{name} imported to ~/Applications.")
        self._ai_status.setObjectName("status-ok")
        self._ai_status.show()
        _restyle(self._ai_status)
        self._clear_appimage_icon()

    def _create_appimage_launcher(self, name: str, appimage_path: str, icon_path: str = ""):
        desktop_dir = os.path.expanduser("~/.local/share/applications")
        try:
            os.makedirs(desktop_dir, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name)
            desktop_path = os.path.join(desktop_dir, f"{safe_name}.desktop")
            launcher_icon = "application-x-executable"
            if icon_path and os.path.isfile(icon_path):
                icon_dir = os.path.expanduser("~/.local/share/icons/kyth-appimages")
                os.makedirs(icon_dir, exist_ok=True)
                ext = os.path.splitext(icon_path)[1].lower() or ".png"
                icon_dest = os.path.join(icon_dir, f"{safe_name}{ext}")
                shutil.copy2(icon_path, icon_dest)
                launcher_icon = icon_dest
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={name}\n"
                f"Exec={appimage_path}\n"
                f"Icon={launcher_icon}\n"
                "Terminal=false\n"
                "Categories=Utility;\n"
            )
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(desktop_path, 0o600)
        except OSError:
            return
        for cmd in (
            ["update-desktop-database", desktop_dir],
            ["kbuildsycoca6", "--noincremental"],
        ):
            try:
                subprocess.run(cmd, capture_output=True, timeout=5, check=False)
            except Exception:
                pass

    # ── Tab 3: Installed ──────────────────────────────────────────────────────

    def _build_installed_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        intro = QLabel("Installed Flatpak apps and user AppImages.")
        intro.setObjectName("card-copy")
        top_row.addWidget(intro, 1)
        self._uninstall_refresh_btn = QPushButton("Refresh")
        self._uninstall_refresh_btn.clicked.connect(self._refresh_installed_list)
        top_row.addWidget(self._uninstall_refresh_btn)
        layout.addLayout(top_row)

        self._uninstall_status = QLabel()
        self._uninstall_status.setObjectName("subheading")
        layout.addWidget(self._uninstall_status)

        self._uninstall_progress = QProgressBar()
        self._uninstall_progress.setRange(0, 0)
        self._uninstall_progress.hide()
        layout.addWidget(self._uninstall_progress)

        self._uninstall_log_toggle = QPushButton("Show details")
        self._uninstall_log_toggle.setCheckable(True)
        self._uninstall_log_toggle.hide()
        layout.addWidget(self._uninstall_log_toggle)

        self._uninstall_log = QTextEdit()
        self._uninstall_log.document().setMaximumBlockCount(5000)
        self._uninstall_log.setReadOnly(True)
        self._uninstall_log.setMaximumHeight(130)
        self._uninstall_log.hide()
        layout.addWidget(self._uninstall_log)
        self._uninstall_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._uninstall_log_toggle, self._uninstall_log, checked)
        )

        self._uninstall_list = QVBoxLayout()
        self._uninstall_list.setSpacing(8)
        layout.addLayout(self._uninstall_list)

        self._refresh_installed_list()
        return tab

    def _refresh_installed_list(self, status_text: str | None = None, status_object: str = "subheading"):
        if self._uninstall_worker and self._uninstall_worker.isRunning():
            return
        self._clear_uninstall_list()
        apps = self._installed_flatpak_apps() + self._installed_appimage_apps()
        if not apps:
            self._uninstall_status.setText(status_text or "No removable Flatpak apps or AppImages found.")
            self._uninstall_status.setObjectName(status_object)
            _restyle(self._uninstall_status)
            return
        flatpak_count = sum(1 for app in apps if app["kind"] == "flatpak")
        appimage_count = sum(1 for app in apps if app["kind"] == "appimage")
        if not shutil.which("flatpak") and appimage_count == 0:
            self._uninstall_status.setText("Flatpak is not available and no AppImages were found.")
            self._uninstall_status.setObjectName("status-warn")
            _restyle(self._uninstall_status)
            return
        self._uninstall_status.setText(
            status_text or (
                f"{flatpak_count} Flatpak app{'s' if flatpak_count != 1 else ''} "
                f"and {appimage_count} AppImage{'s' if appimage_count != 1 else ''} found."
            )
        )
        self._uninstall_status.setObjectName(status_object)
        _restyle(self._uninstall_status)
        for app in apps:
            self._uninstall_list.addWidget(self._make_uninstall_app_row(app))

    def _clear_uninstall_list(self):
        while self._uninstall_list.count():
            item = self._uninstall_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._uninstall_buttons.clear()

    def _make_uninstall_app_row(self, app: dict[str, str]) -> QFrame:
        row = QFrame()
        row.setObjectName("stat-tile")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 10, 14, 10)
        row_layout.setSpacing(12)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(app["name"])
        name_lbl.setObjectName("card-summary")
        name_lbl.setWordWrap(True)
        text_col.addWidget(name_lbl)
        detail_lbl = QLabel(self._uninstall_app_detail(app))
        detail_lbl.setObjectName("card-copy")
        detail_lbl.setWordWrap(True)
        text_col.addWidget(detail_lbl)
        row_layout.addLayout(text_col, 1)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setObjectName("danger")
        uninstall_btn.clicked.connect(lambda _=False, a=app: self._uninstall_app(a))
        self._uninstall_buttons.append(uninstall_btn)
        row_layout.addWidget(uninstall_btn)
        return row

    def _uninstall_app_detail(self, app: dict[str, str]) -> str:
        if app["kind"] == "appimage":
            launcher = " · launcher" if app.get("desktop_path") else ""
            return f"{app['path']} · AppImage{launcher}"
        return f"{app['app_id']} · {app['installation']} install · {app['origin']}"

    def _set_uninstall_controls_enabled(self, enabled: bool):
        self._uninstall_refresh_btn.setEnabled(enabled)
        for btn in self._uninstall_buttons:
            btn.setEnabled(enabled)

    def _uninstall_app(self, app: dict[str, str]):
        if self._uninstall_worker and self._uninstall_worker.isRunning():
            return
        if app["kind"] == "appimage":
            self._uninstall_appimage_app(app)
        else:
            self._uninstall_flatpak_app(app)

    def _uninstall_flatpak_app(self, app: dict[str, str]):
        reply = QMessageBox.question(
            self,
            f"Uninstall {app['name']}",
            f"Remove {app['name']}?\n\n{app['app_id']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cmd = ["flatpak", "uninstall", "-y"]
        if app["installation"] == "user":
            cmd.append("--user")
        elif app["installation"] == "system":
            cmd.append("--system")
        cmd.append(app["app_id"])
        self._set_uninstall_controls_enabled(False)
        self._uninstall_log.clear()
        self._uninstall_log.append("→ " + " ".join(shlex.quote(part) for part in cmd) + "\n")
        self._uninstall_log_toggle.show()
        _set_log_panel(self._uninstall_log_toggle, self._uninstall_log, False)
        self._uninstall_progress.show()
        self._uninstall_status.setText(f"Uninstalling {app['name']}…")
        self._uninstall_status.setObjectName("subheading")
        _restyle(self._uninstall_status)
        self._uninstall_worker = Worker(cmd)
        self._uninstall_worker.line.connect(self._on_uninstall_line)
        self._uninstall_worker.done.connect(
            lambda code, name=app["name"]: self._on_uninstall_done(code, name)
        )
        self._uninstall_worker.start()

    def _uninstall_appimage_app(self, app: dict[str, str]):
        extra = "\nIts user application-menu launcher will also be removed." if app.get("desktop_path") else ""
        reply = QMessageBox.question(
            self,
            f"Uninstall {app['name']}",
            f"Delete this AppImage from your home folder?\n\n{app['path']}{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        targets = [app["path"]]
        if app.get("desktop_path"):
            targets.append(app["desktop_path"])
        safe_targets: list[str] = []
        for target in targets:
            real = os.path.realpath(os.path.expanduser(target))
            home = os.path.realpath(os.path.expanduser("~"))
            if real.startswith(home + os.sep):
                safe_targets.append(real)
        if not safe_targets:
            QMessageBox.warning(
                self,
                "Cannot uninstall AppImage",
                "This AppImage does not look like a user-owned file in your home folder.",
            )
            return
        cmd = [
            "bash", "-c",
            "set -euo pipefail\n"
            "for target in \"$@\"; do\n"
            "    if [[ -e \"$target\" || -L \"$target\" ]]; then\n"
            "        rm -f -- \"$target\"\n"
            "        echo \"Removed $target\"\n"
            "    fi\n"
            "done\n"
            "update-desktop-database \"$HOME/.local/share/applications\" 2>/dev/null || true\n"
            "kbuildsycoca6 --noincremental 2>/dev/null || true\n",
            "kyth-remove-appimage",
            *safe_targets,
        ]
        self._set_uninstall_controls_enabled(False)
        self._uninstall_log.clear()
        self._uninstall_log.append("→ remove AppImage and launcher\n")
        for target in safe_targets:
            self._uninstall_log.append(f"  {target}")
        self._uninstall_log_toggle.show()
        _set_log_panel(self._uninstall_log_toggle, self._uninstall_log, False)
        self._uninstall_progress.show()
        self._uninstall_status.setText(f"Uninstalling {app['name']}…")
        self._uninstall_status.setObjectName("subheading")
        _restyle(self._uninstall_status)
        self._uninstall_worker = Worker(cmd)
        self._uninstall_worker.line.connect(self._on_uninstall_line)
        self._uninstall_worker.done.connect(
            lambda code, name=app["name"]: self._on_uninstall_done(code, name)
        )
        self._uninstall_worker.start()

    def _on_uninstall_line(self, ln: str):
        self._uninstall_log.append(ln)
        self._uninstall_log.ensureCursorVisible()

    def _on_uninstall_done(self, code: int, name: str):
        self._uninstall_progress.hide()
        _finish_worker(self, attr="_uninstall_worker")
        self._set_uninstall_controls_enabled(True)
        if code == 0:
            self._uninstall_log.append("\nDone.")
            self._refresh_installed_list(f"{name} uninstalled.", "status-ok")
        else:
            self._uninstall_status.setText(f"Uninstall failed (exit {code}).")
            self._uninstall_status.setObjectName("status-err")
            _set_log_panel(self._uninstall_log_toggle, self._uninstall_log, True)
            _restyle(self._uninstall_status)

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _installed_flatpak_apps(self) -> list[dict[str, str]]:
        if not shutil.which("flatpak"):
            return []
        try:
            _en_env = {**os.environ, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
            result = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application,name,origin,installation"],
                capture_output=True, text=True, timeout=12, check=False,
                env=_en_env,
            )
        except Exception:
            return []
        apps: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            app_id, name, origin, installation = (part.strip() for part in parts[:4])
            if not app_id:
                continue
            apps.append({
                "kind": "flatpak",
                "app_id": app_id,
                "name": name or app_id,
                "origin": origin or "unknown",
                "installation": installation or "default",
            })
        return sorted(apps, key=lambda app: app["name"].casefold())

    def _appimage_search_dirs(self) -> list[str]:
        home = os.path.expanduser("~")
        return [
            os.path.join(home, "Applications"),
            os.path.join(home, ".local", "bin"),
            os.path.join(home, "bin"),
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
        ]

    def _path_is_user_appimage(self, path: str) -> bool:
        if not path:
            return False
        try:
            real = os.path.realpath(os.path.expanduser(path))
            home = os.path.realpath(os.path.expanduser("~"))
        except OSError:
            return False
        return (
            real.startswith(home + os.sep)
            and os.path.isfile(real)
            and os.path.basename(real).lower().endswith(".appimage")
        )

    def _desktop_entry_for_appimage(self, desktop_path: str) -> dict[str, str] | None:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        try:
            parser.read(desktop_path, encoding="utf-8")
        except Exception:
            return None
        if not parser.has_section("Desktop Entry"):
            return None
        entry = parser["Desktop Entry"]
        exec_line = entry.get("Exec", "")
        try_exec = entry.get("TryExec", "")
        candidates: list[str] = []
        for line in (exec_line, try_exec):
            if not line:
                continue
            try:
                parts = shlex.split(line)
            except ValueError:
                parts = line.split()
            candidates.extend(part for part in parts if ".AppImage" in part or ".appimage" in part)
        appimage_path = next((part for part in candidates if self._path_is_user_appimage(part)), "")
        if not appimage_path:
            return None
        appimage_path = os.path.realpath(os.path.expanduser(appimage_path))
        return {
            "kind": "appimage",
            "app_id": appimage_path,
            "name": entry.get("Name", "") or os.path.basename(appimage_path),
            "origin": "AppImage",
            "installation": "user file",
            "path": appimage_path,
            "desktop_path": desktop_path,
            "icon": entry.get("Icon", ""),
        }

    def _installed_appimage_apps(self) -> list[dict[str, str]]:
        apps_by_path: dict[str, dict[str, str]] = {}
        desktop_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
        for desktop_path in glob.glob(os.path.join(desktop_dir, "*.desktop")):
            app = self._desktop_entry_for_appimage(desktop_path)
            if app:
                apps_by_path[app["path"]] = app
        for directory in self._appimage_search_dirs():
            if not os.path.isdir(directory):
                continue
            try:
                entries = os.listdir(directory)
            except OSError:
                continue
            for name in entries:
                path = os.path.join(directory, name)
                if not self._path_is_user_appimage(path):
                    continue
                real = os.path.realpath(path)
                apps_by_path.setdefault(real, {
                    "kind": "appimage",
                    "app_id": real,
                    "name": os.path.basename(real),
                    "origin": "AppImage",
                    "installation": "user file",
                    "path": real,
                    "desktop_path": "",
                    "icon": "",
                })
        return sorted(apps_by_path.values(), key=lambda app: app["name"].casefold())

    def _open_terminal(self):
        for cmd in (["xdg-terminal-exec"], ["konsole"], ["xterm"]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd)
                    return
                except OSError:
                    pass

    # ── Tab 5: Developer ──────────────────────────────────────────────────────

    def _build_developer_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel("Developer Workstations")
        title.setObjectName("section-title")
        layout.addWidget(title)

        dev_card, dev_layout = _make_card()
        dev_title = QLabel("Kyth Dev Box")
        dev_title.setObjectName("card-title")
        dev_layout.addWidget(dev_title)

        dev_desc = QLabel(
            "Create a Fedora Toolbox-based Distrobox for mutable language tools while keeping the base OS atomic."
        )
        dev_desc.setWordWrap(True)
        dev_layout.addWidget(dev_desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._dev_setup_btn = QPushButton("Setup")
        self._dev_setup_btn.setObjectName("primary")
        self._dev_enter_btn = QPushButton("Enter")
        self._dev_delete_btn = QPushButton("Delete")
        self._dev_delete_btn.setObjectName("danger")
        self._dev_log_toggle = QPushButton("Show Log")
        self._dev_log_toggle.setCheckable(True)
        self._dev_enter_btn.clicked.connect(self._dev_enter_dev_box)
        self._dev_setup_btn.clicked.connect(self._dev_run_setup)
        self._dev_delete_btn.clicked.connect(self._dev_confirm_delete)
        for btn in (self._dev_setup_btn, self._dev_enter_btn, self._dev_delete_btn, self._dev_log_toggle):
            btn_row.addWidget(btn)
        btn_row.addStretch(1)
        dev_layout.addLayout(btn_row)

        self._dev_status_lbl = QLabel("Ready.")
        self._dev_status_lbl.setObjectName("status-muted")
        dev_layout.addWidget(self._dev_status_lbl)

        self._dev_progress = QProgressBar()
        self._dev_progress.setRange(0, 0)
        self._dev_progress.hide()
        dev_layout.addWidget(self._dev_progress)

        self._dev_log = QTextEdit()
        self._dev_log.document().setMaximumBlockCount(5000)
        self._dev_log.setReadOnly(True)
        self._dev_log.hide()
        dev_layout.addWidget(self._dev_log)
        self._dev_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._dev_log_toggle, self._dev_log, checked)
        )
        layout.addWidget(dev_card)

        ai_card, ai_layout = _make_card()
        ai_title = QLabel("AI Dev Environment")
        ai_title.setObjectName("card-title")
        ai_layout.addWidget(ai_title)

        ai_desc = QLabel(
            "Create an opt-in local AI developer Distrobox with Ollama, llama.cpp, Python, Node, Rust, and GPU diagnostics. Models are never downloaded automatically."
        )
        ai_desc.setWordWrap(True)
        ai_layout.addWidget(ai_desc)

        ai_btn_row = QHBoxLayout()
        ai_btn_row.setSpacing(10)
        self._ai_setup_btn = QPushButton("Setup")
        self._ai_setup_btn.setObjectName("primary")
        self._ai_status_btn = QPushButton("Status")
        self._ai_enter_btn = QPushButton("Enter")
        self._ai_start_btn = QPushButton("Start")
        self._ai_stop_btn = QPushButton("Stop")
        self._ai_delete_btn = QPushButton("Delete")
        self._ai_delete_btn.setObjectName("danger")
        self._ai_log_toggle = QPushButton("Show Log")
        self._ai_log_toggle.setCheckable(True)
        self._ai_setup_btn.clicked.connect(lambda _=False: self._ai_run("setup"))
        self._ai_status_btn.clicked.connect(lambda _=False: self._ai_run("status"))
        self._ai_enter_btn.clicked.connect(self._ai_enter_box)
        self._ai_start_btn.clicked.connect(lambda _=False: self._ai_run("start"))
        self._ai_stop_btn.clicked.connect(lambda _=False: self._ai_run("stop"))
        self._ai_delete_btn.clicked.connect(lambda _=False: self._ai_run("remove"))
        for btn in (
            self._ai_setup_btn,
            self._ai_status_btn,
            self._ai_enter_btn,
            self._ai_start_btn,
            self._ai_stop_btn,
            self._ai_delete_btn,
            self._ai_log_toggle,
        ):
            ai_btn_row.addWidget(btn)
        ai_btn_row.addStretch(1)
        ai_layout.addLayout(ai_btn_row)

        self._ai_status_lbl = QLabel("Ready.")
        self._ai_status_lbl.setObjectName("status-muted")
        ai_layout.addWidget(self._ai_status_lbl)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.hide()
        ai_layout.addWidget(self._ai_progress)

        self._ai_log = QTextEdit()
        self._ai_log.document().setMaximumBlockCount(5000)
        self._ai_log.setReadOnly(True)
        self._ai_log.hide()
        ai_layout.addWidget(self._ai_log)
        self._ai_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._ai_log_toggle, self._ai_log, checked)
        )
        layout.addWidget(ai_card)
        layout.addStretch(1)
        return page

    def _dev_run_setup(self):
        if self._dev_worker and self._dev_worker.isRunning():
            return
        self._dev_setup_btn.setEnabled(False)
        self._dev_log.clear()
        self._dev_log.append("→ bash dev-setup …\n")
        self._dev_log_toggle.show()
        _set_log_panel(self._dev_log_toggle, self._dev_log, False)
        self._dev_progress.show()
        self._dev_status_lbl.setText("Setting up dev environment…")
        self._dev_status_lbl.setObjectName("subheading")
        self._dev_status_lbl.show()
        _restyle(self._dev_status_lbl)
        self._dev_worker = Worker(_SETUP_DEV_BOX_CMD)
        self._dev_worker.line.connect(self._dev_on_line)
        self._dev_worker.done.connect(self._dev_on_done)
        self._dev_worker.start()

    def _dev_on_line(self, ln: str):
        self._dev_log.append(ln)
        self._dev_log.ensureCursorVisible()

    def _dev_on_done(self, code: int):
        self._dev_progress.hide()
        _finish_worker(self, attr="_dev_worker")
        self._dev_setup_btn.setEnabled(True)
        if code == 0:
            self._dev_status_lbl.setText("Dev environment ready.")
            self._dev_status_lbl.setObjectName("status-ok")
            self._dev_log.append("\nDone. Launch VS Code from the app menu, or click 'Enter Dev Box'.")
        else:
            self._dev_status_lbl.setText(f"Setup failed (exit code {code}).")
            self._dev_status_lbl.setObjectName("status-err")
            _set_log_panel(self._dev_log_toggle, self._dev_log, True)
        _restyle(self._dev_status_lbl)

    def _dev_confirm_delete(self):
        if self._dev_worker and self._dev_worker.isRunning():
            return
        if not _is_distrobox_container("kyth-dev"):
            QMessageBox.information(
                self, "Nothing to Delete",
                "The kyth-dev container does not exist.",
            )
            return

        first = QMessageBox.warning(
            self,
            "Delete Dev Environment?",
            "This will permanently delete the kyth-dev distrobox container.\n\n"
            "Everything inside the container will be lost:\n"
            "  •  All installed packages (git, just, podman, ripgrep, etc.)\n"
            "  •  Any tools you installed manually inside the container\n"
            "  •  Container-level configuration and state\n\n"
            "Your home directory is NOT affected — source code, dotfiles,\n"
            "and projects remain untouched.\n\n"
            "You can recreate it at any time with 'Set Up Dev Environment'.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if first != QMessageBox.StandardButton.Ok:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Confirm Permanent Deletion")
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setSpacing(12)
        dlg_layout.setContentsMargins(20, 20, 20, 20)

        warn_lbl = QLabel("Are you absolutely sure?")
        warn_lbl.setStyleSheet("color: #f7768e; font-size: 14px; font-weight: 700;")
        dlg_layout.addWidget(warn_lbl)

        detail = QLabel(
            "The kyth-dev container and every package inside it will be\n"
            "permanently removed. This cannot be undone.\n\n"
            "Type  DELETE  below to confirm:"
        )
        detail.setWordWrap(True)
        dlg_layout.addWidget(detail)

        confirm_edit = QLineEdit()
        confirm_edit.setPlaceholderText("DELETE")
        dlg_layout.addWidget(confirm_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Delete Forever")
        ok_btn.setObjectName("danger")
        ok_btn.setEnabled(False)
        _restyle(ok_btn)
        confirm_edit.textChanged.connect(
            lambda t: ok_btn.setEnabled(t.strip() == "DELETE")
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        dlg_layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._dev_run_delete()

    def _dev_run_delete(self):
        self._dev_setup_btn.setEnabled(False)
        self._dev_enter_btn.setEnabled(False)
        self._dev_delete_btn.setEnabled(False)
        self._dev_log.clear()
        self._dev_log.append("→ distrobox rm --force kyth-dev\n")
        self._dev_log_toggle.show()
        _set_log_panel(self._dev_log_toggle, self._dev_log, False)
        self._dev_progress.show()
        self._dev_status_lbl.setText("Deleting dev environment…")
        self._dev_status_lbl.setObjectName("subheading")
        self._dev_status_lbl.show()
        _restyle(self._dev_status_lbl)
        self._dev_worker = Worker(["distrobox", "rm", "--force", "kyth-dev"])
        self._dev_worker.line.connect(self._dev_on_line)
        self._dev_worker.done.connect(self._dev_on_delete_done)
        self._dev_worker.start()

    def _dev_on_delete_done(self, code: int):
        self._dev_progress.hide()
        _finish_worker(self, attr="_dev_worker")
        self._dev_setup_btn.setEnabled(True)
        self._dev_enter_btn.setEnabled(True)
        self._dev_delete_btn.setEnabled(True)
        if code == 0:
            self._dev_status_lbl.setText("Dev environment deleted.")
            self._dev_status_lbl.setObjectName("status-ok")
            self._dev_log.append("\nDone. Click 'Set Up Dev Environment' to recreate it.")
        else:
            self._dev_status_lbl.setText(f"Deletion failed (exit {code}).")
            self._dev_status_lbl.setObjectName("status-err")
            _set_log_panel(self._dev_log_toggle, self._dev_log, True)
        _restyle(self._dev_status_lbl)

    def _dev_enter_dev_box(self):
        if not _is_distrobox_container("kyth-dev"):
            QMessageBox.information(
                self,
                "Dev Box Not Found",
                "Create the KythOS development box first.",
            )
            return
        terminal = None
        for cmd in (["konsole"], ["xdg-terminal-exec"], ["xterm"]):
            if shutil.which(cmd[0]):
                terminal = cmd[0]
                break
        if terminal is None:
            QMessageBox.warning(self, "Terminal not found",
                                "Could not find a terminal emulator to open.")
            return
        if terminal == "konsole":
            subprocess.Popen(["konsole", "-e", "distrobox", "enter", "kyth-dev"])
        else:
            subprocess.Popen([terminal, "--", "distrobox", "enter", "kyth-dev"])

    def _ai_buttons(self):
        return tuple(
            btn for btn in (
                getattr(self, "_ai_setup_btn", None),
                getattr(self, "_ai_status_btn", None),
                getattr(self, "_ai_enter_btn", None),
                getattr(self, "_ai_start_btn", None),
                getattr(self, "_ai_stop_btn", None),
                getattr(self, "_ai_delete_btn", None),
            ) if btn is not None
        )

    def _ai_set_running(self, running: bool):
        for btn in self._ai_buttons():
            btn.setEnabled(not running)
        if hasattr(self, "_ai_progress"):
            self._ai_progress.setVisible(running)

    def _ai_run(self, action: str):
        if getattr(self, "_ai_worker", None) and self._ai_worker.isRunning():
            return
        if action == "remove":
            answer = QMessageBox.question(
                self,
                "Remove AI Dev Environment",
                "Remove the kyth-ai-dev Distrobox? Downloaded models in your home directory will be kept.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._ai_set_running(True)
        self._ai_status_lbl.setObjectName("status-muted")
        self._ai_status_lbl.setText(f"Running {action}...")
        self._ai_log.clear()
        command = ["/usr/bin/kyth-ai-dev", action]
        self._ai_worker = Worker(command)
        self._ai_worker.line.connect(self._ai_on_line)
        self._ai_worker.done.connect(lambda code: self._ai_on_done(action, code))
        self._ai_worker.start()

    def _ai_on_line(self, line: str):
        self._ai_log.append(line)

    def _ai_on_done(self, action: str, code: int):
        self._ai_set_running(False)
        ok = code == 0
        self._ai_status_lbl.setObjectName("status-ok" if ok else "status-err")
        if ok:
            labels = {
                "setup": "AI developer environment is ready.",
                "status": "Status check finished.",
                "start": "Local model service started.",
                "stop": "Local model service stopped.",
                "remove": "AI developer environment removed; models were left in your home directory.",
            }
            self._ai_status_lbl.setText(labels.get(action, "Finished."))
        else:
            self._ai_status_lbl.setText(f"{action.capitalize()} failed (exit code {code}).")
        _restyle(self._ai_status_lbl)

    def _ai_enter_box(self):
        try:
            subprocess.Popen(["konsole", "-e", "/usr/bin/kyth-ai-dev", "enter"])
        except Exception as exc:
            QMessageBox.warning(self, "AI Dev Environment", f"Could not open the AI dev shell:\n{exc}")

    # ── Tab 6: Security ───────────────────────────────────────────────────────

    def _build_security_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        kali_card, kali_layout = _make_card()

        top_row = QHBoxLayout()
        title_lbl = QLabel("Kali Linux Toolbox")
        title_lbl.setObjectName("card-title")
        top_row.addWidget(title_lbl)
        top_row.addStretch()
        self._sec_badge = QLabel()
        self._sec_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self._sec_badge)
        kali_layout.addLayout(top_row)

        desc = QLabel(
            "Creates a Kali Linux container via distrobox that shares your home directory. "
            "Choose a toolset below — the container image is shared regardless of tier."
        )
        desc.setObjectName("card-copy")
        desc.setWordWrap(True)
        kali_layout.addWidget(desc)

        self._sec_tool_group = QButtonGroup(self)
        self._sec_radio_headless = QRadioButton(
            "Headless  — kali-linux-headless  (~150 CLI tools: nmap, metasploit, hashcat, john, hydra, …)"
        )
        self._sec_radio_headless.setObjectName("card-copy")
        self._sec_radio_headless.setChecked(True)
        self._sec_radio_default = QRadioButton(
            "Default  — kali-linux-default  (headless + GUI tools: Zenmap, Autopsy, Faraday, legion, …)"
        )
        self._sec_radio_default.setObjectName("card-copy")
        self._sec_radio_everything = QRadioButton(
            "Everything  — kali-linux-everything  (every available Kali tool)"
        )
        self._sec_radio_everything.setObjectName("card-copy")
        for rb in (self._sec_radio_headless, self._sec_radio_default, self._sec_radio_everything):
            self._sec_tool_group.addButton(rb)
            kali_layout.addWidget(rb)

        self._sec_everything_warn = QLabel(
            "⚠  kali-linux-everything is extremely large — expect 15–20 GB or more of downloads "
            "and a very long install time. Only choose this if you need every available tool."
        )
        self._sec_everything_warn.setObjectName("card-copy")
        self._sec_everything_warn.setStyleSheet("color: #fbbf24; background: #241808; "
                                                "border: 1px solid #f59e0b; border-radius: 6px; "
                                                "padding: 6px 10px;")
        self._sec_everything_warn.setWordWrap(True)
        self._sec_everything_warn.hide()
        kali_layout.addWidget(self._sec_everything_warn)
        self._sec_radio_everything.toggled.connect(self._sec_everything_warn.setVisible)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._sec_create_btn = QPushButton("Create Kali Box")
        self._sec_create_btn.setObjectName("primary")
        self._sec_create_btn.clicked.connect(self._sec_create_box)
        btn_row.addWidget(self._sec_create_btn)
        self._sec_enter_btn = QPushButton("Launch Kali Terminal")
        self._sec_enter_btn.hide()
        self._sec_enter_btn.clicked.connect(self._sec_enter_box)
        btn_row.addWidget(self._sec_enter_btn)
        self._sec_export_btn = QPushButton("Export Apps to Menu")
        self._sec_export_btn.hide()
        self._sec_export_btn.clicked.connect(self._sec_export_apps)
        btn_row.addWidget(self._sec_export_btn)
        self._sec_remove_btn = QPushButton("Remove Box")
        self._sec_remove_btn.setObjectName("danger")
        self._sec_remove_btn.hide()
        self._sec_remove_btn.clicked.connect(self._sec_remove_box)
        btn_row.addWidget(self._sec_remove_btn)
        btn_row.addStretch()
        kali_layout.addLayout(btn_row)

        self._sec_status_lbl = QLabel()
        self._sec_status_lbl.setObjectName("subheading")
        self._sec_status_lbl.hide()
        kali_layout.addWidget(self._sec_status_lbl)

        self._sec_progress = QProgressBar()
        self._sec_progress.setRange(0, 100)
        self._sec_progress.setValue(0)
        self._sec_progress.hide()
        kali_layout.addWidget(self._sec_progress)

        self._sec_log_toggle = QPushButton("Show details")
        self._sec_log_toggle.setCheckable(True)
        self._sec_log_toggle.hide()
        self._sec_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._sec_log_toggle, self._sec_log, checked)
        )
        kali_layout.addWidget(self._sec_log_toggle)

        self._sec_log = QTextEdit()
        self._sec_log.document().setMaximumBlockCount(5000)
        self._sec_log.setReadOnly(True)
        self._sec_log.setMaximumHeight(150)
        self._sec_log.hide()
        kali_layout.addWidget(self._sec_log)

        layout.addWidget(kali_card)

        host_head = QLabel("Host-side Security Tools")
        host_head.setObjectName("heading")
        host_head.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        layout.addWidget(host_head)
        host_sub = QLabel(
            "These tools run natively on KythOS as Flatpaks — better Wayland integration "
            "and no container overhead for GUI-heavy workflows."
        )
        host_sub.setObjectName("card-copy")
        host_sub.setWordWrap(True)
        layout.addWidget(host_sub)

        self._sec_host_tool_refs = []
        for i in range(0, len(self._SEC_HOST_TOOLS), 2):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            for tool in self._SEC_HOST_TOOLS[i:i + 2]:
                tile, refs = self._make_sec_host_tool_tile(tool)
                row_layout.addWidget(tile, 1)
                self._sec_host_tool_refs.append(refs)
            if len(self._SEC_HOST_TOOLS[i:i + 2]) == 1:
                row_layout.addStretch(1)
            row_widget = QWidget()
            row_widget.setLayout(row_layout)
            layout.addWidget(row_widget)

        layout.addStretch()
        return tab

    def _refresh_sec_status(self):
        if not hasattr(self, "_sec_badge"):
            return
        installed = _is_socket_capable_kali_box(self._SEC_BOX_NAME)
        _apply_install_badge(self._sec_badge, installed,
                             ok_text="Installed", warn_text="Not Installed")
        self._sec_create_btn.setVisible(not installed)
        for rb in (self._sec_radio_headless, self._sec_radio_default, self._sec_radio_everything):
            rb.setVisible(not installed)
        self._sec_everything_warn.setVisible(not installed and self._sec_radio_everything.isChecked())
        self._sec_enter_btn.setVisible(installed)
        self._sec_export_btn.setVisible(installed)
        self._sec_remove_btn.setVisible(installed)

        for refs in self._sec_host_tool_refs:
            fp_installed = _is_flatpak_installed(refs["tool"]["flatpak"])
            refs["install"].setVisible(not fp_installed)
            refs["launch"].setVisible(fp_installed)
            refs["uninstall"].setVisible(fp_installed)

    def _sec_create_box(self):
        if self._sec_worker and self._sec_worker.isRunning():
            return

        if self._sec_radio_everything.isChecked():
            meta = "kali-linux-everything"
        elif self._sec_radio_default.isChecked():
            meta = "kali-linux-default"
        else:
            meta = "kali-linux-headless"
        self._sec_last_install_meta = meta
        has_gui = meta in ("kali-linux-default", "kali-linux-everything")

        self._sec_create_btn.setEnabled(False)
        for rb in (self._sec_radio_headless, self._sec_radio_default, self._sec_radio_everything):
            rb.setEnabled(False)
        self._sec_log.clear()
        sudo_note = (
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- configure passwordless sudo\n"
        )
        export_note = (
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- distrobox-export (bulk GUI apps)\n"
            "→ kbuildsycoca6 (refresh KDE application menu)\n"
        ) if has_gui else ""
        size_note = (
            "\n⚠ kali-linux-everything is very large — this may take a long time.\n"
        ) if meta == "kali-linux-everything" else (
            "\nThis pulls the Kali container image and installs the tool metapackage.\n"
            "The first run will take a few minutes depending on your connection.\n"
        )
        self._sec_log.append(
            f"→ distrobox create --root --image {self._SEC_BOX_IMAGE} --name {self._SEC_BOX_NAME}"
            f" --additional-flags '--privileged --security-opt label=disable'\n"
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- noninteractive apt-get install -y {meta}\n"
            + sudo_note + export_note + size_note
        )
        self._sec_log_toggle.show()
        _set_log_panel(self._sec_log_toggle, self._sec_log, False)
        self._sec_progress.setRange(0, 100)
        self._sec_progress.setValue(2)
        self._sec_progress.show()
        self._sec_status_lbl.setText("Pulling Kali container image…")
        self._sec_status_lbl.setObjectName("subheading")
        self._sec_status_lbl.show()
        _restyle(self._sec_status_lbl)
        self._sec_install_phase = 0
        self._sec_total_packages = 0
        self._sec_unpack_count = 0
        self._sec_setup_count = 0

        export_step = (
            f" && distrobox enter --root {self._SEC_BOX_NAME} --"
            r" bash -c 'for f in /usr/share/applications/*.desktop;"
            r" do app=$(basename $f .desktop);"
            r" distrobox-export --app $app 2>/dev/null || true; done'"
            "\n_d=\"$HOME/.local/share/applications\"\n"
            "for _f in \"$_d/\"*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali' \"$_f\" 2>/dev/null || continue\n"
            "    if grep -q '^Categories=' \"$_f\"; then\n"
            "        sed -i 's|^Categories=.*|Categories=X-KythSecurity;|' \"$_f\"\n"
            "    else\n"
            "        printf '\\nCategories=X-KythSecurity;\\n' >> \"$_f\"\n"
            "    fi\n"
            "    sed -i '/^NoDisplay[[:space:]]*=[[:space:]]*true/Id' \"$_f\"\n"
            "    sed -i '/^OnlyShowIn[[:space:]]*=/d' \"$_f\"\n"
            "    sed -i '/^NotShowIn[[:space:]]*=/d' \"$_f\"\n"
            "    if grep -qE 'pkexec|kdesu|gksu|gksudo' \"$_f\" 2>/dev/null; then\n"
            "        sed -i -E 's/(pkexec|kdesu|gksu|gksudo)[[:space:]]+/sudo -E /g' \"$_f\"\n"
            "    fi\n"
            "done\n"
            "for _f in \"$_d/\"*zenmap*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali' \"$_f\" 2>/dev/null || continue\n"
            "    grep -qiE '^Name=.*root|zenmap-root|su-to-zenmap|pkexec' \"$_f\" 2>/dev/null || continue\n"
            "    grep -q ' sudo ' \"$_f\" && continue\n"
            "    sed -i -E 's|[[:space:]]--[[:space:]]+| -- sudo -E |' \"$_f\"\n"
            "done\n"
            "for _f in \"$_d/\"*zenmap*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali|^Exec=.*sudo -E' \"$_f\" 2>/dev/null || continue\n"
            "    grep -qiE '^Name=.*root|zenmap-root|su-to-zenmap|pkexec|sudo -E' \"$_f\" 2>/dev/null || continue\n"
            "    sed -i -E 's|^Exec=.*$|Exec=kyth-distrobox-root-launch --root kali /usr/bin/zenmap|' \"$_f\"\n"
            "    sed -i -E 's|^TryExec=.*$|TryExec=kyth-distrobox-root-launch|' \"$_f\"\n"
            "done\n"
            "update-desktop-database \"$_d\" 2>/dev/null || true\n"
            "kbuildsycoca6 --noincremental 2>/dev/null || true"
        ) if has_gui else ""
        cmd = [
            "bash", "-c",
            "set -euo pipefail\n"
            f"box={self._SEC_BOX_NAME!r}\n"
            f"image={self._SEC_BOX_IMAGE!r}\n"
            "rootless_exists=0\n"
            "distrobox list --no-color 2>/dev/null | grep -q \"^${box}\\b\" && rootless_exists=1 || true\n"
            "if [[ \"${rootless_exists}\" -eq 1 ]]; then\n"
            "    echo \"Removing rootless ${box}; raw socket tools require a rootful Kali box...\"\n"
            "    distrobox stop \"${box}\" --yes 2>/dev/null || distrobox stop \"${box}\" 2>/dev/null || true\n"
            "    distrobox rm --force \"${box}\" 2>/dev/null || distrobox rm \"${box}\" --yes 2>/dev/null || true\n"
            "    podman rm -f \"${box}\" 2>/dev/null || true\n"
            "fi\n"
            "rootful_exists=0\n"
            "sudo -A podman inspect \"${box}\" >/dev/null 2>&1 && rootful_exists=1 || true\n"
            "if [[ \"${rootful_exists}\" -eq 1 ]]; then\n"
            "    _image=$(sudo -A podman inspect \"${box}\" --format '{{.ImageName}}' 2>/dev/null || true)\n"
            "    _privileged=$(sudo -A podman inspect \"${box}\" --format '{{.HostConfig.Privileged}}' 2>/dev/null || true)\n"
            "    _security_opts=$(sudo -A podman inspect \"${box}\" --format '{{range .HostConfig.SecurityOpt}}{{.}} {{end}}' 2>/dev/null || true)\n"
            "    if [[ \"${_image}\" != *kali* ]] || [[ \"${_privileged}\" != \"true\" ]] || [[ \"${_security_opts}\" != *label=disable* ]]; then\n"
            "        echo \"Recreating ${box} with privileged rootful networking and SELinux label disabled...\"\n"
            "        distrobox stop --root \"${box}\" --yes 2>/dev/null || distrobox stop --root \"${box}\" 2>/dev/null || true\n"
            "        distrobox rm --root --force \"${box}\" 2>/dev/null || distrobox rm --root \"${box}\" --yes 2>/dev/null || true\n"
            "        sudo -A podman rm -f \"${box}\" 2>/dev/null || true\n"
            "        rootful_exists=0\n"
            "    fi\n"
            "fi\n"
            "if [[ \"${rootful_exists}\" -eq 0 ]]; then\n"
            "    distrobox create --root --image \"${image}\" --name \"${box}\" --yes"
            " --additional-flags '--privileged --security-opt label=disable'\n"
            "fi\n"
            f"distrobox enter --root {self._SEC_BOX_NAME} -- bash -c \""
            "export DEBIAN_FRONTEND=noninteractive; "
            "(printf '%s\\n' "
            "'popularity-contest popularity-contest/participate boolean false' "
            "'encfs encfs/security-information boolean true' "
            "'encfs encfs/security-information seen true' "
            "'console-setup console-setup/charmap47 select UTF-8' "
            "'samba-common samba-common/dhcp boolean false' "
            "'macchanger macchanger/automatically_run boolean false' "
            "'kismet-capture-common kismet-capture-common/install-users string' "
            "'kismet-capture-common kismet-capture-common/install-setuid boolean true' "
            "'wireshark-common wireshark-common/install-setuid boolean true' "
            "'sslh sslh/inetd_or_standalone select standalone' "
            "| sudo debconf-set-selections) || true; "
            "sudo -E apt-get install -y "
            "-o Dpkg::Options::=--force-confdef "
            "-o Dpkg::Options::=--force-confold "
            f"{meta}\""
            f" && distrobox enter --root {self._SEC_BOX_NAME} -- bash -c \""
            "echo '${USER} ALL=(root) NOPASSWD: ALL' "
            "| sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null; "
            "sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd; "
            "mkdir -p /root/.config/gtk-3.0; "
            "printf '[Settings]\\ngtk-icon-theme-name = hicolor\\n' > /root/.config/gtk-3.0/settings.ini; "
            "if command -v nmap >/dev/null 2>&1; then "
            "printf '#!/bin/sh\\nexec sudo /usr/bin/nmap \\\"\\$@\\\"\\n' | sudo tee /usr/local/bin/nmap > /dev/null; "
            "sudo chmod 755 /usr/local/bin/nmap; fi\""
            + export_step,
        ]
        self._sec_worker = Worker(cmd)
        self._sec_worker.line.connect(self._sec_on_create_line)
        self._sec_worker.done.connect(self._sec_on_create_done)
        self._sec_worker.start()

    def _sec_on_create_line(self, ln: str):
        self._sec_log.append(ln)
        self._sec_log.ensureCursorVisible()

        lo = ln.lower()
        phase = self._sec_install_phase

        if phase <= 1:
            if any(k in lo for k in (
                "trying to pull", "pulling image", "getting image source",
                "copying blob", "copying config",
            )):
                self._sec_install_phase = 1
                if "copying blob" in lo:
                    digest = ln.split()[-1] if ln.split() else ""
                    short = digest[:19] if digest else ""
                    msg = f"Pulling image layer {short}…" if short else "Pulling Kali image layers…"
                elif "copying config" in lo:
                    msg = "Pulling image config…"
                else:
                    msg = "Pulling kalilinux/kali-rolling from registry…"
                self._sec_status_lbl.setText(msg)
                _restyle(self._sec_status_lbl)
                cur = self._sec_progress.value()
                if cur < 40:
                    self._sec_progress.setValue(cur + 1)
                return
            if "writing manifest" in lo or "storing signatures" in lo:
                self._sec_install_phase = 1
                self._sec_status_lbl.setText("Storing image manifest…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(42)
                return
            if any(k in lo for k in (
                "container kali", "creating container", "starting container",
                "image is now available", "image already present",
            )) or (phase == 1 and "distrobox" in lo and "creat" in lo):
                self._sec_install_phase = 2
                self._sec_status_lbl.setText("Creating Kali distrobox container…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 44))
                return

        if phase == 2:
            if any(k in lo for k in ("installing basic", "bootstrapping", "reading package")):
                self._sec_install_phase = 3
                self._sec_status_lbl.setText("Bootstrapping Kali environment…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 55))
            else:
                cur = self._sec_progress.value()
                if cur < 54:
                    self._sec_progress.setValue(cur + 1)
            return

        if phase == 3:
            if any(k in lo for k in ("reading package lists", "building dependency",
                                     "reading state information")):
                self._sec_status_lbl.setText("Fetching Kali package lists…")
                _restyle(self._sec_status_lbl)
                cur = self._sec_progress.value()
                if cur < 59:
                    self._sec_progress.setValue(cur + 1)
            elif any(k in lo for k in ("following new package", "following additional",
                                       "will be installed")):
                self._sec_status_lbl.setText("Resolving package dependencies…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 58))
            m = re.search(r'(\d+) newly installed', ln)
            if m:
                self._sec_total_packages = int(m.group(1))
            m2 = re.search(r'Need to get (.+?) of archives', ln, re.IGNORECASE)
            if m2:
                self._sec_install_phase = 4
                size_str = m2.group(1)
                count_str = f" ({self._sec_total_packages} packages)" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(f"Downloading {size_str} of packages{count_str}…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 60))
            elif "need to get" in lo and "archive" in lo:
                self._sec_install_phase = 4
                self._sec_status_lbl.setText("Downloading packages…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 60))
            return

        if phase == 4:
            m = re.match(r'Get:(\d+)\s+\S+\s+\S+\s+\S+\s+(\S+)', ln)
            if m:
                n = int(m.group(1))
                pkg = m.group(2)
                if self._sec_total_packages > 0:
                    frac = min(1.0, n / self._sec_total_packages)
                    self._sec_progress.setValue(max(self._sec_progress.value(),
                                                   int(60 + frac * 15)))
                    self._sec_status_lbl.setText(
                        f"Downloading {pkg}… ({n} / {self._sec_total_packages})"
                    )
                else:
                    cur = self._sec_progress.value()
                    if cur < 74:
                        self._sec_progress.setValue(cur + 1)
                    self._sec_status_lbl.setText(f"Downloading {pkg}…")
                _restyle(self._sec_status_lbl)
            if ln.startswith("Selecting previously") or ln.startswith("Preparing to unpack"):
                self._sec_install_phase = 5
                total_str = f" / {self._sec_total_packages}" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(f"Unpacking packages… (0{total_str})")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 75))
            return

        if phase == 5:
            if ln.startswith("Unpacking "):
                self._sec_unpack_count += 1
                pkg = ln.split()[1] if len(ln.split()) > 1 else ""
                pkg = pkg.split(":")[0]
                total_str = f" / {self._sec_total_packages}" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(
                    f"Unpacking {pkg}… ({self._sec_unpack_count}{total_str})"
                )
                _restyle(self._sec_status_lbl)
                if self._sec_total_packages > 0:
                    frac = min(1.0, self._sec_unpack_count / self._sec_total_packages)
                    self._sec_progress.setValue(max(self._sec_progress.value(),
                                                   int(75 + frac * 13)))
                else:
                    cur = self._sec_progress.value()
                    if cur < 87:
                        self._sec_progress.setValue(cur + 1)
            if ln.startswith("Setting up "):
                self._sec_install_phase = 6
                pkg = ln.split()[2] if len(ln.split()) > 2 else ""
                pkg = pkg.split(":")[0]
                self._sec_setup_count = 1
                total_str = f" / {self._sec_total_packages}" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(f"Configuring {pkg}… (1{total_str})")
                _restyle(self._sec_status_lbl)
                if self._sec_total_packages > 0:
                    frac = min(1.0, 1 / self._sec_total_packages)
                    self._sec_progress.setValue(max(self._sec_progress.value(),
                                                   int(88 + frac * 10)))
                else:
                    self._sec_progress.setValue(max(self._sec_progress.value(), 88))
            return

        if phase == 6:
            if ln.startswith("Setting up "):
                self._sec_setup_count += 1
                pkg = ln.split()[2] if len(ln.split()) > 2 else ""
                pkg = pkg.split(":")[0]
                total_str = f" / {self._sec_total_packages}" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(
                    f"Configuring {pkg}… ({self._sec_setup_count}{total_str})"
                )
                _restyle(self._sec_status_lbl)
                if self._sec_total_packages > 0:
                    frac = min(1.0, self._sec_setup_count / self._sec_total_packages)
                    self._sec_progress.setValue(max(self._sec_progress.value(),
                                                   int(88 + frac * 10)))
                else:
                    cur = self._sec_progress.value()
                    if cur < 97:
                        self._sec_progress.setValue(cur + 1)
            if "processing triggers" in lo:
                pkg_m = re.search(r'processing triggers for (\S+)', lo)
                trigger_pkg = pkg_m.group(1) if pkg_m else ""
                msg = f"Running post-install triggers ({trigger_pkg})…" if trigger_pkg else "Running post-install triggers…"
                self._sec_status_lbl.setText(msg)
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 98))

    def _sec_on_create_done(self, code: int):
        self._sec_progress.setValue(100)
        self._sec_progress.hide()
        _finish_worker(self, attr="_sec_worker")
        self._sec_create_btn.setEnabled(True)
        for rb in (self._sec_radio_headless, self._sec_radio_default, self._sec_radio_everything):
            rb.setEnabled(True)
        if code == 0:
            meta = getattr(self, "_sec_last_install_meta", "kali-linux-headless")
            if meta in ("kali-linux-default", "kali-linux-everything"):
                self._sec_status_lbl.setText(
                    "Kali box created. GUI apps exported — check your application menu."
                )
            else:
                self._sec_status_lbl.setText("Kali box created. Launch a terminal to start hacking.")
            self._sec_status_lbl.setObjectName("status-ok")
            self._sec_log.append("\nDone.")
        else:
            self._sec_status_lbl.setText(f"Setup failed (exit {code}). Check the details below.")
            self._sec_status_lbl.setObjectName("status-err")
        _restyle(self._sec_status_lbl)
        self._refresh_sec_status()

    def _sec_enter_box(self):
        terminal = None
        for cmd in (["konsole"], ["xdg-terminal-exec"], ["xterm"]):
            if shutil.which(cmd[0]):
                terminal = cmd[0]
                break
        if terminal is None:
            QMessageBox.warning(self, "Terminal not found",
                                "Could not find a terminal emulator to open.")
            return
        if terminal == "konsole":
            subprocess.Popen(["konsole", "-e", "distrobox", "enter", "--root", self._SEC_BOX_NAME])
        else:
            subprocess.Popen([terminal, "--", "distrobox", "enter", "--root", self._SEC_BOX_NAME])

    def _sec_export_apps(self):
        if self._sec_worker and self._sec_worker.isRunning():
            return
        self._sec_export_count = 0
        self._sec_export_btn.setEnabled(False)
        self._sec_enter_btn.setEnabled(False)
        self._sec_remove_btn.setEnabled(False)
        self._sec_log.clear()
        self._sec_log.append(
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- distrobox-export (bulk GUI apps)\n"
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- configure passwordless sudo\n"
            "→ kbuildsycoca6 (refresh KDE application menu)\n\n"
            "Scanning Kali container for GUI apps…\n"
        )
        self._sec_log_toggle.show()
        _set_log_panel(self._sec_log_toggle, self._sec_log, False)
        self._sec_progress.show()
        self._sec_status_lbl.setText("Scanning for GUI apps…")
        self._sec_status_lbl.setObjectName("subheading")
        self._sec_status_lbl.show()
        _restyle(self._sec_status_lbl)

        cmd = [
            "bash", "-c",
            f"distrobox enter --root {self._SEC_BOX_NAME} --"
            r" bash -c '"
            r"shopt -s nullglob; files=(/usr/share/applications/*.desktop);"
            r" if [ ${#files[@]} -eq 0 ]; then exit 2; fi;"
            r" n=0; for f in ${files[@]}; do"
            r"   app=$(basename $f .desktop);"
            r"   distrobox-export --app $app 2>&1 && n=$((n+1)) || echo skip: $app;"
            r" done; echo EXPORTED:$n'"
            "\n_rc=$?; [ \"$_rc\" -eq 2 ] && exit 2\n"
            f"distrobox enter --root {self._SEC_BOX_NAME} -- bash -c \""
            "echo '${USER} ALL=(root) NOPASSWD: ALL' "
            "| sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null; "
            "sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd\"\n"
            "_d=\"$HOME/.local/share/applications\"\n"
            "for _f in \"$_d/\"*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali' \"$_f\" 2>/dev/null || continue\n"
            "    if grep -q '^Categories=' \"$_f\"; then\n"
            "        sed -i 's|^Categories=.*|Categories=X-KythSecurity;|' \"$_f\"\n"
            "    else\n"
            "        printf '\\nCategories=X-KythSecurity;\\n' >> \"$_f\"\n"
            "    fi\n"
            "    sed -i '/^NoDisplay[[:space:]]*=[[:space:]]*true/Id' \"$_f\"\n"
            "    sed -i '/^OnlyShowIn[[:space:]]*=/d' \"$_f\"\n"
            "    sed -i '/^NotShowIn[[:space:]]*=/d' \"$_f\"\n"
            "    if grep -qE 'pkexec|kdesu|gksu|gksudo' \"$_f\" 2>/dev/null; then\n"
            "        sed -i -E 's/(pkexec|kdesu|gksu|gksudo)[[:space:]]+/sudo -E /g' \"$_f\"\n"
            "    fi\n"
            "done\n"
            "for _f in \"$_d/\"*zenmap*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali' \"$_f\" 2>/dev/null || continue\n"
            "    grep -qiE '^Name=.*root|zenmap-root|su-to-zenmap|pkexec' \"$_f\" 2>/dev/null || continue\n"
            "    grep -q ' sudo ' \"$_f\" && continue\n"
            "    sed -i -E 's|[[:space:]]--[[:space:]]+| -- sudo -E |' \"$_f\"\n"
            "done\n"
            "for _f in \"$_d/\"*zenmap*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali|^Exec=.*sudo -E' \"$_f\" 2>/dev/null || continue\n"
            "    grep -qiE '^Name=.*root|zenmap-root|su-to-zenmap|pkexec|sudo -E' \"$_f\" 2>/dev/null || continue\n"
            "    sed -i -E 's|^Exec=.*$|Exec=kyth-distrobox-root-launch --root kali /usr/bin/zenmap|' \"$_f\"\n"
            "    sed -i -E 's|^TryExec=.*$|TryExec=kyth-distrobox-root-launch|' \"$_f\"\n"
            "done\n"
            "update-desktop-database \"$_d\" 2>/dev/null || true\n"
            "kbuildsycoca6 --noincremental 2>/dev/null || true",
        ]
        self._sec_worker = Worker(cmd)
        self._sec_worker.line.connect(self._sec_on_export_line)
        self._sec_worker.done.connect(self._sec_on_export_done)
        self._sec_worker.start()

    def _sec_on_export_line(self, ln: str):
        if ln.startswith("EXPORTED:"):
            try:
                self._sec_export_count = int(ln.split(":", 1)[1].strip())
            except ValueError:
                pass
        else:
            self._sec_log.append(ln)
            self._sec_log.ensureCursorVisible()

    def _sec_on_export_done(self, code: int):
        self._sec_progress.hide()
        _finish_worker(self, attr="_sec_worker")
        self._sec_export_btn.setEnabled(True)
        self._sec_enter_btn.setEnabled(True)
        self._sec_remove_btn.setEnabled(True)
        if code == 2:
            self._sec_status_lbl.setText(
                "No GUI apps found. kali-linux-headless only includes CLI tools. "
                "Re-create the box with 'Default' or 'Everything' to get exportable GUI apps."
            )
            self._sec_status_lbl.setObjectName("status-err")
            self._sec_log.append(
                "\nNo .desktop files found inside the Kali container.\n"
                "kali-linux-headless does not ship GUI apps — there is nothing to export.\n"
                "To get GUI apps (Zenmap, Autopsy, Faraday, etc.), remove this box and\n"
                "re-create it with the 'Default' or 'Everything' tier."
            )
        elif code == 0:
            n = getattr(self, "_sec_export_count", 0)
            if n == 0:
                self._sec_status_lbl.setText(
                    "No GUI apps exported. kali-linux-headless contains CLI tools only — "
                    "remove this box and re-create it with 'Default' or 'Everything' "
                    "to get exportable GUI apps (Zenmap, Autopsy, Faraday, etc.)."
                )
                self._sec_status_lbl.setObjectName("status-err")
                _set_log_panel(self._sec_log_toggle, self._sec_log, True)
            else:
                self._sec_status_lbl.setText(
                    f"Exported {n} app(s) — they should appear in your application menu shortly. "
                    "If you don't see them, try logging out and back in."
                )
                self._sec_status_lbl.setObjectName("status-ok")
            self._sec_log.append("\nDone.")
        else:
            self._sec_status_lbl.setText(f"Export failed (exit {code}). Check the details below.")
            self._sec_status_lbl.setObjectName("status-err")
        _restyle(self._sec_status_lbl)

    def _sec_remove_box(self):
        if self._sec_worker and self._sec_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, "Remove Kali Box",
            "Remove the Kali distrobox container?\n\nFiles in your home directory are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._sec_enter_btn.setEnabled(False)
        self._sec_remove_btn.setEnabled(False)
        self._sec_log.clear()
        self._sec_log.append(
            f"→ distrobox stop/rm {self._SEC_BOX_NAME} (rootless and rootful)\n"
            "→ verify removal and clean exported launchers\n"
        )
        self._sec_log_toggle.show()
        _set_log_panel(self._sec_log_toggle, self._sec_log, False)
        self._sec_progress.show()
        self._sec_status_lbl.setText("Stopping and removing Kali box…")
        self._sec_status_lbl.setObjectName("subheading")
        self._sec_status_lbl.show()
        _restyle(self._sec_status_lbl)

        remove_script = f"""
set -euo pipefail
box={self._SEC_BOX_NAME!r}
appdir="${{HOME}}/.local/share/applications"

echo "Stopping ${{box}} if it is running..."
distrobox stop "${{box}}" --yes 2>/dev/null \
    || distrobox stop "${{box}}" 2>/dev/null \
    || true
distrobox stop --root "${{box}}" --yes 2>/dev/null \
    || distrobox stop --root "${{box}}" 2>/dev/null \
    || true

echo "Removing ${{box}}..."
distrobox rm --force "${{box}}" \
    || distrobox rm "${{box}}" --yes \
    || true
distrobox rm --root --force "${{box}}" 2>/dev/null \
    || distrobox rm --root "${{box}}" --yes 2>/dev/null \
    || true

if distrobox list --no-color 2>/dev/null | grep -q "^${{box}}\\b" \
    || sudo -A podman inspect "${{box}}" >/dev/null 2>&1; then
    echo "Distrobox still lists ${{box}}; forcing backend container removal..."
    if command -v podman >/dev/null 2>&1; then
        podman rm -f "${{box}}" 2>/dev/null || true
        sudo -A podman rm -f "${{box}}" 2>/dev/null || true
    fi
    if command -v docker >/dev/null 2>&1; then
        docker rm -f "${{box}}" 2>/dev/null || true
    fi
fi

if distrobox list --no-color 2>/dev/null | grep -q "^${{box}}\\b" \
    || sudo -A podman inspect "${{box}}" >/dev/null 2>&1; then
    echo "ERROR: ${{box}} still exists after removal attempts." >&2
    exit 1
fi

if [[ -d "${{appdir}}" ]]; then
    removed=0
    while IFS= read -r -d "" f; do
        if grep -qE -- "--name[[:space:]]+${{box}}|-n[[:space:]]+${{box}}|kyth-distrobox-root-launch[[:space:]]+${{box}}\\b" "$f" 2>/dev/null; then
            rm -f "$f"
            removed=$((removed + 1))
        fi
    done < <(find "${{appdir}}" -maxdepth 1 -type f -name "*.desktop" -print0)
    echo "Removed ${{removed}} exported launcher(s)."
fi

update-desktop-database "${{appdir}}" 2>/dev/null || true
kbuildsycoca6 --noincremental 2>/dev/null || true
echo "Kali box is stopped and removed."
"""
        self._sec_worker = Worker(["bash", "-c", remove_script])
        self._sec_worker.line.connect(lambda ln: (
            self._sec_log.append(ln),
            self._sec_log.ensureCursorVisible(),
        ))
        self._sec_worker.done.connect(self._sec_on_remove_done)
        self._sec_worker.start()

    def _sec_on_remove_done(self, code: int):
        self._sec_progress.hide()
        _finish_worker(self, attr="_sec_worker")
        self._sec_enter_btn.setEnabled(True)
        self._sec_remove_btn.setEnabled(True)
        if code == 0:
            self._sec_status_lbl.setText("Kali box removed.")
            self._sec_status_lbl.setObjectName("status-ok")
            self._sec_log.append("\nDone.")
        else:
            self._sec_status_lbl.setText(f"Removal failed (exit {code}).")
            self._sec_status_lbl.setObjectName("status-err")
        _restyle(self._sec_status_lbl)
        self._refresh_sec_status()

    def _make_sec_host_tool_tile(self, tool: dict) -> tuple[QFrame, dict]:
        card, layout = _make_card()
        layout.setSpacing(8)
        name_lbl = QLabel(tool["name"])
        name_lbl.setObjectName("card-title")
        layout.addWidget(name_lbl)
        desc_lbl = QLabel(tool["desc"])
        desc_lbl.setObjectName("card-copy")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        install_btn = QPushButton("Install")
        install_btn.setObjectName("primary")
        install_btn.clicked.connect(lambda _=False, t=tool: self._sec_install_host_tool(t))
        btn_row.addWidget(install_btn)
        launch_btn = QPushButton("Launch")
        launch_btn.hide()
        launch_btn.clicked.connect(
            lambda _=False, cmd=tool["launch"]: subprocess.Popen(cmd)
        )
        btn_row.addWidget(launch_btn)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setObjectName("danger")
        uninstall_btn.hide()
        uninstall_btn.clicked.connect(lambda _=False, t=tool: self._sec_uninstall_host_tool(t))
        btn_row.addWidget(uninstall_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        status_lbl = QLabel()
        status_lbl.setObjectName("subheading")
        status_lbl.hide()
        layout.addWidget(status_lbl)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.hide()
        layout.addWidget(progress)

        log_toggle = QPushButton("Show details")
        log_toggle.setCheckable(True)
        log_toggle.hide()
        layout.addWidget(log_toggle)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setMaximumHeight(100)
        log.hide()
        layout.addWidget(log)

        log_toggle.clicked.connect(
            lambda checked, lt=log_toggle, lg=log: _set_log_panel(lt, lg, checked)
        )

        refs = {
            "tool": tool, "install": install_btn, "launch": launch_btn,
            "uninstall": uninstall_btn, "status": status_lbl,
            "progress": progress, "log_toggle": log_toggle, "log": log,
        }
        return card, refs

    def _sec_install_host_tool(self, tool: dict):
        if self._sec_host_tool_worker and self._sec_host_tool_worker.isRunning():
            return
        active_refs = next(r for r in self._sec_host_tool_refs if r["tool"] is tool)
        self._sec_active_host_refs = active_refs
        for refs in self._sec_host_tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(
            f"→ flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo\n"
            f"→ flatpak install -y flathub {tool['flatpak']}\n"
        )
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Installing {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        self._sec_host_tool_worker = Worker([
            "bash", "-c",
            f"flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {tool['flatpak']}",
        ])
        self._sec_host_tool_worker.line.connect(lambda ln: (
            log.append(ln), log.ensureCursorVisible(),
        ))
        self._sec_host_tool_worker.done.connect(
            lambda code, name=tool["name"]: self._sec_on_host_tool_install_done(code, name)
        )
        self._sec_host_tool_worker.start()

    def _sec_on_host_tool_install_done(self, code: int, name: str):
        active_refs = self._sec_active_host_refs
        active_refs["progress"].hide()
        _finish_worker(self, attr="_sec_host_tool_worker")
        for refs in self._sec_host_tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        if code == 0:
            active_refs["status"].setText(f"{name} installed.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Installation failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        self._refresh_sec_status()

    def _sec_uninstall_host_tool(self, tool: dict):
        if self._sec_host_tool_worker and self._sec_host_tool_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, f"Uninstall {tool['name']}",
            f"Remove {tool['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active_refs = next(r for r in self._sec_host_tool_refs if r["tool"] is tool)
        self._sec_active_host_refs = active_refs
        for refs in self._sec_host_tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(f"→ flatpak uninstall -y {tool['flatpak']}\n")
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Uninstalling {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        self._sec_host_tool_worker = Worker(["flatpak", "uninstall", "-y", tool["flatpak"]])
        self._sec_host_tool_worker.line.connect(lambda ln: (
            log.append(ln), log.ensureCursorVisible(),
        ))
        self._sec_host_tool_worker.done.connect(
            lambda code, name=tool["name"]: self._sec_on_host_tool_uninstall_done(code, name)
        )
        self._sec_host_tool_worker.start()

    def _sec_on_host_tool_uninstall_done(self, code: int, name: str):
        active_refs = self._sec_active_host_refs
        active_refs["progress"].hide()
        _finish_worker(self, attr="_sec_host_tool_worker")
        for refs in self._sec_host_tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        if code == 0:
            active_refs["status"].setText(f"{name} uninstalled.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Uninstall failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        self._refresh_sec_status()

    # ── Tab 4: Creator ────────────────────────────────────────────────────────

    def _build_creator_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        intro = QLabel(
            "Recording, streaming, video editing, and audio tools. "
            "AMD GPU + Mesa RADV gives excellent hardware acceleration in DaVinci Resolve."
        )
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._cr_tool_refs = []
        for i in range(0, len(self._CR_TOOLS), 2):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            for tool in self._CR_TOOLS[i:i + 2]:
                tile, refs = self._make_cr_tool_tile(tool)
                row_layout.addWidget(tile, 1)
                self._cr_tool_refs.append(refs)
            if len(self._CR_TOOLS[i:i + 2]) == 1:
                row_layout.addStretch(1)
            row_widget = QWidget()
            row_widget.setLayout(row_layout)
            layout.addWidget(row_widget)

        layout.addWidget(_divider())

        dv_section_head = QLabel("DaVinci Resolve")
        dv_section_head.setObjectName("heading")
        dv_section_head.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        layout.addWidget(dv_section_head)
        dv_section_sub = QLabel(
            "Download the Linux ZIP from Blackmagic, then click Install from Download. "
            "Kyth will auto-detect the ZIP in your Downloads folder or let you pick it manually, "
            "then package Resolve as a local Flatpak for you."
        )
        dv_section_sub.setObjectName("card-copy")
        dv_section_sub.setWordWrap(True)
        layout.addWidget(dv_section_sub)

        dv_card, dv_layout = _make_card()
        dv_top = QHBoxLayout()
        dv_title = QLabel("DaVinci Resolve")
        dv_title.setObjectName("card-title")
        dv_top.addWidget(dv_title)
        dv_top.addStretch()
        self._dv_badge = QLabel()
        self._dv_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dv_top.addWidget(self._dv_badge)
        dv_layout.addLayout(dv_top)
        dv_desc = QLabel(
            "Professional non-linear video editor, color grader, visual effects, and audio "
            "post-production suite from Blackmagic Design. The free tier is industry-grade."
        )
        dv_desc.setObjectName("card-copy")
        dv_desc.setWordWrap(True)
        dv_layout.addWidget(dv_desc)
        dv_btn_row = QHBoxLayout()
        dv_btn_row.setSpacing(10)
        dv_dl_btn = QPushButton("Download from Blackmagic")
        dv_dl_btn.setObjectName("primary")
        dv_dl_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://www.blackmagicdesign.com/products/davinciresolve")
            )
        )
        dv_btn_row.addWidget(dv_dl_btn)
        self._dv_choose_btn = QPushButton("Choose ZIP…")
        self._dv_choose_btn.clicked.connect(self._pick_davinci_zip)
        dv_btn_row.addWidget(self._dv_choose_btn)
        self._dv_install_btn = QPushButton("Install from Download")
        self._dv_install_btn.setObjectName("primary")
        self._dv_install_btn.clicked.connect(self._install_davinci)
        dv_btn_row.addWidget(self._dv_install_btn)
        self._dv_launch_btn = QPushButton("Launch")
        self._dv_launch_btn.hide()
        self._dv_launch_btn.clicked.connect(self._launch_davinci)
        dv_btn_row.addWidget(self._dv_launch_btn)
        dv_btn_row.addStretch()
        dv_layout.addLayout(dv_btn_row)
        self._dv_zip_hint = QLabel()
        self._dv_zip_hint.setWordWrap(True)
        dv_layout.addWidget(self._dv_zip_hint)
        self._dv_op_status = QLabel()
        self._dv_op_status.hide()
        dv_layout.addWidget(self._dv_op_status)
        self._dv_progress = QProgressBar()
        self._dv_progress.setRange(0, 0)
        self._dv_progress.hide()
        dv_layout.addWidget(self._dv_progress)
        self._dv_log_toggle = QPushButton("Show details")
        self._dv_log_toggle.setCheckable(True)
        self._dv_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._dv_log_toggle, self._dv_log, checked)
        )
        self._dv_log_toggle.hide()
        dv_layout.addWidget(self._dv_log_toggle)
        self._dv_log = QTextEdit()
        self._dv_log.document().setMaximumBlockCount(5000)
        self._dv_log.setReadOnly(True)
        self._dv_log.setMaximumHeight(120)
        self._dv_log.hide()
        dv_layout.addWidget(self._dv_log)
        layout.addWidget(dv_card)

        self._refresh_cr_status()
        return tab

    def _make_cr_tool_tile(self, tool: dict) -> tuple[QFrame, dict]:
        card, layout = _make_card()
        layout.setSpacing(8)
        name_lbl = QLabel(tool["name"])
        name_lbl.setObjectName("card-title")
        layout.addWidget(name_lbl)
        desc_lbl = QLabel(tool["desc"])
        desc_lbl.setObjectName("card-copy")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        install_btn = QPushButton("Install")
        install_btn.clicked.connect(lambda _=False, t=tool: self._install_cr_tool(t))
        btn_row.addWidget(install_btn)
        launch_btn = QPushButton("Launch")
        launch_btn.hide()
        launch_btn.clicked.connect(
            lambda _=False, cmd=tool["launch"]: subprocess.Popen(cmd)
        )
        btn_row.addWidget(launch_btn)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setObjectName("danger")
        uninstall_btn.hide()
        uninstall_btn.clicked.connect(
            lambda _=False, t=tool: self._uninstall_cr_tool(t)
        )
        btn_row.addWidget(uninstall_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        status_lbl = QLabel()
        status_lbl.setObjectName("subheading")
        status_lbl.hide()
        layout.addWidget(status_lbl)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.hide()
        layout.addWidget(progress)

        log_toggle = QPushButton("Show details")
        log_toggle.setCheckable(True)
        log_toggle.hide()
        layout.addWidget(log_toggle)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setMaximumHeight(100)
        log.hide()
        layout.addWidget(log)

        log_toggle.clicked.connect(lambda checked, lt=log_toggle, lg=log: _set_log_panel(lt, lg, checked))

        refs = {
            "tool": tool, "install": install_btn, "launch": launch_btn, "uninstall": uninstall_btn,
            "status": status_lbl, "progress": progress, "log_toggle": log_toggle, "log": log,
        }
        return card, refs

    def _refresh_cr_status(self):
        for refs in self._cr_tool_refs:
            installed = _is_flatpak_installed(refs["tool"]["flatpak"])
            refs["install"].setVisible(not installed)
            refs["launch"].setVisible(installed)
            refs["uninstall"].setVisible(installed)

        if hasattr(self, "_dv_badge"):
            dv_installed = _davinci_flatpak_app_id() is not None
            _apply_install_badge(self._dv_badge, dv_installed)
            self._dv_install_btn.setVisible(not dv_installed)
            self._dv_launch_btn.setVisible(dv_installed)
            self._refresh_davinci_zip_hint()

    def _install_cr_tool(self, tool: dict):
        if self._cr_tool_worker and self._cr_tool_worker.isRunning():
            return
        active_refs = next(r for r in self._cr_tool_refs if r["tool"] is tool)
        self._cr_active_tool_refs = active_refs
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        self._dv_install_btn.setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(f"→ flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo\n→ flatpak install -y flathub {tool['flatpak']}\n")
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Installing {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        self._cr_tool_worker = Worker([
            "bash", "-c",
            f"flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {tool['flatpak']}",
        ])
        self._cr_tool_worker.line.connect(lambda ln: (
            log.append(ln),
            log.ensureCursorVisible(),
        ))
        self._cr_tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_cr_tool_install_done(code, name)
        )
        self._cr_tool_worker.start()

    def _on_cr_tool_install_done(self, code: int, name: str):
        active_refs = self._cr_active_tool_refs
        active_refs["progress"].hide()
        _finish_worker(self, attr="_cr_tool_worker")
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._dv_install_btn.setEnabled(True)
        if code == 0:
            active_refs["status"].setText(f"{name} installed.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Installation failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        self._refresh_cr_status()

    def _uninstall_cr_tool(self, tool: dict):
        if self._cr_tool_worker and self._cr_tool_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, f"Uninstall {tool['name']}",
            f"Remove {tool['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active_refs = next(r for r in self._cr_tool_refs if r["tool"] is tool)
        self._cr_active_tool_refs = active_refs
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        self._dv_install_btn.setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(f"→ flatpak uninstall -y {tool['flatpak']}\n")
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Uninstalling {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        self._cr_tool_worker = Worker(
            ["flatpak", "uninstall", "-y", tool["flatpak"]]
        )
        self._cr_tool_worker.line.connect(lambda ln: (
            log.append(ln),
            log.ensureCursorVisible(),
        ))
        self._cr_tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_cr_tool_uninstall_done(code, name)
        )
        self._cr_tool_worker.start()

    def _on_cr_tool_uninstall_done(self, code: int, name: str):
        active_refs = self._cr_active_tool_refs
        active_refs["progress"].hide()
        _finish_worker(self, attr="_cr_tool_worker")
        if code == 0:
            active_refs["status"].setText(f"{name} uninstalled.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Uninstall failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._dv_install_btn.setEnabled(True)
        self._refresh_cr_status()

    def _pick_davinci_zip(self):
        start_dir = self._dv_selected_zip or _davinci_download_dir()
        if os.path.isfile(start_dir):
            start_dir = os.path.dirname(start_dir)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select DaVinci Resolve Linux ZIP",
            start_dir,
            "ZIP archives (*.zip);;All Files (*)",
        )
        if not path:
            return
        self._dv_selected_zip = path
        self._refresh_davinci_zip_hint()

    def _refresh_davinci_zip_hint(self):
        selected = self._dv_selected_zip
        if selected and os.path.isfile(selected):
            self._dv_zip_hint.setText(f"Selected ZIP: {selected}")
            self._dv_zip_hint.setObjectName("status-ok")
            _restyle(self._dv_zip_hint)
            return

        self._dv_selected_zip = None
        candidates = _davinci_zip_candidates()
        if candidates:
            self._dv_zip_hint.setText(f"Auto-detected ZIP: {candidates[0]}")
            self._dv_zip_hint.setObjectName("status-dim")
        else:
            self._dv_zip_hint.setText(
                f"No DaVinci ZIP found yet. Download it to {_davinci_download_dir()} or click Choose ZIP…"
            )
            self._dv_zip_hint.setObjectName("status-warn")
        _restyle(self._dv_zip_hint)

    def _launch_davinci(self):
        app_id = _davinci_flatpak_app_id()
        if not app_id:
            QMessageBox.warning(self, "DaVinci Resolve", "DaVinci Resolve is not installed yet.")
            return
        subprocess.Popen(["flatpak", "run", app_id])

    def _install_davinci(self):
        if self._dv_worker and self._dv_worker.isRunning():
            return

        if not shutil.which("flatpak-builder"):
            self._dv_log.clear()
            self._dv_log.append("Missing required tool: flatpak-builder\n")
            self._dv_log.append("Update KythOS to the latest image, then try again.\n")
            self._dv_log_toggle.show()
            _set_log_panel(self._dv_log_toggle, self._dv_log, False)
            self._dv_op_status.setText(
                "DaVinci installer tools are missing. Please run a system update first."
            )
            self._dv_op_status.setObjectName("status-warn")
            self._dv_op_status.show()
            _restyle(self._dv_op_status)
            return

        zip_path = self._dv_selected_zip if self._dv_selected_zip and os.path.isfile(self._dv_selected_zip) else ""
        if not zip_path:
            candidates = _davinci_zip_candidates()
            zip_path = candidates[0] if candidates else ""
        if not zip_path:
            self._dv_log.clear()
            self._dv_log.append("No DaVinci Resolve Linux ZIP was found.\n")
            self._dv_log.append(
                f"Download the ZIP from Blackmagic to {_davinci_download_dir()} or click Choose ZIP… and retry.\n"
            )
            self._dv_log_toggle.show()
            _set_log_panel(self._dv_log_toggle, self._dv_log, False)
            self._dv_op_status.setText("Download the Linux ZIP first, or choose it manually.")
            self._dv_op_status.setObjectName("status-warn")
            self._dv_op_status.show()
            _restyle(self._dv_op_status)
            QMessageBox.warning(
                self,
                "DaVinci Resolve",
                "I couldn't find the downloaded Linux ZIP automatically.\n\n"
                "Download it from Blackmagic first, or click “Choose ZIP…” and select it manually.",
            )
            return

        self._dv_selected_zip = zip_path
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(False)
        self._dv_install_btn.setEnabled(False)
        self._dv_choose_btn.setEnabled(False)
        self._dv_log.clear()
        self._dv_log.append(f"→ /usr/bin/kyth-davinci-install {zip_path}\n")
        self._dv_log.append(
            "Kyth will repackage the official Blackmagic download as a user Flatpak. "
            "The first build can take a few minutes.\n"
        )
        self._dv_log_toggle.show()
        _set_log_panel(self._dv_log_toggle, self._dv_log, False)
        self._dv_progress.show()
        self._dv_op_status.setText("Building and installing DaVinci Resolve…")
        self._dv_op_status.setObjectName("subheading")
        self._dv_op_status.show()
        _restyle(self._dv_op_status)
        self._dv_worker = Worker(["/usr/bin/kyth-davinci-install", zip_path])
        self._dv_worker.line.connect(lambda ln: (
            self._dv_log.append(ln),
            self._dv_log.ensureCursorVisible(),
        ))
        self._dv_worker.done.connect(self._on_davinci_install_done)
        self._dv_worker.start()

    def _on_davinci_install_done(self, code: int):
        self._dv_progress.hide()
        _finish_worker(self, attr="_dv_worker")
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(True)
        self._dv_install_btn.setEnabled(True)
        self._dv_choose_btn.setEnabled(True)
        installed = _davinci_flatpak_app_id() is not None
        if code == 0 and installed:
            self._dv_op_status.setText("DaVinci Resolve installed. Launch it from here or the app menu.")
            self._dv_op_status.setObjectName("status-ok")
            self._dv_log.append("\nDone.")
        else:
            self._dv_op_status.setText(
                f"Installation failed (exit {code}). Check the details below — a fresh ZIP or system update may be needed."
            )
            self._dv_op_status.setObjectName("status-err")
        _restyle(self._dv_op_status)
        self._refresh_cr_status()
