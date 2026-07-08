import glob
import os
import shlex
import shutil
import subprocess

# __KYTH_GENERATED_IMPORTS__
from .core_base import _release_worker_when_finished
from .services.gaming import (
    DataWorker, _find_ntfs_drives,
)
from .services.software import (
    Worker, _chromium_app_window_cmd, _install_flatpak_inline, _is_flatpak_installed,
)
from .qt import (  # noqa: E501
    QApplication, QCheckBox, QComboBox, QDBusConnection, QDBusInterface, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTimer,
)
from .widgets import (  # noqa: E501
    Page, _make_card,
)

# Work-bundle apps offered on this page (and pre-selected by the first-run
# wizard when the user picks the Work or Both profile).
_WORK_APPS = [
    ("org.libreoffice.LibreOffice", "LibreOffice",
     "Writer, Calc, and Impress — opens and saves Word, Excel, and PowerPoint files."),
    ("eu.betterbird.Betterbird", "Betterbird",
     "Desktop email, calendar, and contacts — connects to Microsoft 365, Gmail, and IMAP accounts."),
]

_M365_APPS = [
    ("Outlook",    "https://outlook.office.com/mail/",               "Email and calendar"),
    ("Word",       "https://office.live.com/start/Word.aspx",       "Documents"),
    ("Excel",      "https://office.live.com/start/Excel.aspx",      "Spreadsheets"),
    ("PowerPoint", "https://office.live.com/start/PowerPoint.aspx", "Presentations"),
    ("OneNote",    "https://www.onenote.com/notebooks",              "Notes"),
    ("Teams",      "https://teams.microsoft.com/",                   "Chat and meetings"),
]

_MS_FONTS_DIR = os.path.expanduser("~/.local/share/fonts/msttcorefonts")


def _ms_fonts_installed() -> bool:
    try:
        return any(entry.lower().endswith(".ttf") for entry in os.listdir(_MS_FONTS_DIR))
    except OSError:
        return False


def _m365_icon(name: str) -> str:
    icon = f"kyth-m365-{name.lower()}"
    if os.path.exists(f"/usr/share/icons/hicolor/scalable/apps/{icon}.svg"):
        return icon
    # Older images don't ship the per-app icons yet.
    return "internet-web-browser"


def _m365_desktop_entry(name: str, url: str, comment: str) -> str | None:
    launch = _chromium_app_window_cmd(url)
    if launch is None:
        return None
    cmd, wm_class = launch
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name} (Microsoft 365)\n"
        f"Comment={comment}\n"
        f"Exec={shlex.join(cmd)}\n"
        f"Icon={_m365_icon(name)}\n"
        "Categories=Office;\n"
        f"StartupWMClass={wm_class}\n"
    )


def _create_m365_shortcuts() -> int:
    """Write launcher .desktop entries for the Microsoft 365 web apps.

    Returns the number of shortcuts written."""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    written = 0
    try:
        os.makedirs(apps_dir, exist_ok=True)
    except OSError:
        return 0
    for name, url, comment in _M365_APPS:
        entry = _m365_desktop_entry(name, url, comment)
        if entry is None:
            continue
        path = os.path.join(apps_dir, f"kyth-m365-{name.lower()}.desktop")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(entry)
            written += 1
        except OSError:
            pass
    return written


# ── Outlook PST archives ──────────────────────────────────────────────────────

_PST_IMPORT_DIR = os.path.expanduser("~/Documents/Outlook Import")


def _scan_for_pst_files() -> list[str]:
    """Look for Outlook .pst archives in the usual profile locations."""
    found: list[str] = []
    roots = [d.get("mount") for d in _find_ntfs_drives() if d.get("mount")]
    roots.append(os.path.expanduser("~"))
    for root in roots:
        for pattern in (
            "Users/*/Documents/Outlook Files/*.pst",
            "Users/*/Documents/*.pst",
            "Users/*/AppData/Local/Microsoft/Outlook/*.pst",
            "Documents/*.pst",
            "Downloads/*.pst",
        ):
            found.extend(glob.glob(os.path.join(root, pattern)))
    return sorted(set(found))


