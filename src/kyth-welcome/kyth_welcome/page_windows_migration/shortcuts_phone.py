"""Windows Migration page — shortcuts phone cards + handlers, _ShortcutsPhoneMixin."""

from __future__ import annotations

from ..core_base import restyle
from ..services.phone_link import (
    _configure_dynamic_lock_service,
    _kdeconnect_devices,
    _load_dynamic_lock_config,
    _mount_kdeconnect_device,
    _run_kdeconnect_action,
    _save_dynamic_lock_config,
    _send_kdeconnect_sms,
)
from ..services.runtime import DataWorker, guard_disposed, release_worker_when_finished
from ..services.launch import popen, systemsettings, kcmshell
from ..qt import (
    QComboBox, QDesktopServices, QHBoxLayout, QInputDialog, QLabel, QPushButton, QUrl, single_shot,
)
from ..widgets import (
    ToggleSwitch, _make_card,
)


class _ShortcutsPhoneMixin:
    def _build_shortcuts_card(self):
        # Windows keyboard muscle memory
        shortcuts_card, shortcuts_layout = _make_card()
        shortcuts_title = QLabel("Keep your Windows keyboard shortcuts")
        shortcuts_title.setObjectName("card-title")
        shortcuts_layout.addWidget(shortcuts_title)
        shortcuts_body = QLabel(
            "Most familiar shortcuts already work on KythOS: Win+L locks, Win+D shows the desktop, "
            "Alt+Tab switches windows, Win+. opens the emoji picker. This adds the rest:"
        )
        shortcuts_body.setObjectName("card-copy")
        shortcuts_body.setWordWrap(True)
        shortcuts_layout.addWidget(shortcuts_body)
        for keys, what in (
            ("Win+E", "Open the file manager (Dolphin)"),
            ("Win+Shift+S", "Snip a region of the screen (Spectacle)"),
            ("Win+V", "Show clipboard history at the cursor"),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            keys_lbl = QLabel(keys)
            keys_lbl.setObjectName("launch-opt-value")
            keys_lbl.setMinimumWidth(110)
            row.addWidget(keys_lbl)
            what_lbl = QLabel(what)
            what_lbl.setObjectName("card-copy")
            row.addWidget(what_lbl, 1)
            shortcuts_layout.addLayout(row)
        self._shortcuts_status = QLabel("")
        self._shortcuts_status.setObjectName("card-copy")
        self._shortcuts_status.setWordWrap(True)
        shortcuts_layout.addWidget(self._shortcuts_status)
        shortcuts_btns = QHBoxLayout()
        shortcuts_btns.setSpacing(8)
        shortcuts_apply_btn = QPushButton("Apply Familiar Shortcuts")
        shortcuts_apply_btn.setObjectName("primary")
        shortcuts_apply_btn.clicked.connect(self._apply_windows_shortcuts)
        shortcuts_btns.addWidget(shortcuts_apply_btn)
        shortcuts_revert_btn = QPushButton("Restore KDE Defaults")
        shortcuts_revert_btn.clicked.connect(self._revert_windows_shortcuts)
        shortcuts_btns.addWidget(shortcuts_revert_btn)
        shortcuts_btns.addStretch()
        shortcuts_layout.addLayout(shortcuts_btns)
        self._add(shortcuts_card)



    def _build_phone_card(self):
        # Phone Link replacement
        phone_card, phone_layout = _make_card("card-accent-ok")
        phone_title = QLabel("Phone Link → Connected Devices")
        phone_title.setObjectName("card-title")
        phone_layout.addWidget(phone_title)
        phone_body = QLabel(
            "On Windows you had Phone Link; KythOS has KDE Connect built in. Pair your phone "
            "over Wi-Fi to see and answer notifications on the desktop, send files both ways, "
            "share the clipboard, control media, ring a lost phone, and optionally lock this PC "
            "when your trusted device leaves. Both devices must be on the same network."
        )
        phone_body.setObjectName("card-copy")
        phone_body.setWordWrap(True)
        phone_layout.addWidget(phone_body)

        device_row = QHBoxLayout()
        device_row.setSpacing(8)
        device_row.addWidget(QLabel("Paired device:"))
        self._phone_device = QComboBox()
        self._phone_device.setMinimumWidth(260)
        self._phone_device.currentIndexChanged.connect(self._update_phone_controls)
        device_row.addWidget(self._phone_device)
        refresh_phone_btn = QPushButton("Refresh")
        refresh_phone_btn.clicked.connect(self._refresh_phone_devices)
        device_row.addWidget(refresh_phone_btn)
        open_phone_btn = QPushButton("Pair / Manage Devices")
        open_phone_btn.clicked.connect(self._open_kde_connect)
        device_row.addWidget(open_phone_btn)
        device_row.addStretch()
        phone_layout.addLayout(device_row)

        phone_actions = QHBoxLayout()
        phone_actions.setSpacing(8)
        self._phone_action_buttons = []
        for label, action, tip in (
            ("Ping", "--ping", "Show a test notification on the selected device."),
            ("Ring Device", "--ring", "Ring the selected device so you can find it."),
            ("Send Clipboard", "--send-clipboard", "Send the current desktop clipboard to the selected device."),
            ("Send Text", "--send-sms", "Send an SMS through a paired Android phone."),
            ("Browse Files", "--mount", "Mount the selected device and open its shared files in Dolphin."),
        ):
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(
                lambda _=False, selected_action=action: self._run_phone_action(selected_action)
            )
            phone_actions.addWidget(btn)
            self._phone_action_buttons.append(btn)
        phone_actions.addStretch()
        phone_layout.addLayout(phone_actions)

        dynamic_lock_row = QHBoxLayout()
        dynamic_lock_row.setSpacing(8)
        dynamic_lock_row.addWidget(QLabel("Dynamic Lock: lock this PC when the device leaves"))
        self._dynamic_lock_check = ToggleSwitch()
        dynamic_lock_row.addWidget(self._dynamic_lock_check)
        dynamic_lock_row.addWidget(QLabel("Wait:"))
        self._dynamic_lock_grace = QComboBox()
        for label, seconds in (("30 seconds", 30), ("1 minute", 60), ("2 minutes", 120)):
            self._dynamic_lock_grace.addItem(label, seconds)
        dynamic_lock_row.addWidget(self._dynamic_lock_grace)
        save_lock_btn = QPushButton("Save Trusted Device")
        save_lock_btn.clicked.connect(self._save_dynamic_lock)
        dynamic_lock_row.addWidget(save_lock_btn)
        dynamic_lock_row.addStretch()
        phone_layout.addLayout(dynamic_lock_row)

        lock_config = _load_dynamic_lock_config()
        self._dynamic_lock_check.setChecked(lock_config.get("enabled") is True)
        try:
            grace = int(lock_config.get("grace_seconds") or 60)
        except (TypeError, ValueError):
            grace = 60
        for idx in range(self._dynamic_lock_grace.count()):
            if self._dynamic_lock_grace.itemData(idx) == grace:
                self._dynamic_lock_grace.setCurrentIndex(idx)
                break
        self._phone_status = QLabel("")
        self._phone_status.setObjectName("card-copy")
        self._phone_status.setWordWrap(True)
        phone_layout.addWidget(self._phone_status)
        phone_btns = QHBoxLayout()
        phone_btns.setSpacing(8)
        phone_android_btn = QPushButton("Android App")
        phone_android_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl("https://play.google.com/store/apps/details?id=org.kde.kdeconnect_tp")))
        phone_btns.addWidget(phone_android_btn)
        phone_ios_btn = QPushButton("iPhone App")
        phone_ios_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl("https://apps.apple.com/app/kde-connect/id1580245991")))
        phone_btns.addWidget(phone_ios_btn)
        phone_btns.addStretch()
        phone_layout.addLayout(phone_btns)
        self._add(phone_card)
        single_shot(self, 0, self._refresh_phone_devices)



    def _run_shortcut_change(self, delete: bool) -> bool:
        from .services.plasma import apply_windows_shortcuts
        ok, err = apply_windows_shortcuts(delete=delete)
        if not ok and err:
            self._shortcuts_status.setText(err)
            return False
        return ok


    def _apply_windows_shortcuts(self):
        if self._run_shortcut_change(delete=False):
            self._shortcuts_status.setText(
                "✓ familiar shortcuts applied — try Win+E. If a shortcut doesn't respond, sign out and back in."
            )


    def _revert_windows_shortcuts(self):
        if self._run_shortcut_change(delete=True):
            self._shortcuts_status.setText("✓ KDE default shortcuts restored.")


    def _open_kde_connect(self):
        if popen(["kdeconnect-app"]) or kcmshell("kcm_kdeconnect") or systemsettings("kcm_kdeconnect"):
            self._phone_status.setText("")
            return
        self._phone_status.setText(
            "KDE Connect isn't available in this session — install it from the App Store, "
            "or check System Settings → Connected Devices."
        )


    def _selected_phone_device(self) -> dict | None:
        data = self._phone_device.currentData()
        return data if isinstance(data, dict) else None


    def _refresh_phone_devices(self):
        if self._phone_worker is not None and self._phone_worker.isRunning():
            return
        self._phone_status.setObjectName("card-copy")
        restyle(self._phone_status)
        self._phone_status.setText("Looking for paired devices…")
        worker = DataWorker("kdeconnect-devices", _kdeconnect_devices)
        worker.result.connect(guard_disposed(self._on_phone_devices))
        worker.failed.connect(
            guard_disposed(lambda _key, message: self._phone_status.setText(
                f"Could not query KDE Connect: {message}"
            ))
        )
        self._phone_worker = worker
        release_worker_when_finished(self, "_phone_worker", worker)
        worker.start()


    def _on_phone_devices(self, _key: str, devices: list[dict]):
        config = _load_dynamic_lock_config()
        configured_id = str(config.get("device_id") or "")
        if configured_id and not any(item["id"] == configured_id for item in devices):
            devices.append({
                "id": configured_id,
                "name": str(config.get("device_name") or "Trusted device"),
                "reachable": False,
            })

        self._phone_device.blockSignals(True)
        self._phone_device.clear()
        selected_index = 0
        for idx, device in enumerate(devices):
            state = "Connected" if device["reachable"] else "Offline"
            self._phone_device.addItem(f"{device['name']} — {state}", device)
            if device["id"] == configured_id:
                selected_index = idx
        if devices:
            self._phone_device.setCurrentIndex(selected_index)
        else:
            self._phone_device.addItem("No paired devices found", None)
        self._phone_device.blockSignals(False)
        self._update_phone_controls()

        connected = sum(1 for item in devices if item["reachable"])
        if connected:
            self._phone_status.setText(
                f"{connected} connected device{'s' if connected != 1 else ''}. "
                "Notifications and clipboard sharing are managed by KDE Connect."
            )
        elif devices:
            self._phone_status.setText(
                "Paired device found, but it is offline. Wake it and put both devices on the same network."
            )
        else:
            self._phone_status.setText(
                "No paired devices yet. Install KDE Connect on your phone, then choose Pair / Manage Devices."
            )


    def _update_phone_controls(self, _index: int = -1):
        device = self._selected_phone_device()
        reachable = bool(device and device.get("reachable"))
        for btn in self._phone_action_buttons:
            btn.setEnabled(reachable)


    def _run_phone_action(self, action: str):
        if self._phone_action_worker is not None and self._phone_action_worker.isRunning():
            return
        device = self._selected_phone_device()
        if not device or not device.get("reachable"):
            self._phone_status.setText("Choose a connected device first.")
            return
        labels = {
            "--ping": "Sending ping",
            "--ring": "Ringing device",
            "--send-clipboard": "Sending clipboard",
            "--send-sms": "Sending text message",
            "--mount": "Connecting device files",
        }
        destination = ""
        message = ""
        if action == "--send-sms":
            destination, accepted = QInputDialog.getText(
                self, "Send Text Message", "Phone number:"
            )
            if not accepted or not destination.strip():
                return
            message, accepted = QInputDialog.getMultiLineText(
                self, "Send Text Message", "Message:"
            )
            if not accepted or not message.strip():
                return
        self._phone_status.setObjectName("card-copy")
        restyle(self._phone_status)
        self._phone_status.setText(f"{labels.get(action, 'Contacting device')}…")
        if action == "--mount":
            fn = lambda: _mount_kdeconnect_device(device["id"])
        elif action == "--send-sms":
            fn = lambda: _send_kdeconnect_sms(
                device["id"], destination.strip(), message.strip()
            )
        else:
            fn = lambda: _run_kdeconnect_action(device["id"], action)
        worker = DataWorker(f"phone-action:{action}", fn)
        worker.result.connect(guard_disposed(self._on_phone_action))
        worker.failed.connect(guard_disposed(lambda _key, message: self._phone_status.setText(f"Device action failed: {message}")))
        self._phone_action_worker = worker
        release_worker_when_finished(self, "_phone_action_worker", worker)
        worker.start()


    def _on_phone_action(self, key: str, result: tuple[bool, str]):
        ok, detail = result
        action = key.partition(":")[2]
        if ok and action == "--mount":
            QDesktopServices.openUrl(QUrl.fromLocalFile(detail))
            self._phone_status.setText("Device files opened in the file manager.")
        elif ok:
            messages = {
                "--ping": "Ping sent.",
                "--ring": "The device should be ringing now.",
                "--send-clipboard": "Clipboard sent to the device.",
                "--send-sms": "Text message sent through the paired phone.",
            }
            self._phone_status.setText(messages.get(action, detail or "Done."))
        else:
            self._phone_status.setText(detail or "The device action failed.")


    def _save_dynamic_lock(self):
        if self._dynamic_lock_worker is not None and self._dynamic_lock_worker.isRunning():
            return
        enabled = self._dynamic_lock_check.isChecked()
        device = self._selected_phone_device()
        if enabled and not device:
            self._phone_status.setText("Pair and select a trusted device before enabling Dynamic Lock.")
            return
        config = {
            "enabled": enabled,
            "device_id": device["id"] if device else "",
            "device_name": device["name"] if device else "",
            "grace_seconds": int(self._dynamic_lock_grace.currentData() or 60),
        }
        try:
            _save_dynamic_lock_config(config)
        except OSError as exc:
            self._phone_status.setText(f"Could not save Dynamic Lock: {exc}")
            return
        self._phone_status.setText("Saving Dynamic Lock settings…")
        worker = DataWorker(
            "dynamic-lock", lambda: _configure_dynamic_lock_service(enabled)
        )
        worker.result.connect(guard_disposed(self._on_dynamic_lock_saved))
        worker.failed.connect(guard_disposed(lambda _key, message: self._phone_status.setText(f"Could not update Dynamic Lock: {message}")))
        self._dynamic_lock_worker = worker
        release_worker_when_finished(self, "_dynamic_lock_worker", worker)
        worker.start()


    def _on_dynamic_lock_saved(self, _key: str, result: tuple[bool, str]):
        ok, detail = result
        self._phone_status.setText(detail)
        self._phone_status.setObjectName("status-ok" if ok else "status-warn")
        restyle(self._phone_status)
