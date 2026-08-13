# Arch #18: VPN SAML survives sleep — VpnConnectWorker uses StreamingProcessWorker killpg→terminate→kill + BLOCKS_CLOSE
# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.vpn import (
    VPN_OS_OPTIONS as _VPN_OS_OPTIONS,
    VPN_PROTOCOLS as _VPN_PROTOCOLS,
    build_gateway_probe_command,
    build_initial_command,
    build_saml_reconnect_command,
    gp_interface_from_log_line,
    _load_vpn_config,
    _parse_gp_saml_cookie as _parse_gp_saml_cookie,
    _redact_vpn_log_line,
    _save_vpn_config,
    _vpn_line_is_connected,
    vpn_status_view,
)
from .services.workers.vpn import VpnConnectWorker as _VpnConnectWorker
from .qt import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, _WEBENGINE_AVAILABLE, single_shot,
)
from .widgets import (
    Page, _make_card, _set_log_panel,
)

if _WEBENGINE_AVAILABLE:
    from .page_vpn_saml_dialog import SamlBrowserDialog


class VpnPage(Page):
    """Connect to a VPN gateway using openconnect.

    The GlobalProtect SAML browser dialog (SamlBrowserDialog and its QWebEngine
    plumbing) lives in page_vpn_saml_dialog.py — it's a fully self-contained
    QDialog with no dependency on this page, only used from _on_saml_required.
    """

    def __init__(self):
        super().__init__()
        self._worker: _VpnConnectWorker | None = None
        self._saml_pending = False
        self._gp_interface = "portal"
        self._pending_gateway_saml = False
        self._gateway_saml_attempted = False
        self._saml_gateway = ""
        self._saml_protocol = "gp"
        self._saml_os_emul = "win"
        self._saml_username = ""

        self._page_header(
            "Network & Internet",
            "VPN",
            "Connect to a VPN gateway using openconnect. Settings are saved for next time.",
        )

        # ── Connection settings card ──────────────────────────────────────────
        cfg_card, cfg_layout = _make_card()
        cfg_title = QLabel("Connection Settings")
        cfg_title.setObjectName("card-title")
        cfg_layout.addWidget(cfg_title)

        form_row = QHBoxLayout()
        form_row.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(8)
        right = QVBoxLayout()
        right.setSpacing(8)

        def _lbl(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("card-copy")
            return lbl

        left.addWidget(_lbl("Gateway"))
        self._gw = QLineEdit()
        self._gw.setPlaceholderText("e.g. vpn.example.com")
        left.addWidget(self._gw)

        left.addWidget(_lbl("Protocol"))
        self._proto = QComboBox()
        self._proto.addItems(_VPN_PROTOCOLS)
        left.addWidget(self._proto)

        left.addWidget(_lbl("OS Emulation"))
        self._os_emul = QComboBox()
        self._os_emul.addItems(_VPN_OS_OPTIONS)
        left.addWidget(self._os_emul)

        right.addWidget(_lbl("Username"))
        self._vpn_user = QLineEdit()
        self._vpn_user.setPlaceholderText("optional")
        right.addWidget(self._vpn_user)

        right.addWidget(_lbl("Password"))
        self._vpn_pass = QLineEdit()
        self._vpn_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._vpn_pass.setPlaceholderText("optional — leave blank for interactive / SSO auth")
        right.addWidget(self._vpn_pass)

        right.addStretch()

        form_row.addLayout(left, 1)
        form_row.addLayout(right, 1)
        cfg_layout.addLayout(form_row)
        self._add(cfg_card)

        # ── Status + controls card ────────────────────────────────────────────
        ctrl_card, ctrl_layout = _make_card()

        self._vpn_status = QLabel("● Disconnected")
        self._vpn_status.setObjectName("status-dim")
        ctrl_layout.addWidget(self._vpn_status)

        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setMinimumHeight(34)
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setMinimumHeight(34)
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)
        btn_row.addStretch()
        ctrl_layout.addLayout(btn_row)

        self._vpn_log_toggle = QPushButton("Show details")
        self._vpn_log_toggle.setCheckable(True)
        self._vpn_log_toggle.setChecked(False)
        self._vpn_log_toggle.setObjectName("btn-secondary")
        ctrl_layout.addWidget(self._vpn_log_toggle)

        self._vpn_log = QTextEdit()
        self._vpn_log.document().setMaximumBlockCount(5000)
        self._vpn_log.setReadOnly(True)
        self._vpn_log.setVisible(False)
        self._vpn_log.setMinimumHeight(160)
        ctrl_layout.addWidget(self._vpn_log)

        self._vpn_log_toggle.toggled.connect(
            lambda checked: _set_log_panel(self._vpn_log_toggle, self._vpn_log, checked)
        )

        self._add(ctrl_card)
        self._stretch()

        self._load_vpn_saved()

    def _load_vpn_saved(self) -> None:
        v = _load_vpn_config()
        self._gw.setText(v.get("gateway", ""))
        idx = self._proto.findText(v.get("protocol", "gp"))
        if idx >= 0:
            self._proto.setCurrentIndex(idx)
        idx = self._os_emul.findText(v.get("os", "win"))
        if idx >= 0:
            self._os_emul.setCurrentIndex(idx)
        self._vpn_user.setText(v.get("username", ""))

    def _vpn_config_widgets(self):
        return (self._gw, self._proto, self._os_emul, self._vpn_user, self._vpn_pass)

    def _on_connect(self) -> None:
        gateway = self._gw.text().strip()
        if not gateway:
            _set_log_panel(self._vpn_log_toggle, self._vpn_log, True)
            self._vpn_log.append("[Error: Gateway is required]")
            return

        protocol = self._proto.currentText()
        os_emul = self._os_emul.currentText()
        username = self._vpn_user.text().strip()
        password = self._vpn_pass.text()

        _save_vpn_config(gateway, protocol, os_emul, username)

        self._saml_gateway = gateway
        self._saml_protocol = protocol
        self._saml_os_emul = os_emul
        self._saml_username = username
        self._saml_pending = False
        self._gp_interface = "portal"
        self._pending_gateway_saml = False
        self._gateway_saml_attempted = False

        self._vpn_log.clear()
        self._set_vpn_status("connecting")
        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
        for w in self._vpn_config_widgets():
            w.setEnabled(False)

        cmd, stdin_text = build_initial_command(
            gateway, protocol, os_emul, username, password
        )
        self._start_vpn_worker(cmd, stdin_text)

    def _on_disconnect(self) -> None:
        if self._worker:
            self._worker.stop()

    def _on_vpn_line(self, line: str) -> None:
        _set_log_panel(self._vpn_log_toggle, self._vpn_log, True)
        self._vpn_log.append(_redact_vpn_log_line(line))
        sb = self._vpn_log.verticalScrollBar()
        sb.setValue(sb.maximum())
        if _vpn_line_is_connected(line):
            self._set_vpn_status("connected")
            return
        interface = gp_interface_from_log_line(line)
        if interface:
            self._gp_interface = interface
            return
        if (
            "fgets (stdin)" in line
            and self._gp_interface == "gateway"
            and not self._saml_pending
            and not self._gateway_saml_attempted
        ):
            # Portal accepted the SAML cookie, but the gateway then demanded
            # its own prelogin-cookie (the portal cookie is interface-bound and
            # the portal returned no portal-userauthcookie to carry over).
            # openconnect prompted for it on an exhausted stdin and died — redo
            # SAML directly against the gateway once this process exits.
            self._pending_gateway_saml = True
            return
        if "Unexpected 512 result from server" in line:
            self._vpn_log.append(
                "[Hint: the GlobalProtect server rejected the SAML token — "
                "usually a portal/gateway mismatch or a username that doesn't "
                "match the SAML account]"
            )

    def _start_vpn_worker(self, cmd: list[str], stdin_text: str = "") -> None:
        worker = _VpnConnectWorker(cmd, stdin_text)
        self._worker = worker
        worker.line.connect(self._on_vpn_line)
        worker.done.connect(lambda code, w=worker: self._on_vpn_done(w, code))
        worker.saml_required.connect(self._on_saml_required)
        worker.start()

    def _on_vpn_done(self, worker: _VpnConnectWorker, code: int) -> None:
        if worker is not self._worker:
            worker.deleteLater()
            return
        self._worker = None
        worker.deleteLater()
        if self._saml_pending:
            return
        if self._pending_gateway_saml:
            self._pending_gateway_saml = False
            self._gateway_saml_attempted = True
            self._vpn_log.append(
                "[GP] Gateway requires its own SAML sign-in — restarting "
                "authentication against the gateway interface…"
            )
            single_shot(self, 500, self._start_gateway_probe)
            return
        self._set_vpn_status("disconnected")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        for w in self._vpn_config_widgets():
            w.setEnabled(True)
        self._vpn_log.append(f"\n[openconnect exited: code {code}]")

    def _start_gateway_probe(self) -> None:
        """Re-run the openconnect SAML probe against the GP gateway interface.

        Used when the portal leg succeeded but the gateway demanded its own
        prelogin-cookie, which only a gateway-issued SAML login can provide.
        The probe prints the gateway's SAML URL, the embedded browser replays
        the (now session-cached) IdP login, and the reconnect then uses
        gateway:<field>.
        """
        self._gp_interface = "gateway"
        self._set_vpn_status("connecting")
        cmd = build_gateway_probe_command(
            self._saml_gateway,
            self._saml_protocol,
            self._saml_os_emul,
            self._saml_username,
        )
        self._start_vpn_worker(cmd)

    def _on_saml_required(self, saml_url: str) -> None:
        if not _WEBENGINE_AVAILABLE:
            self._vpn_log.append(
                "\n[SAML auth required but python3-pyqt6-webengine is not installed]"
            )
            return
        self._saml_pending = True
        dlg = SamlBrowserDialog(saml_url, self._saml_gateway, self)
        dlg.cookie_ready.connect(self._on_saml_cookie)
        dlg.rejected.connect(self._on_saml_cancelled)
        dlg.exec()
        dlg.deleteLater()

    def _on_saml_cookie(self, cookie: str) -> None:
        self._saml_pending = False
        self._vpn_log.append("[SAML authentication complete — reconnecting…]")
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            # Avoid blocking UI: defer reconnect until the first worker finishes
            try:
                self._worker.finished.connect(lambda _c=cookie: self._on_saml_cookie(_c))
            except RuntimeError:
                pass
            return
        cmd, worker_stdin, username = build_saml_reconnect_command(
            self._saml_gateway,
            self._saml_protocol,
            self._saml_os_emul,
            self._gp_interface,
            cookie,
            self._saml_username,
        )
        print(
            f"[SAML dbg] reconnecting via {self._gp_interface} "
            f"with username={'yes' if username else 'no'}"
        )

        self._start_vpn_worker(cmd, worker_stdin)

    def _on_saml_cancelled(self) -> None:
        self._saml_pending = False
        self._set_vpn_status("disconnected")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        for w in self._vpn_config_widgets():
            w.setEnabled(True)
        self._vpn_log.append("\n[SAML authentication cancelled]")

    def _set_vpn_status(self, state: str) -> None:
        view = vpn_status_view(state)
        self._vpn_status.setText(view.text)
        self._vpn_status.setObjectName(view.style)
        restyle(self._vpn_status)