def _convert_pst(path: str) -> tuple[bool, str]:
    """Convert a .pst to mbox folders under ~/Documents/Outlook Import."""
    name = os.path.splitext(os.path.basename(path))[0]
    dest = os.path.join(_PST_IMPORT_DIR, name)
    try:
        os.makedirs(dest, exist_ok=True)
        r = subprocess.run(
            ["readpst", "-r", "-o", dest, path],
            capture_output=True, text=True, timeout=3600,
        )
    except FileNotFoundError:
        return False, "readpst is not installed — update KythOS to the latest image."
    except Exception as exc:
        return False, str(exc)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or "Conversion failed."
    return True, dest


def _refresh_m365_shortcuts() -> None:
    """Rewrite existing shortcuts whose generated content changed — e.g. the
    pre-icon entries that left every web app with a generic globe."""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    for name, url, comment in _M365_APPS:
        path = os.path.join(apps_dir, f"kyth-m365-{name.lower()}.desktop")
        if not os.path.exists(path):
            continue
        entry = _m365_desktop_entry(name, url, comment)
        if entry is None:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                current = fh.read()
            if current != entry:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(entry)
        except OSError:
            pass


def _m365_shortcuts_present() -> bool:
    apps_dir = os.path.expanduser("~/.local/share/applications")
    return all(
        os.path.exists(os.path.join(apps_dir, f"kyth-m365-{name.lower()}.desktop"))
        for name, _, _ in _M365_APPS
    )


