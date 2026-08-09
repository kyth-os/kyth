import pathlib
# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.process import command_stdout
from .services.gaming import DataWorker
from .services.hardware import (
    HardwareProbe,
    HardwareProbeWorker,
    _parse_kscreen_output,
    bt_audio_device_summary,
    force_ldac_reconnect,
    hardware_summary_view,
    hdr_vrr_status_text,
    switch_to_bt_audio_output,
)
from .services.launch import kcmshell, popen
from .services.runtime import finish_worker
from .qt import (
    QDesktopServices, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QUrl, QVBoxLayout, QWidget, Signal, single_shot,
)
from .widgets import (
    HardwareCard, Page, _make_card, _make_section_header,
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

        # Two-column probe card grid, grouped into "Needs Attention" (warn/err)
        # and "Healthy & Info" sections instead of one flat interleaved grid —
        # with ~20 checks on a fresh probe, a flat grid means the 1-2 things
        # that actually need a look are scattered among a wall of "OK" cards.
        self._attention_heading = QLabel("Needs Attention")
        self._attention_heading.setObjectName("section-heading")
        self._attention_heading.hide()
        self._add(self._attention_heading)

        self._attention_container = QWidget()
        self._attention_col = QGridLayout(self._attention_container)
        self._attention_col.setContentsMargins(0, 0, 0, 0)
        self._attention_col.setSpacing(12)
        self._attention_col.setColumnStretch(0, 1)
        self._attention_col.setColumnStretch(1, 1)
        self._attention_container.hide()
        self._add(self._attention_container)

        self._healthy_heading = QLabel("Healthy & Info")
        self._healthy_heading.setObjectName("section-heading")
        self._healthy_heading.hide()
        self._add(self._healthy_heading)

        self._card_container = QWidget()
        self._card_col = QGridLayout(self._card_container)
        self._card_col.setContentsMargins(0, 0, 0, 0)
        self._card_col.setSpacing(12)
        self._card_col.setColumnStretch(0, 1)
        self._card_col.setColumnStretch(1, 1)
        self._add(self._card_container)

        # Configuration section — Windows Settings-style header
        hdr, _ = _make_section_header("Configuration", "Bluetooth audio and display")
        self._add(hdr)

        self._add(self._make_peripherals_hub_card())
        self._add(self._make_cooling_card())
        self._add(self._make_bt_audio_card())
        self._add(self._make_display_card())

        self._stretch()

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        single_shot(self, 0, self.refresh)
        single_shot(self, 0, self._refresh_display_status)

    def _refresh_display_status(self):
        if self._display_worker is not None or self._display_status_lbl is None:
            return
        self._display_worker = DataWorker(
            "display",
            lambda: command_stdout(["kscreen-doctor", "-o"], timeout=6),
        )
        self._display_worker.result.connect(self._on_display_status_ready)
        self._display_worker.failed.connect(self._on_display_status_failed)
        self._display_worker.finished.connect(lambda: setattr(self, "_display_worker", None))
        self._display_worker.finished.connect(self._display_worker.deleteLater)
        self._display_worker.start()

    def _on_display_status_ready(self, _key: str, raw: object):
        text = str(raw or "")
        if self._display_status_lbl is not None:
            # Show current mode + VRR/HDR via hdr_vrr_status_text, with formatted mode
            self._display_status_lbl.setText(hdr_vrr_status_text(text))
        if getattr(self, "_display_vrr_warn_lbl", None) is not None:
            try:
                probe = _parse_kscreen_output(text)
                warn = getattr(probe, "action", "") or ""
                # Surface VRR state per-output: never vs always on high-refresh
                if probe.status == "warn" and probe.action:
                    self._display_vrr_warn_lbl.setText(f"⚠️ {probe.action}")
                    self._display_vrr_warn_lbl.setObjectName("status-warn")
                    self._display_vrr_warn_lbl.show()
                elif "VRR" in probe.details and "Never" in probe.details:
                    self._display_vrr_warn_lbl.setText("⚠️ VRR is set to Never on a high-refresh display — enable VRR in Display Settings for smoother gameplay.")
                    self._display_vrr_warn_lbl.setObjectName("status-warn")
                    self._display_vrr_warn_lbl.show()
                elif "VRR" in probe.details and "always" in probe.details.lower():
                    self._display_vrr_warn_lbl.setText("✓ VRR is enabled (Always) — adaptive sync active for games.")
                    self._display_vrr_warn_lbl.setObjectName("status-ok")
                    self._display_vrr_warn_lbl.show()
                else:
                    self._display_vrr_warn_lbl.hide()
                restyle(self._display_vrr_warn_lbl)
            except Exception:
                if self._display_vrr_warn_lbl is not None:
                    self._display_vrr_warn_lbl.hide()

    def _on_display_status_failed(self, _key: str, _message: str):
        if self._display_status_lbl is not None:
            self._display_status_lbl.setText("Display info unavailable — kscreen not running or no outputs detected.")
        if getattr(self, "_display_vrr_warn_lbl", None) is not None:
            self._display_vrr_warn_lbl.hide()

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

        self._display_vrr_warn_lbl = QLabel("")
        self._display_vrr_warn_lbl.setObjectName("status-warn")
        self._display_vrr_warn_lbl.setWordWrap(True)
        self._display_vrr_warn_lbl.hide()
        layout.addWidget(self._display_vrr_warn_lbl)

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
        hdr_btn = QPushButton("HDR per-game")
        hdr_btn.setToolTip("Set per-game HDR via kyth-hdr-per-game")
        hdr_btn.clicked.connect(lambda _=False: __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["/usr/bin/kyth-hdr-per-game"]) if pathlib.Path("/usr/bin/kyth-hdr-per-game").exists() else None)
        btns.addWidget(hdr_btn)
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
        easy_btn = QPushButton("Mic Effects (EasyEffects)")
        easy_btn.setToolTip("Open EasyEffects for noise gate/EQ — for headset mic parity")
        easy_btn.clicked.connect(lambda: __import__("shutil").which("easyeffects") and __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["flatpak","run","com.github.wwmm.easyeffects"]) or __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["flatpak","run","com.github.wwmm.easyeffects"]))
        btns.addWidget(easy_btn)
        bt_settings_btn = QPushButton("Bluetooth Settings")
        bt_settings_btn.clicked.connect(
            lambda: kcmshell("kcm_bluetooth") or QDesktopServices.openUrl(QUrl("settings://bluetooth"))
        )
        btns.addWidget(bt_settings_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _start_bt_worker(self, key: str, fn, on_result, on_failed=None):
        # H8/M7: ensure worker is cleaned up and label is still alive when callback fires
        self._bt_worker = DataWorker(key, fn)
        self._bt_worker.result.connect(on_result)

        def _safe_failed(_k, err):
            try:
                if self._bt_status_lbl is not None:
                    # sip: wrapped C++ object may be deleted if page was reparented
                    self._bt_status_lbl.setText(f"Bluetooth operation failed: {err}")
            except RuntimeError:
                pass

        if on_failed:
            self._bt_worker.failed.connect(on_failed)
        else:
            self._bt_worker.failed.connect(_safe_failed)
        self._bt_worker.finished.connect(lambda: setattr(self, "_bt_worker", None))
        self._bt_worker.finished.connect(self._bt_worker.deleteLater)
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
        restyle(self._status_lbl)
        self._progress.show()

        self._worker = HardwareProbeWorker()
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _replace_cards(self, probes: list[HardwareProbe]):
        for grid in (self._attention_col, self._card_col):
            while grid.count():
                item = grid.takeAt(0)
                if w := item.widget():
                    w.deleteLater()

        # self._cards stays in the same order as `probes` — _wire_wizard_action_buttons
        # zips them positionally (strict=True), so card[i] must stay the card for
        # probe[i] regardless of which grid it's visually placed into below.
        self._cards = []
        attention_n = healthy_n = 0
        for probe in probes:
            card = HardwareCard(probe)
            self._cards.append(card)
            if probe.status in ("warn", "err"):
                self._attention_col.addWidget(card, attention_n // 2, attention_n % 2)
                attention_n += 1
            else:
                self._card_col.addWidget(card, healthy_n // 2, healthy_n % 2)
                healthy_n += 1

        self._attention_heading.setVisible(attention_n > 0)
        self._attention_container.setVisible(attention_n > 0)
        self._healthy_heading.setVisible(healthy_n > 0)

    def _on_done(self, probes: list[HardwareProbe]):
        self._progress.hide()
        self._refresh_btn.setEnabled(True)
        finish_worker(self)
        self._replace_cards(probes)
        self._last_probes = probes

        view = hardware_summary_view(probes)
        self._status_lbl.setText(view.status_text)
        self._status_lbl.setObjectName(view.status_style)
        self._summary_card.setObjectName(view.summary_card_style)
        self._summary_title.setText(view.summary_title)
        self._summary_body.setText(view.summary_body)
        restyle(self._status_lbl)
        restyle(self._summary_card)
        self._summary_card.show()

        if self._wizard_mode:
            self._wire_wizard_action_buttons(probes)

    def _wire_wizard_action_buttons(self, probes: list[HardwareProbe]):
        for card, probe in zip(self._cards, probes, strict=True):
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
        single_shot(self, 1500, self.refresh)

    def _make_peripherals_hub_card(self) -> QFrame:
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Peripherals — RGB, Fans, Controllers, Capture")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Your RGB, fan curves, controller mappings, HDR per-game settings, and audio routing — all in one place. "
            "KythOS detects what's present and shows the next step. For RGB: OpenRGB or kyth-apply-rgb. Fans: fan-curve.toml + hwmon. "
            "Controllers: ujust controller-check. HDR: Gaming → HDR. Audio: PipeWire per-app mixer."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        self._peri_status = QLabel("Click Scan Peripherals to detect RGB, fans, controllers, HDR, and audio.")
        self._peri_status.setObjectName("card-copy")
        self._peri_status.setWordWrap(True)
        layout.addWidget(self._peri_status)
        self._peri_rows = QVBoxLayout()
        self._peri_rows.setSpacing(6)
        layout.addLayout(self._peri_rows)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        scan_btn = QPushButton("Scan Peripherals")
        scan_btn.setObjectName("primary")
        scan_btn.clicked.connect(self._scan_peripherals)
        btns.addWidget(scan_btn)
        rgb_btn = QPushButton("RGB Settings")
        rgb_btn.clicked.connect(lambda _=False: popen(["openrgb"]) if __import__("shutil").which("openrgb") else self._navigate("Gaming"))
        btns.addWidget(rgb_btn)
        ctrl_btn = QPushButton("Controller Check")
        ctrl_btn.clicked.connect(lambda _=False: popen(["/usr/bin/kyth-controller-check"]) or self._navigate("Gaming"))
        btns.addWidget(ctrl_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _scan_peripherals(self):
        from .services.runtime import DataWorker, release_worker_when_finished
        self._peri_status.setText("Scanning peripherals…")
        restyle(self._peri_status)
        while self._peri_rows.count():
            it = self._peri_rows.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        def _scan():
            try:
                from kyth_welcome.services.peripherals_hub import scan_peripherals as _scan_p
                return _scan_p()
            except Exception as exc:
                return {"error": str(exc)}

        worker = DataWorker("peripherals-scan", _scan)
        worker.result.connect(self._on_peripherals_result)
        worker.failed.connect(lambda _k, msg: self._peri_status.setText(f"Scan failed: {msg}"))
        self._peri_worker = worker
        release_worker_when_finished(self, "_peri_worker", worker)
        worker.start()

    def _on_peripherals_result(self, _key: str, data: dict):
        if data.get("error"):
            self._peri_status.setText(f"Scan failed: {data['error']}")
            restyle(self._peri_status)
            return
        # Render 5 rows: rgb/fan/controllers/hdr/audio
        for key, label in (("rgb", "RGB Lighting"), ("fan", "Fan / Cooling"), ("controllers", "Controllers"), ("hdr", "HDR"), ("audio", "Audio Routing")):
            info = data.get(key) or {}
            detail = info.get("detail", "")
            avail = info.get("available", False)
            status = "ok" if avail else "dim"
            # Controllers blocked reasoning -> warn
            if key == "controllers" and not avail:
                status = "warn"
            row = QFrame()
            row.setObjectName({"ok": "hw-card-ok", "warn": "hw-card-warn", "dim": "hw-card-dim"}.get(status, "hw-card-dim"))
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 7, 12, 7)
            rl.setSpacing(10)
            name_lbl = QLabel(label)
            name_lbl.setObjectName("card-subtitle")
            name_lbl.setMinimumWidth(130)
            rl.addWidget(name_lbl)
            desc = QLabel(detail)
            desc.setObjectName("card-copy")
            desc.setWordWrap(True)
            rl.addWidget(desc, 1)
            self._peri_rows.addWidget(row)
        self._peri_status.setText("Scan complete — see details below. Use the buttons above for deeper settings.")
        self._peri_status.setObjectName("status-ok")
        restyle(self._peri_status)

    def _make_cooling_card(self):
        from .widgets import _make_card
        from .qt import QLabel, QPushButton, QHBoxLayout, QVBoxLayout
        card, layout = _make_card()
        title = QLabel("Cooling — fan curve, power cap, sleep drain")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Fan curve from /etc/kyth/fan-curve.toml (hwmon) + power cap via fan_curve.py, and deep sleep drain check via resume-check. "
            "Windows users judge a laptop in 3 days on fan noise and sleep drain — this surfaces both."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        self._cool_status = QLabel("Checking fan curve…")
        self._cool_status.setObjectName("card-copy")
        self._cool_status.setWordWrap(True)
        layout.addWidget(self._cool_status)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        show_btn = QPushButton("Show Fan Curve")
        show_btn.clicked.connect(lambda _=False: self._show_fan_curve())
        btns.addWidget(show_btn)
        sleep_btn = QPushButton("Test Sleep (resume-check)")
        sleep_btn.setToolTip("Run ujust resume-check in background")
        sleep_btn.clicked.connect(lambda _=False: __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["/usr/bin/kyth-resume-check"]) if pathlib.Path("/usr/bin/kyth-resume-check").exists() else __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["systemctl","status","sleep.target"]))
        btns.addWidget(sleep_btn)
        btns.addStretch()
        layout.addLayout(btns)
        # initial fan curve display
        try:
            from kyth_shared.fan_curve import load_fan_curve
            cfg = load_fan_curve()
            self._cool_status.setText(f"Fan points {cfg.get('points')} power_cap {cfg.get('power_cap_w')}W")
        except Exception:
            self._cool_status.setText("Fan curve unavailable")
        return card

    def _show_fan_curve(self):
        try:
            from kyth_shared.fan_curve import load_fan_curve
            cfg = load_fan_curve()
            self._cool_status.setText(f"Fan points {cfg.get('points')} power_cap {cfg.get('power_cap_w')}W — edit /etc/kyth/fan-curve.toml")
            from .core_base import restyle
            restyle(self._cool_status)
        except Exception as exc:
            self._cool_status.setText(f"Fan curve read failed: {exc}")

    def _on_failed(self, message: str):
        self._progress.hide()
        self._refresh_btn.setEnabled(True)
        finish_worker(self)
        self._status_lbl.setText(f"Probe failed: {message}")
        self._status_lbl.setObjectName("status-err")
        restyle(self._status_lbl)

# New #4-6: driver/fwupd auto + Familiar Desktop toggle + OneDrive native mount (see new features 4-6)
