import shutil

# __KYTH_GENERATED_IMPORTS__
from .core_base import _release_worker_when_finished
from .services.gaming import TrackedThread
from .services.hardware import _detect_controllers
from .services.runtime import Worker
from .services.privileged import AuthFrontend, helper_action
from .qt import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton, Signal,
)
from .services.launch import flatpak_run, popen, systemsettings
from .widgets import (
    Page, _make_card,
)

class ControllerProbeWorker(TrackedThread):
    result = Signal(dict)

    def run(self) -> None:
        self.result.emit(_detect_controllers())


class ControllerPage(Page):
    def __init__(self):
        super().__init__()
        self._probe_worker: ControllerProbeWorker | None = None
        self._probed = False

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

        xbox_bt_steps = QLabel(
            "Pair over Bluetooth (no dongle):\n"
            "  1.  Press and hold the Xbox button for 3 seconds until it flashes\n"
            "  2.  Hold the Sync button (top of controller) until it flashes rapidly\n"
            "  3.  Open System Tray → Bluetooth → Add Device"
        )
        xbox_bt_steps.setObjectName("card-copy")
        xbox_layout.addWidget(xbox_bt_steps)

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

        ps_bt_steps = QLabel(
            "Pair over Bluetooth:\n"
            "  DualSense (PS5):  hold PS + Create until the light bar blinks\n"
            "  DualShock 4 (PS4):  hold PS + Share until the light bar blinks\n"
            "  Then: System Tray → Bluetooth → Add Device\n\n"
            "For haptics and adaptive triggers in Proton games:\n"
            "  Steam → Settings → Controller → Enable PlayStation controller support\n"
            "  In each game's controller settings: enable DualSense features\n"
            "  Avoid third-party controller emulation tools — they hide the native DualSense\n"
            "  from Proton and prevent haptic/trigger passthrough"
        )
        ps_bt_steps.setObjectName("card-copy")
        ps_layout.addWidget(ps_bt_steps)

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
        other_steps = QLabel(
            "Nintendo Switch Pro (Bluetooth):\n"
            "  Hold the Sync button on the top edge until the lights cycle\n\n"
            "8BitDo (Bluetooth):\n"
            "  Hold Start + B (Android mode) or Start + X (macOS mode, best for Linux)\n"
            "  Then hold the Pair button for 3 seconds\n\n"
            "Most USB controllers (HORI, PowerA, PDP, Razer):\n"
            "  Plug in — they appear immediately as standard HID gamepads"
        )
        other_steps.setObjectName("card-copy")
        other_layout.addWidget(other_steps)

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
        self._sb_warn_lbl.setObjectName("card-copy")
        self._sb_warn_lbl.setWordWrap(True)
        self._sb_warn_lbl.setStyleSheet("color: #d4a843; padding: 6px 0;")
        self._sb_warn_lbl.hide()
        self._add(self._sb_warn_lbl)

        self._stretch()

    # ── Probe ──────────────────────────────────────────────────────────────────

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._probed:
            self._probed = True
            self._start_probe()

    def _start_probe(self) -> None:
        if self._probe_worker and self._probe_worker.isRunning():
            return
        self._status_lbl.setText("Scanning…")
        self._refresh_btn.setEnabled(False)
        worker = ControllerProbeWorker()
        self._probe_worker = worker
        worker.result.connect(self._on_probe_result)
        _release_worker_when_finished(self, "_probe_worker", worker)
        worker.start()

    def _on_probe_result(self, info: dict) -> None:
        self._refresh_btn.setEnabled(True)

        # ── Connected controllers status ───────────────────────────────────────
        lines: list[str] = []
        for name, _ in info["usb_controllers"]:
            lines.append(f"  ✓  {name}")
        for node in info["input_nodes"]:
            label = node.replace("usb-", "").replace("_", " ")
            lines.append(f"  ✓  {label}  (input node)")
        if not lines:
            self._status_lbl.setText("No controllers detected. Connect a controller and press Refresh.")
        else:
            mods = []
            if info["xpadneo_loaded"]:   mods.append("xpadneo")
            if info["xone_loaded"]:      mods.append("xone_hid")
            if info["hid_ps_loaded"]:    mods.append("hid_playstation")
            mod_line = f"\n  Active drivers: {', '.join(mods)}" if mods else ""
            self._status_lbl.setText("\n".join(lines) + mod_line)

        # ── xone dongle status ─────────────────────────────────────────────────
        if info["xone_dongle"] and not info["xone_loaded"]:
            self._xone_status_lbl.setText(
                "Xbox Wireless Adapter detected — firmware not yet flashed. "
                "Click the button below to complete setup (requires password)."
            )
            self._xone_status_lbl.setStyleSheet("color: #d4a843;")
            self._xone_btn.show()
        elif info["xone_dongle"] and info["xone_loaded"]:
            self._xone_status_lbl.setText(
                "✓  Xbox Wireless Adapter is ready. Press the sync button on the "
                "adapter and controller together to pair."
            )
            self._xone_status_lbl.setStyleSheet("color: #4fc1ff;")
            self._xone_btn.hide()
        else:
            self._xone_status_lbl.setText(
                "No Xbox Wireless Adapter detected. "
                "If you have one, plug it in and press Refresh."
            )
            self._xone_status_lbl.setStyleSheet("")
            self._xone_btn.hide()

        # ── DualSense status ───────────────────────────────────────────────────
        if info["dualsense_found"] and info["dualsensectl_out"]:
            self._ds_status_lbl.setText(
                "DualSense connected — " + info["dualsensectl_out"].strip().splitlines()[0]
            )
            self._ds_status_lbl.show()
        elif info["dualsense_found"]:
            self._ds_status_lbl.setText("✓  DualSense connected.")
            self._ds_status_lbl.show()
        else:
            self._ds_status_lbl.hide()

        # ── Secure Boot warning ────────────────────────────────────────────────
        if info["secure_boot"] and (info["xone_dongle"] or not info["xpadneo_loaded"]):
            self._sb_warn_lbl.show()
        else:
            self._sb_warn_lbl.hide()

    # ── Actions ────────────────────────────────────────────────────────────────

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
            self._xone_status_lbl.setStyleSheet("color: #4fc1ff;")
            self._xone_btn.hide()
        else:
            self._xone_status_lbl.setText(f"Firmware flash failed (exit {code}). Check that xone is installed.")
            self._xone_status_lbl.setStyleSheet("color: #f48771;")
