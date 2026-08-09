import shutil

# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.workers import ControllerProbeWorker
from .services.hardware import controller_status_view
from .services.runtime import Worker, release_worker_when_finished
from .services.privileged import AuthFrontend, helper_action
from .qt import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton,
)
from .services.launch import flatpak_run, popen, systemsettings
from .widgets import (
    Page, _make_card, _make_flow_step,
)



class ControllerPage(Page):
    def __init__(self):
        super().__init__()
        self._probe_worker: ControllerProbeWorker | None = None
        self._probed = False
        # Arch #12: hotplug — re-probe debounced 300ms on udev poll when page visible
        from .qt import QTimer

        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setSingleShot(True)
        self._hotplug_timer.setInterval(300)
        self._hotplug_timer.timeout.connect(self._start_probe)

        self._page_header(
            "Gaming",
            "Controllers",
            "Connect a controller and KythOS will configure it automatically. "
            "This page helps with wireless setup, driver status, and DualSense features.",
        )

        # ── Connected controllers ──────────────────────────────────────────────
        self._status_card, self._status_layout = _make_card()
        status_top = QHBoxLayout()
        status_title = QLabel("Connected Controllers")
        status_title.setObjectName("card-title")
        status_top.addWidget(status_title)
        status_top.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._start_probe)
        status_top.addWidget(self._refresh_btn)
        self._rumble_btn = QPushButton("Test Rumble")
        self._rumble_btn.setToolTip("Vibrate the first detected gamepad for 1 second (fftest)")
        self._rumble_btn.clicked.connect(self._test_rumble)
        status_top.addWidget(self._rumble_btn)
        self._steam_input_btn = QPushButton("Steam Input")
        self._steam_input_btn.setToolTip("Open Steam Controller settings")
        self._steam_input_btn.clicked.connect(lambda: flatpak_run("com.valvesoftware.Steam", "steam://open/controllersettings"))
        status_top.addWidget(self._steam_input_btn)
        self._status_layout.addLayout(status_top)
        self._status_lbl = QLabel("Scanning…")
        self._status_lbl.setObjectName("card-copy")
        self._status_lbl.setWordWrap(True)
        self._status_layout.addWidget(self._status_lbl)
        self._add(self._status_card)

        # ── Xbox Wireless Adapter ──────────────────────────────────────────────
        xbox_card, xbox_layout = _make_card()
        xbox_title = QLabel("Xbox — Wireless USB Adapter")
        xbox_title.setObjectName("card-title")
        xbox_layout.addWidget(xbox_title)
        xbox_desc = QLabel(
            "The Xbox Wireless USB Adapter requires a one-time firmware flash before "
            "controllers can pair with it. If you are using a wired USB cable or an "
            "official Xbox controller over Bluetooth, no extra setup is needed."
        )
        xbox_desc.setObjectName("card-copy")
        xbox_desc.setWordWrap(True)
        xbox_layout.addWidget(xbox_desc)

        self._xone_status_lbl = QLabel()
        self._xone_status_lbl.setObjectName("card-copy")
        xbox_layout.addWidget(self._xone_status_lbl)

        self._xone_btn = QPushButton("Flash Xbox Dongle Firmware")
        self._xone_btn.setObjectName("primary")
        self._xone_btn.hide()
        self._xone_btn.clicked.connect(self._flash_xone)
        xbox_layout.addWidget(self._xone_btn)

        xbox_bt_label = QLabel("Pair over Bluetooth (no dongle):")
        xbox_bt_label.setObjectName("card-copy")
        xbox_layout.addWidget(xbox_bt_label)
        for index, (step_title, copy) in enumerate((
            ("Press and hold the Xbox button", "For 3 seconds, until it flashes."),
            ("Hold the Sync button", "Top of the controller, until it flashes rapidly."),
            ("Add the device", "System Tray → Bluetooth → Add Device."),
        ), 1):
            xbox_layout.addWidget(_make_flow_step(index, step_title, copy))

        xbox_bt_btn = QPushButton("Open Bluetooth Settings")
        xbox_bt_btn.clicked.connect(lambda: systemsettings("kcm_bluetooth"))
        xbox_layout.addWidget(xbox_bt_btn)
        self._add(xbox_card)

        # ── PlayStation ────────────────────────────────────────────────────────
        ps_card, ps_layout = _make_card()
        ps_title = QLabel("PlayStation — DualSense & DualShock 4")
        ps_title.setObjectName("card-title")
        ps_layout.addWidget(ps_title)
        ps_desc = QLabel(
            "DualSense works wired and over Bluetooth. KythOS ships udev rules that grant "
            "the hidraw interface to the logged-in user, enabling adaptive triggers and haptics "
            "in supported games via Steam Input and the hid-playstation kernel module."
        )
        ps_desc.setObjectName("card-copy")
        ps_desc.setWordWrap(True)
        ps_layout.addWidget(ps_desc)

        ps_bt_label = QLabel("Pair over Bluetooth:")
        ps_bt_label.setObjectName("card-copy")
        ps_layout.addWidget(ps_bt_label)
        for index, (step_title, copy) in enumerate((
            ("DualSense (PS5)", "Hold PS + Create until the light bar blinks."),
            ("DualShock 4 (PS4)", "Hold PS + Share until the light bar blinks."),
            ("Add the device", "System Tray → Bluetooth → Add Device."),
        ), 1):
            ps_layout.addWidget(_make_flow_step(index, step_title, copy))

        ps_haptics_label = QLabel("For haptics and adaptive triggers in Proton games:")
        ps_haptics_label.setObjectName("card-copy")
        ps_layout.addWidget(ps_haptics_label)
        for index, (step_title, copy) in enumerate((
            ("Enable PlayStation controller support", "Steam → Settings → Controller."),
            ("Enable DualSense features", "In each game's own controller settings."),
            ("Avoid third-party controller emulation tools", "They hide the native DualSense from Proton and prevent haptic/trigger passthrough."),
        ), 1):
            ps_layout.addWidget(_make_flow_step(index, step_title, copy))

        self._ds_status_lbl = QLabel()
        self._ds_status_lbl.setObjectName("card-copy")
        self._ds_status_lbl.hide()
        ps_layout.addWidget(self._ds_status_lbl)

        ps_btns = QHBoxLayout()
        ps_btns.setSpacing(8)
        ps_bt_btn = QPushButton("Open Bluetooth Settings")
        ps_bt_btn.clicked.connect(lambda: systemsettings("kcm_bluetooth"))
        ps_btns.addWidget(ps_bt_btn)
        steam_ctrl_btn = QPushButton("Open Steam Controller Settings")
        steam_ctrl_btn.setToolTip("Opens Steam to the Controller settings page where you enable DualSense support.")
        steam_ctrl_btn.clicked.connect(
            lambda: flatpak_run(
                "com.valvesoftware.Steam",
                "steam://open/controllersettings",
            )
        )
        ps_btns.addWidget(steam_ctrl_btn)
        ps_btns.addStretch()
        ps_layout.addLayout(ps_btns)
        self._add(ps_card)

        # ── Nintendo / 8BitDo / Other ──────────────────────────────────────────
        other_card, other_layout = _make_card()
        other_title = QLabel("Nintendo Switch Pro, 8BitDo & Other Controllers")
        other_title.setObjectName("card-title")
        other_layout.addWidget(other_title)
        for index, (step_title, copy) in enumerate((
            ("Nintendo Switch Pro (Bluetooth)", "Hold the Sync button on the top edge until the lights cycle."),
            ("8BitDo (Bluetooth)", "Hold Start + B (Android mode) or Start + X (macOS mode, best for Linux), then hold Pair for 3 seconds."),
            ("Most USB controllers", "HORI, PowerA, PDP, Razer, and similar — plug in and they appear immediately as standard HID gamepads."),
        ), 1):
            other_layout.addWidget(_make_flow_step(index, step_title, copy))

        other_bt_btn = QPushButton("Open Bluetooth Settings")
        other_bt_btn.clicked.connect(lambda: systemsettings("kcm_bluetooth"))
        other_layout.addWidget(other_bt_btn)
        self._add(other_card)

        # ── Test your controller ───────────────────────────────────────────────
        test_card, test_layout = _make_card()
        test_title = QLabel("Test Your Controller")
        test_title.setObjectName("card-title")
        test_layout.addWidget(test_title)
        test_desc = QLabel(
            "jstest-gtk shows every button press and axis movement in real time. "
            "Use it to confirm your controller is detected and all inputs register correctly."
        )
        test_desc.setObjectName("card-copy")
        test_desc.setWordWrap(True)
        test_layout.addWidget(test_desc)
        self._test_btn = QPushButton("Open Controller Tester")
        self._test_btn.setObjectName("primary")
        self._test_btn.clicked.connect(lambda: popen(["jstest-gtk"]))
        test_layout.addWidget(self._test_btn)
        self._add(test_card)

        # ── Secure Boot warning (populated after probe) ────────────────────────
        self._sb_warn_lbl = QLabel(
            "⚠  Secure Boot is enabled. The xone (Xbox dongle) and xpadneo (Xbox "
            "Bluetooth) kernel modules need their signing keys enrolled before they "
            "will load. Run  sudo mokutil --import /etc/xone/cert.der  and follow "
            "the prompts, then reboot."
        )
        self._sb_warn_lbl.setObjectName("text-warn")
        self._sb_warn_lbl.setWordWrap(True)
        self._sb_warn_lbl.hide()
        self._add(self._sb_warn_lbl)

        self._stretch()

    # ── Probe ──────────────────────────────────────────────────────────────────

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._probed:
            self._probed = True
            self._start_probe()
        else:
            # Re-probe debounced when returning to page (hotplug, BT re-pair)
            self._hotplug_timer.start()

    def _start_probe(self) -> None:
        if self._probe_worker and self._probe_worker.isRunning():
            return
        self._status_lbl.setText("Scanning…")
        self._refresh_btn.setEnabled(False)
        worker = ControllerProbeWorker()
        self._probe_worker = worker
        worker.result.connect(self._on_probe_result)
        release_worker_when_finished(self, "_probe_worker", worker)
        worker.start()

    def _on_probe_result(self, info: dict) -> None:
        self._refresh_btn.setEnabled(True)
        view = controller_status_view(info)

        self._status_lbl.setText(view.status_text)

        self._xone_status_lbl.setText(view.xone_status_text)
        self._xone_status_lbl.setObjectName(view.xone_status_object_name)
        restyle(self._xone_status_lbl)
        self._xone_btn.setVisible(view.xone_button_visible)

        self._ds_status_lbl.setText(view.dualsense_status_text)
        self._ds_status_lbl.setVisible(view.dualsense_status_visible)

        self._sb_warn_lbl.setVisible(view.secure_boot_warning_visible)

    # ── Actions ────────────────────────────────────────────────────────────────

    def _test_rumble(self) -> None:
        import glob, shutil
        dev = next(iter(glob.glob("/dev/input/js*") or glob.glob("/dev/input/by-id/*joystick*")), None)
        if not dev and shutil.which("fftest"):
            dev = "/dev/input/js0"
        if not dev:
            QMessageBox.information(self, "No controller", "No joystick device found at /dev/input/js*. Connect a controller first.")
            return
        cmd = ["fftest", dev] if shutil.which("fftest") else ["evtest", dev]
        # Non-blocking: open terminal with test
        popen(cmd)

    def _flash_xone(self) -> None:
        cmd = shutil.which("xone-dongle-install") or shutil.which("xone-firmware-install")
        if not cmd:
            QMessageBox.warning(self, "Not found", "xone-dongle-install not found on this system.")
            return
        self._xone_btn.setEnabled(False)
        self._xone_status_lbl.setText("Flashing firmware…")
        helper = "xone-dongle-install" if cmd.endswith("xone-dongle-install") else "xone-firmware-install"
        worker = Worker(helper_action(
            helper,
            frontend=AuthFrontend.PKEXEC,
        ).command())
        worker.done.connect(self._on_xone_done)
        worker.start()
        self._xone_worker = worker

    def _on_xone_done(self, code: int) -> None:
        self._xone_btn.setEnabled(True)
        if code == 0:
            self._xone_status_lbl.setText("✓  Firmware flashed. Unplug and re-plug the adapter, then press Refresh.")
            self._xone_status_lbl.setObjectName("text-blue")
            restyle(self._xone_status_lbl)
            self._xone_btn.hide()
        else:
            self._xone_status_lbl.setText(f"Firmware flash failed (exit {code}). Check that xone is installed.")
            self._xone_status_lbl.setObjectName("text-err")
            restyle(self._xone_status_lbl)