# ── Page: Work Setup ──────────────────────────────────────────────────────────
class WorkSetupPage(Page):
    """Guided checklist that makes a fresh install Monday-morning ready:
    office apps, Microsoft 365 shortcuts, document fonts, VPN, shares,
    cloud sync, and printing — threading the existing Hub pages together."""

    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _: None)
        self._ms_fonts_worker: Worker | None = None
        self._pst_worker: DataWorker | None = None
        self._focus_remaining = 0
        self._focus_warnings: list[str] = []
        self._focus_notification_cookie: int | None = None
        self._focus_inhibit_proc: subprocess.Popen | None = None
        self._focus_timer = QTimer(self)
        self._focus_timer.setInterval(1000)
        self._focus_timer.timeout.connect(self._focus_tick)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._cleanup_focus_session)

        self._page_header(
            "Apps",
            "Work Setup",
            "Everything a work machine needs before Monday morning: office apps, email, "
            "Microsoft 365, document fonts, VPN, network shares, cloud sync, and printing. "
            "Each step is optional — set up only what your workplace uses.",
        )

        self._add(self._make_work_apps_card())
        self._add(self._make_m365_card())
        self._add(self._make_fonts_card())
        self._add(self._make_pst_card())
        self._add(self._make_focus_card())
        self._add(self._make_connect_card())
        self._stretch()

    # ── Office & email apps ────────────────────────────────────────────────
    def _make_work_apps_card(self):
        card, layout = _make_card()
        title = QLabel("1. Office and email apps")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "LibreOffice covers Word, Excel, and PowerPoint files. Betterbird handles "
            "work email and calendars. Both install from Flathub in one click."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        for app_id, name, desc in _WORK_APPS:
            btn = QPushButton(f"Install {name}")
            btn.setToolTip(desc)
            if _is_flatpak_installed(app_id):
                btn.setText(f"✓ {name} installed")
                btn.setEnabled(False)
            else:
                btn.setObjectName("primary")
                btn.clicked.connect(
                    lambda _=False, b=btn, a=app_id, n=name: _install_flatpak_inline(self, b, a, n)
                )
            btns.addWidget(btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    # ── Microsoft 365 web apps ─────────────────────────────────────────────
    def _make_m365_card(self):
        card, layout = _make_card()
        title = QLabel("2. Microsoft 365 — web app shortcuts")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "If your workplace uses Microsoft 365, the full suite runs in the browser. "
            "Add launcher shortcuts so Outlook, Teams, Word, and the rest open in their "
            "own windows from the app menu — pinnable to the taskbar like native apps."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._m365_btn = QPushButton("Add Microsoft 365 to App Launcher")
        _refresh_m365_shortcuts()
        if _m365_shortcuts_present():
            self._m365_btn.setText("✓ Shortcuts added — find them in the app menu")
            self._m365_btn.setEnabled(False)
        else:
            self._m365_btn.setObjectName("primary")
        self._m365_btn.clicked.connect(self._on_add_m365)
        btns.addWidget(self._m365_btn)

        for name, url, tip in _M365_APPS[:2]:
            open_btn = QPushButton(f"Open {name}")
            open_btn.setToolTip(f"{tip} — opens in a dedicated window")
            open_btn.clicked.connect(
                lambda _=False, u=url, n=name: self._open_m365_webapp(u, n)
            )
            btns.addWidget(open_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _open_m365_webapp(self, url: str, name: str) -> None:
        launch = _chromium_app_window_cmd(url)
        if launch is None:
            QMessageBox.warning(
                self, "No browser found",
                "Opening web app shortcuts needs a Chromium-family browser "
                "(Brave, Chromium, Edge, or Chrome), but none was found.",
            )
            return
        try:
            subprocess.Popen(launch[0])
        except OSError as exc:
            QMessageBox.warning(self, "Could not open web app", str(exc))

    def _on_add_m365(self):
        written = _create_m365_shortcuts()
        if written == len(_M365_APPS):
            self._m365_btn.setText("✓ Shortcuts added — find them in the app menu")
            self._m365_btn.setEnabled(False)
        else:
            self._m365_btn.setText(f"Added {written} of {len(_M365_APPS)} — try again")

    # ── Microsoft fonts ────────────────────────────────────────────────────
    def _make_fonts_card(self):
        card, layout = _make_card()
        title = QLabel("3. Microsoft fonts — keep document formatting intact")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "Documents from other PCs may use fonts like Times New Roman and Arial. "
            "Installing them keeps layouts pixel-identical instead of substituted."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._fonts_btn = QPushButton("Install Microsoft Fonts")
        if _ms_fonts_installed():
            self._fonts_btn.setText("✓ Microsoft fonts installed")
            self._fonts_btn.setEnabled(False)
        else:
            self._fonts_btn.setObjectName("primary")
        self._fonts_btn.clicked.connect(self._on_install_fonts)
        btns.addWidget(self._fonts_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self._fonts_status = QLabel("")
        self._fonts_status.setObjectName("card-copy")
        self._fonts_status.setWordWrap(True)
        self._fonts_status.hide()
        layout.addWidget(self._fonts_status)
        return card

    def _on_install_fonts(self):
        if self._ms_fonts_worker is not None and self._ms_fonts_worker.isRunning():
            return
        self._fonts_btn.setEnabled(False)
        self._fonts_btn.setText("Installing…")
        self._fonts_status.setText("Downloading Microsoft core fonts…")
        self._fonts_status.show()
        self._ms_fonts_worker = Worker(["bash", "-c", "ujust install-ms-fonts"])
        self._ms_fonts_worker.done.connect(self._on_fonts_done)
        self._ms_fonts_worker.start()

    def _on_fonts_done(self, code: int):
        if code == 0:
            self._fonts_btn.setText("✓ Microsoft fonts installed")
            self._fonts_status.setText("✓ Done. Restart LibreOffice to pick up the new fonts.")
        else:
            self._fonts_btn.setEnabled(True)
            self._fonts_btn.setText("Install Microsoft Fonts")
            self._fonts_status.setText("✗ Installation failed. Check your network connection and try again.")

    # ── Outlook PST archives ───────────────────────────────────────────────
    def _make_pst_card(self):
        card, layout = _make_card()
        title = QLabel("4. Outlook archives — bring your old email (.pst)")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "Years of mail live in Outlook .pst archive files that nothing on Linux opens "
            "directly. KythOS converts them to the standard mbox format: in Betterbird, "
            "add the ImportExportTools NG add-on, then Tools → ImportExportTools NG → "
            "Import mbox file and pick the converted folder."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._pst_scan_btn = QPushButton("Find PST Files")
        self._pst_scan_btn.setObjectName("primary")
        self._pst_scan_btn.setToolTip("Scans mounted PC drives and your home folder for Outlook archives.")
        self._pst_scan_btn.clicked.connect(self._scan_pst)
        btns.addWidget(self._pst_scan_btn)
        pick_btn = QPushButton("Choose PST File…")
        pick_btn.clicked.connect(self._pick_pst)
        btns.addWidget(pick_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self._pst_status = QLabel("")
        self._pst_status.setObjectName("card-copy")
        self._pst_status.setWordWrap(True)
        self._pst_status.hide()
        layout.addWidget(self._pst_status)
        self._pst_found_row = QHBoxLayout()
        self._pst_found_row.setSpacing(8)
        layout.addLayout(self._pst_found_row)
        return card

    def _set_pst_status(self, text: str):
        self._pst_status.setText(text)
        self._pst_status.show()

    def _scan_pst(self):
        if self._pst_worker is not None and self._pst_worker.isRunning():
            return
        self._pst_scan_btn.setEnabled(False)
        self._set_pst_status("Scanning for Outlook archives…")
        worker = DataWorker("pst-scan", _scan_for_pst_files)
        worker.result.connect(self._on_pst_found)
        self._pst_worker = worker
        _release_worker_when_finished(self, "_pst_worker", worker)
        worker.start()

    def _on_pst_found(self, _key: str, paths: list):
        self._pst_scan_btn.setEnabled(True)
        while self._pst_found_row.count():
            item = self._pst_found_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not paths:
            self._set_pst_status(
                "No .pst files found. If your PC drive is not mounted yet, "
                "scan and unlock it from the Move Files page first, or "
                "use Choose PST File."
            )
            return
        self._set_pst_status(f"Found {len(paths)} archive{'s' if len(paths) != 1 else ''} — click one to convert:")
        for path in paths[:6]:
            btn = QPushButton(os.path.basename(path))
            btn.setToolTip(path)
            btn.clicked.connect(lambda _=False, p=path: self._convert_pst(p))
            self._pst_found_row.addWidget(btn)
        self._pst_found_row.addStretch()

    def _pick_pst(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an Outlook archive", os.path.expanduser("~"),
            "Outlook archives (*.pst *.ost);;All files (*)",
        )
        if path:
            self._convert_pst(path)

    def _convert_pst(self, path: str):
        if self._pst_worker is not None and self._pst_worker.isRunning():
            return
        self._set_pst_status(f"Converting {os.path.basename(path)} — large archives can take a while…")
        worker = DataWorker("pst-convert", lambda: _convert_pst(path))
        worker.result.connect(self._on_pst_converted)
        self._pst_worker = worker
        _release_worker_when_finished(self, "_pst_worker", worker)
        worker.start()

    def _on_pst_converted(self, _key: str, result: tuple):
        ok, detail = result
        if ok:
            self._set_pst_status(
                f"✓ Converted to {detail}. In Betterbird: add the ImportExportTools NG "
                "add-on, then Tools → ImportExportTools NG → Import mbox file."
            )
        else:
            self._set_pst_status(f"✗ Conversion failed: {detail}")

    # ── Focus sessions ─────────────────────────────────────────────────────
    def _make_focus_card(self):
        card, layout = _make_card("card-accent-ok")
        title = QLabel("5. Focus Assist — quiet work sessions")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "Start a timed focus block without changing permanent settings. KythOS can "
            "silence notification popups, prevent sleep, and open the work apps you choose; "
            "everything returns to normal when the timer ends."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        options = QHBoxLayout()
        options.setSpacing(10)
        self._focus_duration = QComboBox()
        for label, minutes in (("25 minutes", 25), ("50 minutes", 50), ("90 minutes", 90)):
            self._focus_duration.addItem(label, minutes)
        options.addWidget(self._focus_duration)
        self._focus_dnd = QCheckBox("Do Not Disturb")
        self._focus_dnd.setChecked(True)
        options.addWidget(self._focus_dnd)
        self._focus_awake = QCheckBox("Keep PC awake")
        self._focus_awake.setChecked(True)
        options.addWidget(self._focus_awake)
        options.addStretch()
        layout.addLayout(options)

        apps = QHBoxLayout()
        apps.setSpacing(10)
        apps.addWidget(QLabel("Open at start:"))
        self._focus_betterbird = QCheckBox("Betterbird")
        self._focus_betterbird.setEnabled(_is_flatpak_installed("eu.betterbird.Betterbird"))
        self._focus_betterbird.setToolTip("Install Betterbird from step 1 if this option is unavailable.")
        apps.addWidget(self._focus_betterbird)
        self._focus_office = QCheckBox("LibreOffice")
        self._focus_office.setEnabled(_is_flatpak_installed("org.libreoffice.LibreOffice"))
        self._focus_office.setToolTip("Install LibreOffice from step 1 if this option is unavailable.")
        apps.addWidget(self._focus_office)
        self._focus_outlook = QCheckBox("Outlook Web")
        apps.addWidget(self._focus_outlook)
        apps.addStretch()
        layout.addLayout(apps)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self._focus_start_btn = QPushButton("Start Focus Session")
        self._focus_start_btn.setObjectName("primary")
        self._focus_start_btn.clicked.connect(self._start_focus_session)
        controls.addWidget(self._focus_start_btn)
        self._focus_stop_btn = QPushButton("End Session")
        self._focus_stop_btn.setEnabled(False)
        self._focus_stop_btn.clicked.connect(lambda _=False: self._end_focus_session(False))
        controls.addWidget(self._focus_stop_btn)
        controls.addStretch()
        layout.addLayout(controls)

        self._focus_status = QLabel("Ready for a quiet work block.")
        self._focus_status.setObjectName("card-copy")
        self._focus_status.setWordWrap(True)
        layout.addWidget(self._focus_status)
        return card

    @staticmethod
    def _notifications_interface() -> QDBusInterface:
        return QDBusInterface(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            QDBusConnection.sessionBus(),
        )

    def _inhibit_notifications(self) -> bool:
        try:
            reply = self._notifications_interface().call(
                "Inhibit", "kyth-welcome", "KythOS Focus Session", {}
            )
            args = reply.arguments()
            if args:
                self._focus_notification_cookie = int(args[0])
                return True
        except Exception:
            pass
        return False

    def _release_notification_inhibit(self):
        cookie = self._focus_notification_cookie
        self._focus_notification_cookie = None
        if cookie is None:
            return
        try:
            self._notifications_interface().call("UnInhibit", cookie)
        except Exception:
            pass

    def _launch_focus_apps(self):
        launches: list[list[str]] = []
        if self._focus_betterbird.isChecked():
            launches.append(["flatpak", "run", "eu.betterbird.Betterbird"])
        if self._focus_office.isChecked():
            launches.append(["flatpak", "run", "org.libreoffice.LibreOffice"])
        if self._focus_outlook.isChecked():
            launch = _chromium_app_window_cmd("https://outlook.office.com/mail/")
            if launch is not None:
                launches.append(launch[0])
        for cmd in launches:
            try:
                subprocess.Popen(cmd)
            except OSError:
                continue

    def _start_focus_session(self):
        if self._focus_timer.isActive():
            return
        minutes = int(self._focus_duration.currentData() or 25)
        warnings: list[str] = []
        if self._focus_dnd.isChecked() and not self._inhibit_notifications():
            warnings.append("Do Not Disturb was unavailable")
        if self._focus_awake.isChecked():
            if not shutil.which("systemd-inhibit"):
                warnings.append("sleep inhibition was unavailable")
            else:
                try:
                    self._focus_inhibit_proc = subprocess.Popen([
                        "systemd-inhibit", "--what=idle:sleep",
                        "--why=KythOS Focus Session", "--mode=block",
                        "sleep", str(minutes * 60 + 60),
                    ])
                except OSError:
                    warnings.append("sleep inhibition was unavailable")
        self._launch_focus_apps()
        self._focus_remaining = minutes * 60
        self._focus_duration.setEnabled(False)
        self._focus_start_btn.setEnabled(False)
        self._focus_stop_btn.setEnabled(True)
        self._focus_timer.start()
        self._focus_warnings = warnings
        self._update_focus_status()

    def _focus_tick(self):
        self._focus_remaining -= 1
        if self._focus_remaining <= 0:
            self._end_focus_session(True)
            return
        self._update_focus_status()

    def _update_focus_status(self):
        minutes, seconds = divmod(max(0, self._focus_remaining), 60)
        status = (
            f"Focus session active — {minutes:02d}:{seconds:02d} remaining. "
            "Notification popups and sleep return to their previous behavior when it ends."
        )
        if self._focus_warnings:
            status += " Note: " + "; ".join(self._focus_warnings) + "."
        self._focus_status.setText(status)

    def _cleanup_focus_session(self):
        self._focus_timer.stop()
        self._release_notification_inhibit()
        proc = self._focus_inhibit_proc
        self._focus_inhibit_proc = None
        if proc is not None and proc.poll() is None:
            proc.terminate()

    def _end_focus_session(self, completed: bool):
        was_active = self._focus_timer.isActive()
        self._cleanup_focus_session()
        self._focus_remaining = 0
        self._focus_duration.setEnabled(True)
        self._focus_start_btn.setEnabled(True)
        self._focus_stop_btn.setEnabled(False)
        self._focus_warnings = []
        self._focus_status.setText(
            "Focus session complete. Take a short break before the next block."
            if completed else "Focus session ended. Notifications and normal power behavior are restored."
        )
        if completed and was_active and shutil.which("notify-send"):
            subprocess.Popen([
                "notify-send", "Focus session complete",
                "Take a short break before starting another block.",
            ])

    # ── Workplace connections ──────────────────────────────────────────────
    def _make_connect_card(self):
        card, layout = _make_card()
        title = QLabel("6. Connect to your workplace")
        title.setObjectName("card-title")
        layout.addWidget(title)
        copy = QLabel(
            "Each of these opens the matching setup page. Have your IT details handy: "
            "VPN gateway address, share paths (\\\\server\\share), and printer name."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        for label, page_key in (
            ("Set up VPN", "VPN"),
            ("Mount Network Shares", "Network Shares"),
            ("Sync Cloud Storage", "Cloud Storage"),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=page_key: self._navigate(k))
            btns.addWidget(btn)

        printer_btn = QPushButton("Add a Printer")
        printer_btn.setToolTip("Opens KDE printer settings. Network printers are usually detected automatically.")
        printer_btn.clicked.connect(self._open_printer_settings)
        btns.addWidget(printer_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    @staticmethod
    def _open_printer_settings():
        if shutil.which("kcmshell6"):
            subprocess.Popen(["kcmshell6", "kcm_printer_manager"])
        else:
            subprocess.Popen(["systemsettings", "kcm_printer_manager"])
