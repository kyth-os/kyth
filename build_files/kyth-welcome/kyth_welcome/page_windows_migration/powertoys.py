"""Windows Migration page — PowerToys-equivalents card + handlers, _PowerToysMixin."""

from __future__ import annotations

from ..services.launch import popen, systemsettings, kcmshell
from ..qt import (
    QHBoxLayout, QLabel, QPushButton,
)
from ..widgets import (
    _make_card,
)


class _PowerToysMixin:
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
