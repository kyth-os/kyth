# __KYTH_GENERATED_IMPORTS__
from .core_base import _command_stdout, _restyle
from .services.gaming import DataWorker
from .services.hardware import (
    HardwareProbe,
    HardwareProbeWorker,
    bt_audio_device_summary,
    force_ldac_reconnect,
    switch_to_bt_audio_output,
)
from .services.launch import kcmshell, popen
from .services.software import _finish_worker
from .qt import (  # noqa: E501
    QDesktopServices, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTimer, QUrl, QVBoxLayout, QWidget, Signal,
)
from .widgets import (  # noqa: E501
    HardwareCard, Page, _make_card,
)

# ── Page: Hardware ────────────────────────────────────────────────────────────
class HardwarePage(Page):
    action_requested = Signal(str)

    def __init__(self, wizard_mode: bool = False, navigate=None):
        super().__init__()
        self._worker = None
        self._wizard_mode = wizard_mode
        self._navigate = navigate or self.action_requested.emit
        self._cards: list[HardwareCard] = []
        self._last_probes: list[HardwareProbe] = []
        self._initial_refresh_started = False
        self._display_worker: DataWorker | None = None
        self._display_status_lbl: QLabel | None = None
        self._bt_worker: DataWorker | None = None

        self._page_header(
            "System",
            "Hardware",
            "Graphics, firmware, connectivity, audio, storage, and platform checks.",
        )

        # Control block: refresh button, status label, and progress bar bundled together
        ctrl_block = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_block)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("primary")
        self._refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch()
        self._status_lbl = QLabel("Running hardware probes…")
        self._status_lbl.setObjectName("subheading")
        btn_row.addWidget(self._status_lbl)
        ctrl_layout.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        ctrl_layout.addWidget(self._progress)
        self._add(ctrl_block)

        # Summary card — hidden until probes finish
        self._summary_card, summary_layout = _make_card()
        self._summary_title = QLabel()
        self._summary_title.setObjectName("card-title")
        summary_layout.addWidget(self._summary_title)
        self._summary_body = QLabel()
        self._summary_body.setObjectName("card-copy")
        self._summary_body.setWordWrap(True)
        summary_layout.addWidget(self._summary_body)
        self._summary_card.hide()
        self._add(self._summary_card)

        # Two-column probe card grid
        self._card_container = QWidget()
        self._card_col = QGridLayout(self._card_container)
        self._card_col.setContentsMargins(0, 0, 0, 0)
        self._card_col.setSpacing(12)
        self._card_col.setColumnStretch(0, 1)
        self._card_col.setColumnStretch(1, 1)
        self._add(self._card_container)

        # Configuration section
        config_lbl = QLabel("Configuration")
        config_lbl.setObjectName("section-heading")
        self._add(config_lbl)

        self._add(self._make_bt_audio_card())
        self._add(self._make_display_card())

        self._stretch()

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        QTimer.singleShot(0, self.refresh)
        QTimer.singleShot(0, self._refresh_display_status)

    def _display_status_text(self, raw: str) -> str:
        hdr_outputs: list[tuple[str, str]] = []   # (name, hdr_state)
        vrr_outputs: list[tuple[str, str]] = []   # (name, vrr_state)
        if raw:
            cur_name = ""
            for line in raw.splitlines():
                stripped = line.strip()
                if stripped.startswith("Output:") or (stripped and not line.startswith(" ")):
                    parts = stripped.split()
                    if len(parts) >= 2:
                        cur_name = parts[-1].rstrip(":")
                elif stripped.lower().startswith("hdr:") and cur_name:
                    hdr_outputs.append((cur_name, stripped.split(":", 1)[1].strip()))
                elif stripped.lower().startswith("vrr:") and cur_name:
                    vrr_outputs.append((cur_name, stripped.split(":", 1)[1].strip()))

        if hdr_outputs or vrr_outputs:
            lines = []
            seen = set()
            for name, hdr in hdr_outputs:
                seen.add(name)
                vrr = next((v for n, v in vrr_outputs if n == name), "unknown")
                hdr_str = "HDR on" if hdr == "enabled" else "HDR off"
                vrr_str = f"VRR {vrr}" if vrr not in ("unknown", "") else "VRR unknown"
                lines.append(f"{name}: {hdr_str}  ·  {vrr_str}")
            for name, vrr in vrr_outputs:
                if name not in seen:
                    lines.append(f"{name}: VRR {vrr}")
            return "\n".join(lines)
        return "Display info unavailable — kscreen not running or no outputs detected."

    def _refresh_display_status(self):
        if self._display_worker is not None or self._display_status_lbl is None:
            return
        self._display_worker = DataWorker(
            "display",
            lambda: _command_stdout(["kscreen-doctor", "-o"], timeout=6),
        )
        self._display_worker.result.connect(self._on_display_status_ready)
        self._display_worker.failed.connect(self._on_display_status_failed)
        self._display_worker.finished.connect(lambda: setattr(self, "_display_worker", None))
        self._display_worker.start()

    def _on_display_status_ready(self, _key: str, raw: object):
        if self._display_status_lbl is not None:
            self._display_status_lbl.setText(self._display_status_text(str(raw or "")))

    def _on_display_status_failed(self, _key: str, _message: str):
        if self._display_status_lbl is not None:
            self._display_status_lbl.setText("Display info unavailable — kscreen not running or no outputs detected.")

    def _make_display_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Display — HDR & Variable Refresh Rate")
        title.setObjectName("card-title")
        layout.addWidget(title)

        status_lbl = QLabel("Checking display capabilities…")
        self._display_status_lbl = status_lbl
        status_lbl.setObjectName("card-copy")
        status_lbl.setWordWrap(True)
        layout.addWidget(status_lbl)

        body = QLabel(
            "HDR and Variable Refresh Rate (FreeSync/G-Sync) are configured per monitor in "
            "KDE Display Settings. Enable HDR for your primary display, then set per-game "
            "HDR via Steam → game properties → General → HDR."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        display_btn = QPushButton("Display Settings")
        display_btn.setObjectName("primary")
        display_btn.setToolTip("Open KDE Display Settings — HDR, VRR, refresh rate, and multi-monitor layout.")
        display_btn.clicked.connect(
            lambda _=False: kcmshell("kcm_kscreen") or QDesktopServices.openUrl(QUrl("settings://display"))
        )
        btns.addWidget(display_btn)
        color_btn = QPushButton("Color & Night Light")
        color_btn.setToolTip("Color profiles and Night Light blue-light filter settings.")
        color_btn.clicked.connect(lambda _=False: kcmshell("kcm_nightcolor"))
        btns.addWidget(color_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _make_bt_audio_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Bluetooth Audio")
        title.setObjectName("card-title")
        layout.addWidget(title)

        desc = QLabel(
            "KythOS prefers LDAC (990 kbps HQ) over SBC when your headset supports it. "
            "If your Bluetooth headset sounds worse than expected, use the controls below "
            "to check the active codec, switch audio to your headset, or reconnect to renegotiate the codec."
        )
        desc.setObjectName("card-copy")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._bt_status_lbl = QLabel("Click Refresh Devices to scan.")
        self._bt_status_lbl.setObjectName("card-copy")
        self._bt_status_lbl.setWordWrap(True)
        layout.addWidget(self._bt_status_lbl)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        refresh_btn = QPushButton("Refresh Devices")
        refresh_btn.clicked.connect(self._refresh_bt_audio)
        btns.addWidget(refresh_btn)
        switch_btn = QPushButton("Switch to BT Output")
        switch_btn.setToolTip("Set the connected Bluetooth audio device as the default audio output.")
        switch_btn.clicked.connect(self._switch_to_bt_audio)
        btns.addWidget(switch_btn)
        ldac_btn = QPushButton("Force LDAC Reconnect")
        ldac_btn.setToolTip(
            "Disconnect and reconnect the active Bluetooth device to renegotiate codec. "
            "Use this if your headset falls back to SBC instead of LDAC."
        )
        ldac_btn.clicked.connect(self._force_ldac_reconnect)
        btns.addWidget(ldac_btn)
        bt_settings_btn = QPushButton("Bluetooth Settings")
        bt_settings_btn.clicked.connect(
            lambda: kcmshell("kcm_bluetooth") or QDesktopServices.openUrl(QUrl("settings://bluetooth"))
        )
        btns.addWidget(bt_settings_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _start_bt_worker(self, key: str, fn, on_result, on_failed=None):
        self._bt_worker = DataWorker(key, fn)
        self._bt_worker.result.connect(on_result)
        if on_failed:
            self._bt_worker.failed.connect(on_failed)
        else:
            self._bt_worker.failed.connect(lambda _k, err: self._bt_status_lbl.setText(f"Bluetooth operation failed: {err}"))
        self._bt_worker.finished.connect(lambda: setattr(self, "_bt_worker", None))
        self._bt_worker.start()

    def _refresh_bt_audio(self):
        self._bt_status_lbl.setText("Scanning Bluetooth devices…")

        self._start_bt_worker(
            "bt-refresh",
            bt_audio_device_summary,
            lambda _k, text: self._bt_status_lbl.setText(str(text)),
        )

    def _switch_to_bt_audio(self):
        self._bt_status_lbl.setText("Switching audio output to Bluetooth…")
        self._start_bt_worker(
            "bt-switch",
            switch_to_bt_audio_output,
            lambda _k, text: self._bt_status_lbl.setText(str(text)),
        )

    def _force_ldac_reconnect(self):
        self._bt_status_lbl.setText("Looking for connected Bluetooth device…")

        def _on_done(_key: str, msg: object) -> None:
            text = str(msg) if msg else "No connected Bluetooth device found. Connect your headset first."
            self._bt_status_lbl.setText(text)

        self._start_bt_worker("ldac-reconnect", force_ldac_reconnect, _on_done)

    def refresh(self):
        self._refresh_btn.setEnabled(False)
        self._status_lbl.setText("Running hardware probes…")
        self._status_lbl.setObjectName("subheading")
        _restyle(self._status_lbl)
        self._progress.show()

        self._worker = HardwareProbeWorker()
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _replace_cards(self, probes: list[HardwareProbe]):
        while self._card_col.count():
            item = self._card_col.takeAt(0)
            if w := item.widget():
                w.deleteLater()
        self._cards = []
        for i, probe in enumerate(probes):
            card = HardwareCard(probe)
            self._cards.append(card)
            self._card_col.addWidget(card, i // 2, i % 2)

    def _on_done(self, probes: list[HardwareProbe]):
        self._progress.hide()
        self._refresh_btn.setEnabled(True)
        _finish_worker(self)
        self._replace_cards(probes)
        self._last_probes = probes

        levels = {p.status for p in probes}
        errs = [p for p in probes if p.status == "err"]
        warns = [p for p in probes if p.status == "warn"]
        oks = [p for p in probes if p.status == "ok"]
        if "err" in levels:
            self._status_lbl.setText("One or more issues need attention.")
            self._status_lbl.setObjectName("status-err")
            self._summary_card.setObjectName("card-accent-err")
            self._summary_title.setText(f"{len(errs)} hardware issue{'s' if len(errs) != 1 else ''} found")
            self._summary_body.setText("Start with the issue cards below; each one includes the safest next action when KythOS knows one.")
        elif "warn" in levels:
            self._status_lbl.setText("Mostly healthy — a few items worth checking.")
            self._status_lbl.setObjectName("status-warn")
            self._summary_card.setObjectName("card-accent-warn")
            self._summary_title.setText(f"{len(warns)} hardware warning{'s' if len(warns) != 1 else ''}")
            self._summary_body.setText("The system is usable, but some device, display, driver, or platform checks have recommended follow-up.")
        else:
            self._status_lbl.setText("All checks passed.")
            self._status_lbl.setObjectName("status-ok")
            self._summary_card.setObjectName("card-accent-ok")
            self._summary_title.setText(f"All {len(oks)} hardware checks passed")
            self._summary_body.setText("Graphics, firmware, audio, networking, storage, and platform checks look ready.")
        _restyle(self._status_lbl)
        _restyle(self._summary_card)
        self._summary_card.show()

        if self._wizard_mode:
            self._wire_wizard_action_buttons(probes)

    def _wire_wizard_action_buttons(self, probes: list[HardwareProbe]):
        for card, probe in zip(self._cards, probes):
            if probe.action_page_key:
                key = probe.action_page_key
                card.set_action_fn(
                    probe.action or f"Open {key}",
                    lambda k=key: self.action_requested.emit(k),
                )
                card.expand()
            elif probe.action_cmd:
                cmd = probe.action_cmd
                card.set_action_fn(
                    probe.action or "Fix",
                    lambda c=cmd: self._run_inline_cmd(c),
                )
                card.expand()

    def _run_inline_cmd(self, cmd: list[str]):
        popen(cmd)
        QTimer.singleShot(1500, self.refresh)

    def _on_failed(self, message: str):
        self._progress.hide()
        self._refresh_btn.setEnabled(True)
        _finish_worker(self)
        self._status_lbl.setText(f"Probe failed: {message}")
        self._status_lbl.setObjectName("status-err")
        _restyle(self._status_lbl)
