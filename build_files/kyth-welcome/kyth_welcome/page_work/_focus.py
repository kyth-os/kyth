import shutil

# __KYTH_GENERATED_IMPORTS__
from ..services.launch import popen
from ..services.software import _chromium_app_window_cmd, _is_flatpak_installed
from ..qt import (  # noqa: E501
    QCheckBox, QComboBox, QDBusConnection, QDBusInterface, QHBoxLayout, QLabel, QPushButton,
)
from ..widgets import _make_card


class _FocusMixin:
    def _make_focus_card(self):
        card, layout = _make_card("card-accent-ok")
        title = QLabel("5. Focus Assist \u2014 quiet work sessions")
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
                popen(cmd)
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
                    self._focus_inhibit_proc = popen([
                        "systemd-inhibit", "--what=idle:sleep",
                        "--why=KythOS Focus Session", "--mode=block",
                        "sleep", str(minutes * 60 + 60),
                    ])
                    if self._focus_inhibit_proc is None:
                        warnings.append("sleep inhibition was unavailable")
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
            f"Focus session active \u2014 {minutes:02d}:{seconds:02d} remaining. "
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
            popen([
                "notify-send", "Focus session complete",
                "Take a short break before starting another block.",
            ])
