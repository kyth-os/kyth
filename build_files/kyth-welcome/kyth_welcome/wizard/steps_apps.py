"""Wizard step builders — _AppsStepMixin."""
from __future__ import annotations

import shlex

from ..core_base import _cancel_worker, _restyle
from ..services.software import Worker, _finish_worker, _is_flatpak_installed
from ..qt import (
    QCheckBox, QDesktopServices, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QTextEdit, QUrl,
    QVBoxLayout, QWidget, Qt,
)
from ..widgets import _make_card, _set_log_panel

_GAMING_APP_IDS = {
    "com.valvesoftware.Steam", "com.discordapp.Discord", "com.obsproject.Studio",
    "org.freedesktop.Piper", "com.moonlight_stream.Moonlight",
    "com.github.mtkennerly.ludusavi",
}
_EVERYDAY_APP_IDS = {
    "com.brave.Browser", "org.libreoffice.LibreOffice", "eu.betterbird.Betterbird",
    "org.videolan.VLC",
}


class _AppsStepMixin:
    def _make_first_run_apps_step(self) -> QWidget:
        page = QWidget()
        page.setObjectName("wiz-body")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(52, 40, 52, 28)
        layout.setSpacing(14)

        pill = QLabel("GET APPS")
        pill.setObjectName("wiz-pill")
        layout.addWidget(pill)

        title = QLabel("Add what you actually use.")
        title.setObjectName("wiz-heading")
        layout.addWidget(title)

        subtitle = QLabel(
            "Your core gaming setup is already handled. Pick anything else you want now; "
            "you can install or remove these later from the System Hub."
        )
        subtitle.setObjectName("wiz-subheading")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        core_card, core_layout = _make_card("wiz-card-ok")
        core_title = QLabel("Game-ready defaults")
        core_title.setObjectName("wiz-card-title")
        core_layout.addWidget(core_title)
        core_copy = QLabel(
            "Heroic Games Launcher, Lutris, ProtonUp-Qt, and protontricks install automatically "
            "as soon as networking is available."
        )
        core_copy.setObjectName("wiz-card-copy")
        core_copy.setWordWrap(True)
        core_layout.addWidget(core_copy)
        layout.addWidget(core_card)

        prep_row = QHBoxLayout()
        prep_row.setSpacing(12)

        install_model, install_model_layout = _make_card("wiz-card-ok")
        install_model_title = QLabel("Install apps the KythOS way")
        install_model_title.setObjectName("wiz-card-title")
        install_model_layout.addWidget(install_model_title)
        install_model_copy = QLabel(
            "Use App Store or Flathub first. Standalone .exe and .msi installers "
            "belong in Bottles, while downloaded .rpm packages are system packages for "
            "mutable Fedora-style installs and are usually the wrong path on KythOS."
        )
        install_model_copy.setObjectName("wiz-card-copy")
        install_model_copy.setWordWrap(True)
        install_model_layout.addWidget(install_model_copy)
        install_model_btns = QHBoxLayout()
        install_model_btns.setSpacing(8)
        flathub_btn = QPushButton("Browse Flathub")
        flathub_btn.clicked.connect(
            lambda _=False: QDesktopServices.openUrl(QUrl("https://flathub.org"))
        )
        install_model_btns.addWidget(flathub_btn)
        install_model_btns.addStretch()
        install_model_layout.addLayout(install_model_btns)
        prep_row.addWidget(install_model, 1)

        gaps_card, gaps_layout = _make_card("wiz-card")
        gaps_title = QLabel("Check daily-driver gaps now")
        gaps_title.setObjectName("wiz-card-title")
        gaps_layout.addWidget(gaps_title)
        gaps_copy = QLabel(
            "Game Pass is browser/cloud-first here, Microsoft 365 and OneDrive use web "
            "or cloud helpers, Adobe apps need native alternatives, and iCUE, G HUB, "
            "Synapse, and SteelSeries GG become OpenRGB, Piper, or vendor-limited "
            "workflows depending on the device."
        )
        gaps_copy.setObjectName("wiz-card-copy")
        gaps_copy.setWordWrap(True)
        gaps_layout.addWidget(gaps_copy)
        prep_row.addWidget(gaps_card, 1)
        layout.addLayout(prep_row)

        catalog = [
            ("com.valvesoftware.Steam",       "Steam",          "Valve's game store and Proton launcher for your Steam library."),
            ("com.discordapp.Discord",        "Discord",        "Voice, text, and community chat — used by almost every gaming community."),
            ("com.brave.Browser",             "Brave Browser",  "Fast, privacy-friendly browser with good media support."),
            ("com.obsproject.Studio",         "OBS Studio",     "Record and stream your gameplay."),
            ("org.videolan.VLC",              "VLC",            "Plays virtually every video and audio format without extra codecs."),
            ("org.libreoffice.LibreOffice",   "LibreOffice",    "Open Word, Excel, and PowerPoint files — full office suite."),
            ("eu.betterbird.Betterbird",      "Betterbird",     "Work email, calendar, and contacts — connects to Microsoft 365, Gmail, and IMAP."),
            ("com.github.mtkennerly.ludusavi","Ludusavi",       "Back up and restore game saves before migration or modding."),
            ("org.freedesktop.Piper",         "Piper",          "Configure supported gaming mice for DPI, buttons, and LEDs."),
            ("com.moonlight_stream.Moonlight","Moonlight",      "Stream games from another PC or NVIDIA Shield on your network."),
        ]
        # Profile-relevant apps float to the top; nothing is hidden, since any
        # checkbox can still be selected regardless of the chosen profile.
        relevant = _GAMING_APP_IDS if self._profile == "gaming" else _EVERYDAY_APP_IDS
        self._wizard_extra_apps = sorted(catalog, key=lambda item: item[0] not in relevant)

        extras_card, extras_layout = _make_card("wiz-card")
        extras_title = QLabel("Optional apps")
        extras_title.setObjectName("wiz-card-title")
        extras_layout.addWidget(extras_title)

        apps_view = QScrollArea()
        apps_view.setWidgetResizable(True)
        apps_view.setMinimumHeight(230)
        apps_view.setFrameShape(QFrame.Shape.NoFrame)
        apps_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        apps_widget = QWidget()
        apps_layout = QVBoxLayout(apps_widget)
        apps_layout.setContentsMargins(0, 0, 8, 0)
        apps_layout.setSpacing(10)

        self._wizard_extra_checks = []
        for app_id, name, desc in self._wizard_extra_apps:
            row = QWidget()
            row.setMinimumHeight(48)
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)

            already_installed = _is_flatpak_installed(app_id)
            check = QCheckBox()
            check.setChecked(not already_installed and app_id in relevant)
            check.setEnabled(not already_installed)
            self._wizard_extra_checks.append((check, app_id, name))
            row_layout.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name_lbl = QLabel(name)
            name_lbl.setObjectName("wiz-card-title")
            name_lbl.setStyleSheet("font-size: 13px;")
            desc_lbl = QLabel("Already installed." if already_installed else desc)
            desc_lbl.setObjectName("wiz-card-copy")
            desc_lbl.setWordWrap(True)
            text_col.addWidget(name_lbl)
            text_col.addWidget(desc_lbl)
            row_layout.addLayout(text_col, 1)
            apps_layout.addWidget(row)

        apps_layout.addStretch()
        apps_view.setWidget(apps_widget)
        extras_layout.addWidget(apps_view, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._wizard_install_btn = QPushButton("Install Selected")
        self._wizard_install_btn.setObjectName("primary")
        self._wizard_install_btn.clicked.connect(self._install_selected_wizard_apps)
        btn_row.addWidget(self._wizard_install_btn)
        self._wizard_cancel_install_btn = QPushButton("Cancel Install")
        self._wizard_cancel_install_btn.clicked.connect(self._cancel_selected_wizard_apps)
        self._wizard_cancel_install_btn.hide()
        btn_row.addWidget(self._wizard_cancel_install_btn)
        select_none_btn = QPushButton("Clear")
        select_none_btn.clicked.connect(lambda: [check.setChecked(False) for check, _, _ in self._wizard_extra_checks])
        btn_row.addWidget(select_none_btn)
        btn_row.addStretch()
        extras_layout.addLayout(btn_row)

        self._wizard_install_status = QLabel("Select apps above, or continue if you only want the gaming defaults.")
        self._wizard_install_status.setObjectName("wiz-subheading")
        extras_layout.addWidget(self._wizard_install_status)

        self._wizard_install_progress = QProgressBar()
        self._wizard_install_progress.setRange(0, 100)
        self._wizard_install_progress.setValue(0)
        self._wizard_install_progress.hide()
        extras_layout.addWidget(self._wizard_install_progress)

        self._wizard_install_log_toggle = QPushButton("Show details")
        self._wizard_install_log_toggle.setCheckable(True)
        self._wizard_install_log_toggle.hide()
        extras_layout.addWidget(self._wizard_install_log_toggle)

        self._wizard_install_log = QTextEdit()
        self._wizard_install_log.document().setMaximumBlockCount(5000)
        self._wizard_install_log.setReadOnly(True)
        self._wizard_install_log.setMaximumHeight(120)
        self._wizard_install_log.hide()
        extras_layout.addWidget(self._wizard_install_log)
        self._wizard_install_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._wizard_install_log_toggle, self._wizard_install_log, checked)
        )

        layout.addWidget(extras_card, 1)
        self._wizard_extra_worker = None
        return page


    def _install_selected_wizard_apps(self):
        if self._wizard_extra_worker and self._wizard_extra_worker.isRunning():
            return
        selected = [
            (app_id, name)
            for check, app_id, name in self._wizard_extra_checks
            if check.isChecked() and check.isEnabled()
        ]
        if not selected:
            self._wizard_install_status.setText("No optional apps selected.")
            self._wizard_install_status.setObjectName("status-dim")
            _restyle(self._wizard_install_status)
            return

        names = ", ".join(name for _, name in selected)
        self._wizard_install_btn.setEnabled(False)
        self._wizard_cancel_install_btn.setEnabled(True)
        self._wizard_cancel_install_btn.show()
        for check, _, _ in self._wizard_extra_checks:
            check.setEnabled(False)
        self._wizard_install_total = len(selected)
        self._wizard_install_done = 0
        self._wizard_install_status.setText(f"Preparing to install {names}...")
        self._wizard_install_status.setObjectName("wiz-subheading")
        _restyle(self._wizard_install_status)
        self._wizard_install_progress.setRange(0, len(selected))
        self._wizard_install_progress.setValue(0)
        self._wizard_install_progress.show()
        self._wizard_install_log.clear()
        self._wizard_install_log.append("-> flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo")
        for app_id, name in selected:
            self._wizard_install_log.append(f"-> flatpak install -y flathub {app_id}  # {name}")
        self._wizard_install_log.append("")
        self._wizard_install_log_toggle.show()
        _set_log_panel(self._wizard_install_log_toggle, self._wizard_install_log, False)

        script = [
            "set -e",
            "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo",
        ]
        for app_id, name in selected:
            script.append(f"echo __KYTH_APP_START__:{shlex.quote(app_id)}:{shlex.quote(name)}")
            script.append(f"flatpak install -y flathub {shlex.quote(app_id)}")
            script.append(f"echo __KYTH_APP_DONE__:{shlex.quote(app_id)}:{shlex.quote(name)}")
        cmd = ["bash", "-c", "\n".join(script)]
        self._wizard_extra_worker = Worker(cmd)
        self._wizard_extra_worker.line.connect(self._on_wizard_extra_install_line)
        self._wizard_extra_worker.done.connect(
            lambda code, installed=selected: self._on_wizard_extra_install_done(code, installed)
        )
        self._wizard_extra_worker.start()
        self._update_nav()


    def _cancel_selected_wizard_apps(self):
        reply = QMessageBox.question(
            self,
            "Cancel App Install?",
            "Stop installing the selected apps? Apps that already finished installing will remain available.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        _cancel_worker(
            self,
            attr="_wizard_extra_worker",
            status_lbl=self._wizard_install_status,
            log=self._wizard_install_log,
            cancel_btn=self._wizard_cancel_install_btn,
            message="Cancelling optional app install…",
        )


    def _on_wizard_extra_install_line(self, line: str):
        if line.startswith("__KYTH_APP_START__:"):
            parts = line.split(":", 2)
            name = parts[2] if len(parts) > 2 else "selected app"
            current = getattr(self, "_wizard_install_done", 0) + 1
            total = max(1, getattr(self, "_wizard_install_total", 1))
            self._wizard_install_status.setText(f"Installing {name} ({current} of {total})...")
            self._wizard_install_status.setObjectName("wiz-subheading")
            _restyle(self._wizard_install_status)
            return
        if line.startswith("__KYTH_APP_DONE__:"):
            parts = line.split(":", 2)
            name = parts[2] if len(parts) > 2 else "app"
            self._wizard_install_done = getattr(self, "_wizard_install_done", 0) + 1
            total = max(1, getattr(self, "_wizard_install_total", 1))
            self._wizard_install_progress.setValue(self._wizard_install_done)
            self._wizard_install_status.setText(f"Installed {name} ({self._wizard_install_done} of {total}).")
            return
        self._wizard_install_log.append(line)
        self._wizard_install_log.ensureCursorVisible()


    def _on_wizard_extra_install_done(self, code: int, installed: list[tuple[str, str]]):
        _finish_worker(self, attr="_wizard_extra_worker")
        self._wizard_cancel_install_btn.hide()
        if code == Worker.CANCELLED:
            self._wizard_install_status.setText("Optional app install cancelled. Apps that finished installing are still available.")
            self._wizard_install_status.setObjectName("status-warn")
            self._wizard_install_log.append("\nCancelled.")
            for check, app_id, _ in self._wizard_extra_checks:
                check.setEnabled(not _is_flatpak_installed(app_id))
        elif code == 0:
            self._wizard_install_progress.setValue(max(1, getattr(self, "_wizard_install_total", 1)))
            self._wizard_install_status.setText("Optional apps installed.")
            self._wizard_install_status.setObjectName("status-ok")
            self._wizard_install_log.append("\nDone.")
            installed_ids = {app_id for app_id, _ in installed}
            for check, app_id, _ in self._wizard_extra_checks:
                check.setChecked(False)
                check.setEnabled(app_id not in installed_ids)
        else:
            self._wizard_install_status.setText(f"Optional app install failed (exit {code}).")
            self._wizard_install_status.setObjectName("status-err")
            for check, app_id, _ in self._wizard_extra_checks:
                check.setEnabled(not _is_flatpak_installed(app_id))
        self._wizard_install_btn.setEnabled(True)
        _restyle(self._wizard_install_status)
        self._update_nav()
