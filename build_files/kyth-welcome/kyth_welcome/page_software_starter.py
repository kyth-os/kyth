import shlex
import subprocess

# __KYTH_GENERATED_IMPORTS__
from .core_base import _restyle
from .services.software import (
    Worker, _chromium_app_window_cmd, _finish_worker, _install_flatpak_inline, _is_flatpak_installed,
)
from .qt import (  # noqa: E501
    QCheckBox, QComboBox, QDesktopServices, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QTextEdit, QUrl, QVBoxLayout, QWidget, Qt,
)
from .widgets import _make_card, _set_log_panel


class _StarterPackTabMixin:
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
