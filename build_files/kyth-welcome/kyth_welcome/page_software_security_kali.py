import shutil

# __KYTH_GENERATED_IMPORTS__
from .core_base import _apply_install_badge, _restyle
from .services.launch import popen
from .services.security import (
    _is_socket_capable_kali_box,
    build_kali_create_command,
    build_kali_export_command,
    build_kali_remove_command,
    KaliInstallProgressTracker,
)
from .services.runtime import Worker, _finish_worker
from .qt import (
    QButtonGroup, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QTextEdit, Qt,
)
from .widgets import _make_card, _set_log_panel


class _KaliContainerMixin:
    """Kali Linux distrobox container lifecycle: create, enter, export apps, remove."""

    def _build_kali_card(self, layout):
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
            "⚠  kali-linux-everything is extremely large — expect 15–20 GB or more of downloads "  # noqa: RUF001 — en dash, deliberate typography
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

    def _refresh_sec_kali_status(self):
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
        self._sec_progress_tracker = KaliInstallProgressTracker()

        cmd = build_kali_create_command(self._SEC_BOX_NAME, self._SEC_BOX_IMAGE, meta, has_gui)
        self._sec_worker = Worker(cmd)
        self._sec_worker.line.connect(self._sec_on_create_line)
        self._sec_worker.done.connect(self._sec_on_create_done)
        self._sec_worker.start()

    def _sec_on_create_line(self, ln: str):
        self._sec_log.append(ln)
        self._sec_log.ensureCursorVisible()

        msg, prog = self._sec_progress_tracker.parse_line(ln)
        if msg is not None:
            self._sec_status_lbl.setText(msg)
            _restyle(self._sec_status_lbl)
        if prog is not None:
            self._sec_progress.setValue(prog)

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
        self._refresh_sec_kali_status()

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
            popen(["konsole", "-e", "distrobox", "enter", "--root", self._SEC_BOX_NAME])
        else:
            popen([terminal, "--", "distrobox", "enter", "--root", self._SEC_BOX_NAME])

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

        cmd = build_kali_export_command(self._SEC_BOX_NAME)
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

        self._sec_worker = Worker(build_kali_remove_command(self._SEC_BOX_NAME))
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
        self._refresh_sec_kali_status()
