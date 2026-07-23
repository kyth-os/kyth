import json
import os
import re

# __KYTH_GENERATED_IMPORTS__
from .core_base import (
    _apply_install_badge, _restyle, _run_worker,
)
from .services.network import (
    _is_cifs_available, _is_mounted, _load_smb_config,
    _save_smb_config, _systemd_escape_mount_path,
)
from .services.network_share_helper import _mount_point
from .services.privileged import helper_action, systemctl_action
from .services.runtime import Worker
from .qt import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)
from .widgets import (
    Page, _make_card,
)

# ── Page: Network Shares ──────────────────────────────────────────────────────
class NetworkSharesPage(Page):
    """Mount and manage network shares (SMB/CIFS)."""

    def __init__(self):
        super().__init__()
        self._worker: Worker | None = None
        self._shares: list[dict] = _load_smb_config()
        self._reconnect_name: str | None = None

        self._page_header(
            "Network & Internet",
            "Network Shares",
            "Mount network file shares (SMB/CIFS) and access them as local folders. "
            "Shares can auto-mount at boot so they are always available.",
        )

        # ── cifs-utils warning (shown only when missing) ───────────────────────
        self._cifs_warn, cw_layout = _make_card("card-accent-warn")
        cw_title = QLabel("cifs-utils not installed")
        cw_title.setObjectName("card-title")
        cw_layout.addWidget(cw_title)
        cw_body = QLabel(
            "The mount.cifs helper is missing. It will be present after the next OS update "
            "(cifs-utils has been added to the image). You can still configure shares now; "
            "mounting will work once the image is applied."
        )
        cw_body.setObjectName("card-copy")
        cw_body.setWordWrap(True)
        cw_layout.addWidget(cw_body)
        self._add(self._cifs_warn)

        # ── Add share form ────────────────────────────────────────────────────
        add_card, add_layout = _make_card()
        add_title = QLabel("Add a Network Share")
        add_title.setObjectName("card-title")
        add_layout.addWidget(add_title)
        add_desc = QLabel(
            "Enter the share details. A password prompt will appear to apply system changes."
        )
        add_desc.setObjectName("card-copy")
        add_desc.setWordWrap(True)
        add_layout.addWidget(add_desc)

        form_row = QHBoxLayout()
        form_row.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(8)
        right = QVBoxLayout()
        right.setSpacing(8)

        def _field_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("card-copy")
            return lbl

        # Left column
        left.addWidget(_field_label("Share Name (label)"))
        self._f_name = QLineEdit()
        self._f_name.setPlaceholderText("e.g.  NAS-Media")
        left.addWidget(self._f_name)

        left.addWidget(_field_label("Server (hostname or IP)"))
        self._f_server = QLineEdit()
        self._f_server.setPlaceholderText("e.g.  192.168.1.100  or  mypc")
        left.addWidget(self._f_server)

        left.addWidget(_field_label("Share Path on Server"))
        self._f_share = QLineEdit()
        self._f_share.setPlaceholderText("e.g.  Media  or  Users/Alice/Documents")
        left.addWidget(self._f_share)

        left.addWidget(_field_label("Local Mount Point"))
        self._f_mount = QLineEdit()
        self._f_mount.setPlaceholderText("e.g.  /mnt/kyth/NAS-Media  (default: /mnt/kyth/<name>)")
        left.addWidget(self._f_mount)

        # Right column
        right.addWidget(_field_label("Username"))
        self._f_user = QLineEdit()
        self._f_user.setPlaceholderText("Network share username")
        right.addWidget(self._f_user)

        right.addWidget(_field_label("Password"))
        self._f_pass = QLineEdit()
        self._f_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._f_pass.setPlaceholderText("Network share password")
        right.addWidget(self._f_pass)

        right.addWidget(_field_label("Domain (optional)"))
        self._f_domain = QLineEdit()
        self._f_domain.setPlaceholderText("e.g.  WORKGROUP  (leave blank if unsure)")
        right.addWidget(self._f_domain)

        right.addSpacing(4)
        self._f_auto = QCheckBox("Auto-mount on boot")
        self._f_auto.setChecked(True)
        right.addWidget(self._f_auto)

        form_row.addLayout(left, 1)
        form_row.addLayout(right, 1)
        add_layout.addLayout(form_row)

        add_btn_row = QHBoxLayout()
        add_btn_row.setSpacing(12)
        self._add_share_btn = QPushButton("Add Share")
        self._add_share_btn.setObjectName("primary")
        self._add_share_btn.clicked.connect(self._add_share)
        add_btn_row.addWidget(self._add_share_btn)
        self._mount_now_chk = QCheckBox("Mount immediately")
        self._mount_now_chk.setChecked(True)
        add_btn_row.addWidget(self._mount_now_chk)
        add_btn_row.addStretch()
        add_layout.addLayout(add_btn_row)
        self._add(add_card)

        # ── Operation progress ────────────────────────────────────────────────
        self._op_status = QLabel()
        self._op_status.setWordWrap(True)
        self._op_status.hide()
        self._add(self._op_status)

        self._op_progress = QProgressBar()
        self._op_progress.setRange(0, 0)
        self._op_progress.hide()
        self._add(self._op_progress)

        self._op_log = QTextEdit()
        self._op_log.document().setMaximumBlockCount(5000)
        self._op_log.setReadOnly(True)
        self._op_log.setMinimumHeight(110)
        self._op_log.hide()
        self._add(self._op_log)

        # ── Configured shares list ─────────────────────────────────────────────
        self._divider()

        shares_heading = QLabel("Configured Shares")
        shares_heading.setObjectName("section-heading")
        self._add(shares_heading)

        self._shares_container = QWidget()
        self._shares_container.setObjectName("content-area")
        self._shares_inner = QVBoxLayout(self._shares_container)
        self._shares_inner.setContentsMargins(0, 0, 0, 0)
        self._shares_inner.setSpacing(12)
        self._add(self._shares_container)

        self._stretch()
        self._update_cifs_warning()
        self._rebuild_shares_list()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_cifs_warning(self):
        self._cifs_warn.setVisible(not _is_cifs_available())

    def _rebuild_shares_list(self):
        while self._shares_inner.count():
            item = self._shares_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._shares = _load_smb_config()

        if not self._shares:
            empty = QLabel("No shares configured yet. Use the form above to add one.")
            empty.setObjectName("status-dim")
            self._shares_inner.addWidget(empty)
            return

        for share in self._shares:
            self._shares_inner.addWidget(self._make_share_card(share))

    def _make_share_card(self, share: dict) -> QFrame:
        card, layout = _make_card()

        # Header row
        hdr = QHBoxLayout()
        unc = f"//{share['server']}/{share['share_path'].lstrip('/')}"
        name_lbl = QLabel(share["name"])
        name_lbl.setObjectName("card-title")
        hdr.addWidget(name_lbl)
        hdr.addStretch()
        mounted = _is_mounted(share["mount_point"])
        unit_name = _systemd_escape_mount_path(share["mount_point"])
        unit_exists = os.path.exists(f"/etc/systemd/system/{unit_name}")
        badge = QLabel()
        _apply_install_badge(
            badge, mounted, "Mounted", "Not Mounted" if unit_exists else "Reconnect Needed"
        )
        hdr.addWidget(badge)
        layout.addLayout(hdr)

        # Info labels
        unc_lbl = QLabel(f"{unc}  →  {share['mount_point']}")
        unc_lbl.setObjectName("card-copy")
        layout.addWidget(unc_lbl)

        # Auto-mount toggle
        auto_chk = QCheckBox("Auto-mount on boot")
        auto_chk.setChecked(share.get("auto_mount", False))
        auto_chk.setEnabled(unit_exists)
        if not unit_exists:
            auto_chk.setToolTip("Reconnect this share to recreate its mount and credentials.")
        auto_chk.toggled.connect(
            lambda checked, s=share: self._toggle_auto_mount(s, checked)
        )
        layout.addWidget(auto_chk)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        if not unit_exists:
            reconnect_btn = QPushButton("Reconnect")
            reconnect_btn.setObjectName("primary")
            reconnect_btn.setToolTip("Re-enter the password and recreate this share on this PC.")
            reconnect_btn.clicked.connect(lambda checked=False, s=share: self._prepare_reconnect(s))
            btn_row.addWidget(reconnect_btn)
        elif mounted:
            u_btn = QPushButton("Unmount")
            u_btn.clicked.connect(lambda checked=False, s=share: self._unmount_share(s))
            btn_row.addWidget(u_btn)
        else:
            m_btn = QPushButton("Mount Now")
            m_btn.clicked.connect(lambda checked=False, s=share: self._mount_share(s))
            btn_row.addWidget(m_btn)
        rm_btn = QPushButton("Remove")
        rm_btn.clicked.connect(lambda checked=False, s=share: self._remove_share(s))
        btn_row.addWidget(rm_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return card

    def _prepare_reconnect(self, share: dict):
        self._reconnect_name = share["name"]
        self._f_name.setText(share["name"])
        self._f_server.setText(share["server"])
        self._f_share.setText(share["share_path"])
        self._f_mount.setText(share["mount_point"])
        self._f_user.setText(share.get("username", ""))
        self._f_pass.clear()
        self._f_domain.setText(share.get("domain", ""))
        self._f_auto.setChecked(share.get("auto_mount", False))
        self._mount_now_chk.setChecked(True)
        self._add_share_btn.setText("Reconnect Share")
        self._op_status.setText(
            f"Enter the password for {share['name']}, then choose Reconnect Share."
        )
        self._op_status.setObjectName("status-warn")
        self._op_status.show()
        _restyle(self._op_status)
        self._f_pass.setFocus()

    # ── Form validation ───────────────────────────────────────────────────────

    def _validate_form(self) -> dict | None:
        name       = self._f_name.text().strip()
        server     = self._f_server.text().strip()
        share_path = self._f_share.text().strip()
        mount_pt   = self._f_mount.text().strip()
        username   = self._f_user.text().strip()
        password   = self._f_pass.text()
        domain     = self._f_domain.text().strip()
        auto_mount = self._f_auto.isChecked()

        if not name:
            QMessageBox.warning(self, "Missing Field", "Please enter a Share Name.")
            return None
        if not server:
            QMessageBox.warning(self, "Missing Field", "Please enter a Server address.")
            return None
        if not share_path:
            QMessageBox.warning(self, "Missing Field", "Please enter the Share Path.")
            return None
        if not username:
            QMessageBox.warning(self, "Missing Field", "Please enter a Username.")
            return None

        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
        if not mount_pt:
            mount_pt = f"/mnt/kyth/{safe_name}"
        mount_pt = os.path.expanduser(mount_pt)
        # Same validation the root-side add/remove helper enforces (it runs as
        # root and creates this directory, so mounting over /etc or /usr would
        # corrupt the system) — checked here too so bad input gets a friendly
        # message immediately instead of a less-clear failure from the helper.
        try:
            mount_pt = _mount_point(mount_pt)
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Mount Point",
                "Mount point must be under /mnt/, /media/, /run/media/, or /home/, "
                "and contain only letters, numbers, spaces, '.', '_', '-', or '/'.",
            )
            return None

        existing = {s["name"] for s in self._shares}
        if safe_name in existing and safe_name != self._reconnect_name:
            QMessageBox.warning(
                self, "Duplicate Name",
                f'A share named "{safe_name}" already exists. Remove it first or use a different name.',
            )
            return None

        return {
            "name":       safe_name,
            "server":     server,
            "share_path": share_path.lstrip("/"),
            "mount_point": mount_pt,
            "username":   username,
            "password":   password,
            "domain":     domain,
            "auto_mount": auto_mount,
        }

    # ── Actions ───────────────────────────────────────────────────────────────

    def _add_share(self):
        if self._worker and self._worker.isRunning():
            return
        share = self._validate_form()
        if not share:
            return
        mount_now = self._mount_now_chk.isChecked()
        payload = {
            **share,
            "mount_now": mount_now,
            "uid": os.getuid(),
            "gid": os.getgid(),
        }
        self._begin_op(f"Adding share {share['name']}…")
        _run_worker(
            self,
            helper_action("network-share", "add").command(),
            input_text=json.dumps(payload),
            on_line=self._op_log.append,
            on_done=lambda code, s=share: self._on_add_done(code, s),
        )

    def _on_add_done(self, code: int, share: dict):
        self._op_progress.hide()
        if code == 0:
            saved = {k: v for k, v in share.items() if k != "password"}
            self._shares = [s for s in self._shares if s["name"] != self._reconnect_name]
            self._shares.append(saved)
            _save_smb_config(self._shares)
            self._op_status.setText(
                "Share reconnected successfully."
                if self._reconnect_name else "Share added successfully."
            )
            self._op_status.setObjectName("status-ok")
            self._reconnect_name = None
            self._add_share_btn.setText("Add Share")
            for field in (self._f_name, self._f_server, self._f_share, self._f_mount,
                          self._f_user, self._f_pass, self._f_domain):
                field.clear()
        else:
            self._op_status.setText(f"Add failed (exit {code}). Check the log below.")
            self._op_status.setObjectName("status-err")
        _restyle(self._op_status)
        self._rebuild_shares_list()

    def _mount_share(self, share: dict):
        if self._worker and self._worker.isRunning():
            return
        unit = _systemd_escape_mount_path(share["mount_point"])
        self._run_systemctl("start", unit, f"Mounting {share['name']}…")

    def _unmount_share(self, share: dict):
        if self._worker and self._worker.isRunning():
            return
        unit = _systemd_escape_mount_path(share["mount_point"])
        self._run_systemctl("stop", unit, f"Unmounting {share['name']}…")

    def _toggle_auto_mount(self, share: dict, enabled: bool):
        if self._worker and self._worker.isRunning():
            return
        for s in self._shares:
            if s["name"] == share["name"]:
                s["auto_mount"] = enabled
        _save_smb_config(self._shares)
        unit   = _systemd_escape_mount_path(share["mount_point"])
        action = "enable" if enabled else "disable"
        label  = "Enabling" if enabled else "Disabling"
        self._run_systemctl(action, unit, f"{label} auto-mount for {share['name']}…")

    def _remove_share(self, share: dict):
        reply = QMessageBox.question(
            self, "Remove Share",
            f"Remove \"{share['name']}\" and delete its systemd unit and credentials?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._worker and self._worker.isRunning():
            return
        self._begin_op(f"Removing {share['name']}…")
        _run_worker(
            self,
            helper_action("network-share", "remove").command(),
            input_text=json.dumps({
                "name": share["name"],
                "mount_point": share["mount_point"],
            }),
            on_line=self._op_log.append,
            on_done=lambda code, s=share: self._on_remove_done(code, s),
        )

    def _on_remove_done(self, code: int, share: dict):
        self._op_progress.hide()
        if code == 0:
            self._shares = [s for s in self._shares if s["name"] != share["name"]]
            _save_smb_config(self._shares)
            self._op_status.setText(f"{share['name']} removed.")
            self._op_status.setObjectName("status-ok")
        else:
            self._op_status.setText(f"Remove failed (exit {code}). Check the log below.")
            self._op_status.setObjectName("status-err")
        _restyle(self._op_status)
        self._rebuild_shares_list()

    def _run_systemctl(self, action: str, unit: str, status_msg: str):
        self._begin_op(status_msg)
        _run_worker(
            self,
            systemctl_action(action, unit).command(),
            on_line=self._op_log.append,
            on_done=self._on_generic_done,
        )

    def _on_generic_done(self, code: int):
        self._op_progress.hide()
        if code == 0:
            self._op_status.setText("Done.")
            self._op_status.setObjectName("status-ok")
        else:
            self._op_status.setText(f"Operation failed (exit {code}).")
            self._op_status.setObjectName("status-err")
        _restyle(self._op_status)
        self._rebuild_shares_list()

    def _begin_op(self, msg: str):
        self._op_log.clear()
        self._op_log.show()
        self._op_status.setText(msg)
        self._op_status.setObjectName("status-dim")
        _restyle(self._op_status)
        self._op_status.show()
        self._op_progress.show()
