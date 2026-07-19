import shutil

# __KYTH_GENERATED_IMPORTS__
from ..core_base import _release_worker_when_finished
from ..services.diagnostics import _collect_signin_status, fingerprint_enroll_shell_command
from ..services.gaming import DataWorker
from ..services.launch import open_first, open_settings_module, open_terminal_command
from ..qt import QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from ..widgets import _make_card


class _SigninMixin:
    def _make_signin_card(self) -> QFrame:
        from ..qt import QFrame
        card, layout = _make_card()
        title = QLabel("Sign-in options")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Review fingerprint enrollment, screen locking, automatic login, KWallet, "
            "and passkey readiness from one place. Password sign-in always remains available."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        self._signin_rows = QVBoxLayout()
        self._signin_rows.setSpacing(6)
        layout.addLayout(self._signin_rows)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        enroll_btn = QPushButton("Enroll Fingerprint")
        enroll_btn.setObjectName("primary")
        enroll_btn.clicked.connect(self._enroll_fingerprint)
        btns.addWidget(enroll_btn)
        account_btn = QPushButton("Manage User Account")
        account_btn.clicked.connect(lambda _=False: self._open_signin_settings("kcm_users", "User Accounts"))
        btns.addWidget(account_btn)
        lock_btn = QPushButton("Screen Lock Settings")
        lock_btn.clicked.connect(lambda _=False: self._open_signin_settings("kcm_screenlocker", "Screen Lock"))
        btns.addWidget(lock_btn)
        wallet_btn = QPushButton("Open KWallet")
        wallet_btn.clicked.connect(self._open_wallet)
        btns.addWidget(wallet_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_signin_status)
        btns.addWidget(refresh_btn)
        btns.addStretch()
        layout.addLayout(btns)
        self._signin_status = QLabel("")
        self._signin_status.setObjectName("card-copy")
        self._signin_status.setWordWrap(True)
        layout.addWidget(self._signin_status)
        self._refresh_signin_status()
        return card

    def _clear_signin_rows(self):
        while self._signin_rows.count():
            item = self._signin_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

    def _refresh_signin_status(self):
        worker = getattr(self, "_signin_worker", None)
        if worker is not None and worker.isRunning():
            return
        self._signin_status.setText("Checking sign-in options\u2026")
        self._clear_signin_rows()
        worker = DataWorker("signin", _collect_signin_status)
        worker.result.connect(self._on_signin_status)
        self._signin_worker = worker
        _release_worker_when_finished(self, "_signin_worker", worker)
        worker.start()

    def _on_signin_status(self, _key: str, rows: list):
        glyphs = {"ok": "\u2713", "warn": "!", "dim": "\u00b7"}
        styles = {"ok": "status-ok", "warn": "status-warn", "dim": "status-dim"}
        for status, area, text in rows:
            row = QHBoxLayout()
            row.setSpacing(10)
            mark = QLabel(glyphs.get(status, "\u00b7"))
            mark.setObjectName(styles.get(status, "status-dim"))
            mark.setFixedWidth(16)
            row.addWidget(mark)
            area_lbl = QLabel(area)
            area_lbl.setObjectName("card-summary")
            area_lbl.setMinimumWidth(120)
            row.addWidget(area_lbl)
            text_lbl = QLabel(text)
            text_lbl.setObjectName("card-copy")
            text_lbl.setWordWrap(True)
            row.addWidget(text_lbl, 1)
            self._signin_rows.addLayout(row)
        self._signin_status.setText("")

    def _enroll_fingerprint(self):
        if not shutil.which("fprintd-enroll"):
            self._signin_status.setText(
                "Fingerprint tools are available after applying the latest KythOS update and restarting."
            )
            return
        if open_terminal_command(fingerprint_enroll_shell_command()):
            self._signin_status.setText("Follow the fingerprint prompts in the terminal window.")
            return
        self._open_signin_settings("kcm_users", "User Accounts")

    def _open_signin_settings(self, module: str, label: str):
        if open_settings_module(module):
            self._signin_status.setText("")
            return
        self._signin_status.setText(f"Could not open {label} in this session.")

    def _open_wallet(self):
        if open_first(["kwalletmanager6"], ["kwalletmanager5"]):
            self._signin_status.setText("")
            return
        self._signin_status.setText("KWallet Manager is not installed; saved credentials still use the KWallet service.")
