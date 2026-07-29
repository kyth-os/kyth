"""Windows Migration page — localsend misc cards + handlers, _LocalSendMiscMixin."""

from __future__ import annotations

import os
from ..services.runtime import DataWorker, release_worker_when_finished
from ..actions import _install_flatpak_inline
from ..services.flatpak import _is_flatpak_installed
from ..services.launch import flatpak_run, popen, systemsettings, kcmshell
from ..services.windows_migration import (
    _collect_hw_sanity,
)
from ..qt import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, single_shot,
)
from ..widgets import (
    _make_card,
)


class _LocalSendMiscMixin:
    def _build_nearby_card(self):
        # Nearby Sharing equivalents
        nearby_card, nearby_layout = _make_card("card-accent-ok")
        nearby_title = QLabel("Nearby Sharing → LocalSend and KDE Connect")
        nearby_title.setObjectName("card-title")
        nearby_layout.addWidget(nearby_title)
        nearby_body = QLabel(
            "Send files directly over your local network without uploading them first. "
            "LocalSend works across Windows, macOS, Linux, Android, and iPhone; KDE Connect "
            "adds phone notifications, clipboard sharing, and a Dolphin right-click action "
            "named Send to Nearby Device."
        )
        nearby_body.setObjectName("card-copy")
        nearby_body.setWordWrap(True)
        nearby_layout.addWidget(nearby_body)
        nearby_btns = QHBoxLayout()
        nearby_btns.setSpacing(8)
        self._localsend_btn = QPushButton()
        self._localsend_btn.setObjectName("primary")
        self._localsend_btn.clicked.connect(self._open_or_install_localsend)
        nearby_btns.addWidget(self._localsend_btn)
        send_btn = QPushButton("Send a File")
        send_btn.setToolTip("Choose files, then select a paired KDE Connect device.")
        send_btn.clicked.connect(self._send_nearby_files)
        nearby_btns.addWidget(send_btn)
        pair_btn = QPushButton("Pair a Phone or PC")
        pair_btn.clicked.connect(self._open_kde_connect)
        nearby_btns.addWidget(pair_btn)
        nearby_btns.addStretch()
        nearby_layout.addLayout(nearby_btns)
        self._nearby_status = QLabel("")
        self._nearby_status.setObjectName("card-copy")
        self._nearby_status.setWordWrap(True)
        nearby_layout.addWidget(self._nearby_status)
        self._refresh_localsend_btn()
        self._add(nearby_card)



    def _build_powertoys_card(self):
        # PowerToys equivalents built into Plasma and Dolphin
        powertoys_card, powertoys_layout = _make_card()
        powertoys_title = QLabel("PowerToys equivalents — already built in")
        powertoys_title.setObjectName("card-title")
        powertoys_layout.addWidget(powertoys_title)
        powertoys_body = QLabel(
            "The names are different, but the useful PowerToys workflows are here "
            "without another background utility."
        )
        powertoys_body.setObjectName("card-copy")
        powertoys_body.setWordWrap(True)
        powertoys_layout.addWidget(powertoys_body)
        for title, summary in (
            ("PowerToys Run", "Press Alt+Space for KRunner: launch apps, search files, calculate, convert units, and run commands."),
            ("FancyZones", "Press Win+T for the KDE tile editor, or drag windows while holding Shift to use your tile layout."),
            ("Always on Top", "Right-click a title bar → More Actions → Keep Above Others; assign a custom shortcut in System Settings."),
            ("PowerRename", "Select multiple files in Dolphin and press F2 for batch rename with find-and-replace and numbering."),
            ("Keyboard Manager", "System Settings → Keyboard → Shortcuts remaps global shortcuts and application actions."),
            ("Awake", "Use Power Management settings, or Game Night Mode on the Gaming page to prevent sleep while playing."),
            ("Color Picker / Text Extractor", "Spectacle covers region capture and annotation; dedicated color-picker and OCR apps are available in the App Store."),
        ):
            powertoys_layout.addWidget(self._make_migration_row("ok", title, summary))
        powertoys_btns = QHBoxLayout()
        powertoys_btns.setSpacing(8)
        run_btn = QPushButton("Open PowerToys Run")
        run_btn.setObjectName("primary")
        run_btn.clicked.connect(self._open_krunner)
        powertoys_btns.addWidget(run_btn)
        shortcuts_btn = QPushButton("Open Keyboard Shortcuts")
        shortcuts_btn.clicked.connect(
            lambda _=False: self._open_settings_module("kcm_keys", "Keyboard Shortcuts")
        )
        powertoys_btns.addWidget(shortcuts_btn)
        rules_btn = QPushButton("Open Window Rules")
        rules_btn.clicked.connect(
            lambda _=False: self._open_settings_module("kcm_kwinrules", "Window Rules")
        )
        powertoys_btns.addWidget(rules_btn)
        powertoys_btns.addStretch()
        powertoys_layout.addLayout(powertoys_btns)
        self._powertoys_status = QLabel("")
        self._powertoys_status.setObjectName("card-copy")
        self._powertoys_status.setWordWrap(True)
        powertoys_layout.addWidget(self._powertoys_status)
        self._add(powertoys_card)



    def _build_hw_card(self):
        # Hardware sanity — the things the previous setup configured silently
        hw_card, hw_layout = _make_card()
        hw_top = QHBoxLayout()
        hw_title = QLabel("Did everything come along? Quick hardware check")
        hw_title.setObjectName("card-title")
        hw_top.addWidget(hw_title)
        hw_top.addStretch()
        hw_again_btn = QPushButton("Check Again")
        hw_again_btn.clicked.connect(self._run_hw_sanity)
        hw_top.addWidget(hw_again_btn)
        hw_layout.addLayout(hw_top)
        hw_body = QLabel(
            "Network, display (HDR and variable refresh), printers, Bluetooth, and power — "
            "the things Windows set up silently, checked here so you don't have to hunt for drivers."
        )
        hw_body.setObjectName("card-copy")
        hw_body.setWordWrap(True)
        hw_layout.addWidget(hw_body)
        self._hw_status = QLabel("Checking…")
        self._hw_status.setObjectName("card-copy")
        hw_layout.addWidget(self._hw_status)
        self._hw_rows = QVBoxLayout()
        self._hw_rows.setSpacing(6)
        hw_layout.addLayout(self._hw_rows)
        hw_btns = QHBoxLayout()
        hw_btns.setSpacing(8)
        self._hw_printer_btn = QPushButton("Set Up Printer")
        self._hw_printer_btn.setToolTip("Runs: ujust setup-printer")
        self._hw_printer_btn.hide()
        self._hw_printer_btn.clicked.connect(
            lambda _=False: self._run_ujust("setup-printer", self._hw_printer_btn))
        hw_btns.addWidget(self._hw_printer_btn)
        hw_open_btn = QPushButton("Open Hardware")
        hw_open_btn.clicked.connect(lambda _=False: self._navigate("Hardware"))
        hw_btns.addWidget(hw_open_btn)
        hw_btns.addStretch()
        hw_layout.addLayout(hw_btns)
        self._add(hw_card)
        # Pages are built eagerly at startup; defer the subprocess probes.
        single_shot(self, 900, self._run_hw_sanity)



    def _refresh_localsend_btn(self):
        installed = _is_flatpak_installed("org.localsend.localsend_app")
        self._localsend_btn.setText("Open LocalSend" if installed else "Install LocalSend")


    def _open_or_install_localsend(self):
        app_id = "org.localsend.localsend_app"
        if _is_flatpak_installed(app_id):
            try:
                flatpak_run(app_id)
                self._nearby_status.setText("LocalSend opened. Devices on the same network appear automatically.")
            except OSError as exc:
                self._nearby_status.setText(f"Could not open LocalSend: {exc}")
            return

        def _installed(code: int):
            if code == 0:
                self._localsend_btn.setEnabled(True)
                self._refresh_localsend_btn()
                self._nearby_status.setText("LocalSend installed — open it on both devices to start sharing.")

        _install_flatpak_inline(
            self, self._localsend_btn, app_id, "LocalSend", done_cb=_installed,
        )


    def _send_nearby_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Send files to a nearby device", os.path.expanduser("~")
        )
        if not paths:
            return
        helper = "/usr/bin/kyth-nearby-share"
        if not os.path.exists(helper):
            self._nearby_status.setText(
                "Nearby Sharing is available after applying the latest KythOS update and restarting."
            )
            return
        try:
            popen([helper, *paths])
            self._nearby_status.setText("Choose the destination device in the Nearby Sharing prompt.")
        except OSError as exc:
            self._nearby_status.setText(f"Could not start Nearby Sharing: {exc}")


    def _open_krunner(self):
        for cmd in (
            ["krunner"],
            ["qdbus6", "org.kde.krunner", "/App", "display"],
            ["qdbus-qt6", "org.kde.krunner", "/App", "display"],
            ["qdbus", "org.kde.krunner", "/App", "display"],
        ):
            if popen(cmd):
                self._powertoys_status.setText("")
                return
        self._powertoys_status.setText("KRunner is not available in this session. Press Alt+Space after signing into Plasma.")


    def _open_settings_module(self, module: str, label: str):
        if kcmshell(module) or systemsettings(module) or systemsettings():
            self._powertoys_status.setText("")
            return
        self._powertoys_status.setText(f"Could not open {label} in this session.")

    # ── Hardware sanity ───────────────────────────────────────────────────────


    def _run_hw_sanity(self):
        if self._hw_worker is not None and self._hw_worker.isRunning():
            return
        self._hw_status.setText("Checking…")
        self._hw_status.show()
        worker = DataWorker("hw-sanity", _collect_hw_sanity)
        worker.result.connect(self._on_hw_sanity)
        self._hw_worker = worker
        release_worker_when_finished(self, "_hw_worker", worker)
        worker.start()


    def _on_hw_sanity(self, _key: str, rows: list):
        self._clear_layout(self._hw_rows)
        if not rows:
            self._hw_status.setText("Could not run the hardware checks in this session.")
            return
        self._hw_status.hide()
        printer_missing = False
        for status, title, text in rows:
            if title == "Printer" and status == "warn":
                printer_missing = True
            self._hw_rows.addWidget(self._make_migration_row(status, title, text))
        self._hw_printer_btn.setVisible(printer_missing)

    # ── Copy My Files ─────────────────────────────────────────────────────────
