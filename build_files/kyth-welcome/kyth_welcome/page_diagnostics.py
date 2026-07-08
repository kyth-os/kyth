import configparser
import getpass
import glob
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime

# __KYTH_GENERATED_IMPORTS__
from .core_base import (
    _has_rollback_deployment, _has_staged_update, _release_worker_when_finished, _restyle,
)
from .services.diagnostics import (
    _command_stdout, _diagnostics_report, _health_command_report, _health_recommendations,
)
from .services.gaming import DataWorker
from .services.hardware import (
    HardwareProbe, HardwareProbeWorker,
)
from .services.software import _finish_worker
from .qt import (  # noqa: E501
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QTimer, QVBoxLayout, QWidget,
)
from .widgets import (  # noqa: E501
    ActionRow, EmptyState, HardwareCard, Page, _make_card, _make_flow_step,
)


# ── Security overview ─────────────────────────────────────────────────────────

def _storage_sense_enabled() -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-enabled", "kyth-storage-sense.timer"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "enabled"
    except Exception:
        return False


def _collect_security_status() -> list[tuple[str, str, str]]:
    """Security overview rows: (status, area, text)."""
    rows: list[tuple[str, str, str]] = []

    try:
        r = subprocess.run(["systemctl", "is-active", "firewalld"],
                           capture_output=True, text=True, timeout=5)
        fw_on = r.stdout.strip() == "active"
    except Exception:
        fw_on = False
    rows.append((
        "ok" if fw_on else "warn", "Firewall",
        "firewalld is running — inbound connections are filtered."
        if fw_on else "firewalld is not running — check Repair if you didn't disable it yourself.",
    ))

    enforce = (_command_stdout(["getenforce"], timeout=5) or "").strip()
    rows.append((
        "ok" if enforce == "Enforcing" else "warn", "Access control",
        "SELinux is enforcing — system files and services are isolated."
        if enforce == "Enforcing" else f"SELinux is {enforce or 'unavailable'} (expected: Enforcing).",
    ))

    sb = (_command_stdout(["mokutil", "--sb-state"], timeout=5) or "").lower()
    if "enabled" in sb:
        rows.append(("ok", "Secure Boot", "Firmware verifies the boot chain before KythOS starts."))
    elif "disabled" in sb:
        rows.append(("warn", "Secure Boot", "Disabled. Optional — enable in firmware and run 'ujust enroll-secureboot'."))
    else:
        rows.append(("dim", "Secure Boot", "State unknown (no EFI variables — likely a VM or legacy BIOS boot)."))

    rows.append((
        "ok", "App sandboxing",
        "Store apps run as Flatpaks in sandboxes — permissions are reviewable in Flatseal.",
    ))

    staged = _has_staged_update()
    rows.append((
        "ok", "Updates",
        "An update is downloaded and staged — it applies on the next restart."
        if staged else "OS updates download automatically in the background and apply on restart.",
    ))

    rows.append((
        "ok" if _has_rollback_deployment() else "dim", "Recovery",
        "The previous OS version is kept — one-click rollback from Repair."
        if _has_rollback_deployment() else "A rollback point appears automatically after your first update.",
    ))

    rows.append((
        "ok", "Antivirus",
        "No Defender needed: the OS is read-only and cryptographically verified on "
        "every update, and apps are sandboxed. There is nothing to subscribe to.",
    ))
    return rows


def _collect_signin_status() -> list[tuple[str, str, str]]:
    """Account and sign-in overview."""
    rows: list[tuple[str, str, str]] = []
    user = getpass.getuser()

    try:
        result = subprocess.run(
            ["fprintd-list", user], capture_output=True, text=True, timeout=12,
        )
        detail = (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        result = None
        detail = "fprintd is not installed"
    except Exception as exc:
        result = None
        detail = str(exc)
    lower = detail.lower()
    if result is not None and result.returncode == 0 and "finger" in lower:
        rows.append(("ok", "Fingerprint", "A fingerprint is enrolled for this account."))
    elif "no devices available" in lower or "no devices" in lower:
        rows.append(("dim", "Fingerprint", "No supported fingerprint reader was detected."))
    elif "no fingerprints" in lower or "not enrolled" in lower:
        rows.append(("warn", "Fingerprint", "Reader detected, but no fingerprint is enrolled yet."))
    else:
        rows.append(("dim", "Fingerprint", f"Fingerprint state unavailable: {detail or 'unknown state'}."))

    autolock = (_command_stdout([
        "kreadconfig6", "--file", "kscreenlockerrc", "--group", "Daemon", "--key", "Autolock",
    ], timeout=5) or "true").lower()
    lock_resume = (_command_stdout([
        "kreadconfig6", "--file", "kscreenlockerrc", "--group", "Daemon", "--key", "LockOnResume",
    ], timeout=5) or "true").lower()
    lock_ok = autolock not in ("false", "0") and lock_resume not in ("false", "0")
    rows.append((
        "ok" if lock_ok else "warn", "Screen lock",
        "Automatic locking and lock-on-resume are enabled."
        if lock_ok else "Automatic locking or lock-on-resume is disabled; review Screen Lock settings.",
    ))

    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.optionxform = str
    sddm_files = ["/etc/sddm.conf", *sorted(glob.glob("/etc/sddm.conf.d/*.conf"))]
    try:
        config.read(sddm_files)
        autologin_user = config.get("Autologin", "User", fallback="").strip()
    except (configparser.Error, OSError):
        autologin_user = ""
    autologin = autologin_user == user
    rows.append((
        "warn" if autologin else "ok", "Automatic login",
        "Enabled for this account — convenient, but anyone with the PC can enter the desktop."
        if autologin else "Off for this account; a sign-in is required after startup.",
    ))

    wallet_enabled = (_command_stdout([
        "kreadconfig6", "--file", "kwalletrc", "--group", "Wallet", "--key", "Enabled",
    ], timeout=5) or "true").lower() not in ("false", "0")
    rows.append((
        "ok" if wallet_enabled else "warn", "Credential vault",
        "KWallet is enabled for saved app and network credentials."
        if wallet_enabled else "KWallet is disabled; apps may store credentials less conveniently.",
    ))

    rows.append((
        "ok", "Passkeys",
        "Passkeys are managed by your browser or password manager and protected by its sign-in controls.",
    ))
    return rows

# ── Page: Diagnostics ─────────────────────────────────────────────────────────
class DiagnosticsPage(Page):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._health_worker = None
        self._initial_refresh_started = False
        self._last_probes: list[HardwareProbe] = []
        self._base_report = ""
        self._health_report = ""
        self._probe_cards: dict[str, HardwareCard] = {}

        self._page_header(
            "System",
            "Health Report",
            "A quick look at how your hardware and system stack are doing.",
        )

        triage_card, triage_layout = _make_card()
        triage_title = QLabel("Health report triage")
        triage_title.setObjectName("card-title")
        triage_layout.addWidget(triage_title)
        for i, (title, copy) in enumerate((
            ("Summary first", "The banner tells you whether the system looks healthy, needs attention, or has a blocking issue."),
            ("Cards next", "Hardware and security rows point at the specific area: graphics, display, audio, network, storage, recovery, or sign-in."),
            ("Details last", "Technical logs stay collapsed until you need to copy, save, or attach them to an issue."),
        ), 1):
            triage_layout.addWidget(_make_flow_step(i, title, copy))
        self._add(triage_card)

        self._actions = ActionRow("Ready to run a fresh health report.", "idle")
        self._refresh_btn = self._actions.add_button("Run Health Report", self.refresh, primary=True)
        self._copy_btn = self._actions.add_button("Copy Report", self._copy_report)
        self._save_btn = self._actions.add_button("Save Report…", self._save_report)
        self._issue_btn = self._actions.add_button("Report Issue", self._report_issue)
        self._actions.finish()
        self._copy_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._issue_btn.setEnabled(False)
        self._status_lbl = self._actions.status
        self._add(self._actions)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._add(self._progress)

        # Summary banner
        self._banner_card, self._banner_layout = _make_card()
        self._banner_title = QLabel()
        self._banner_title.setObjectName("card-title")
        self._banner_layout.addWidget(self._banner_title)
        self._banner_body = QLabel()
        self._banner_body.setObjectName("card-copy")
        self._banner_body.setWordWrap(True)
        self._banner_layout.addWidget(self._banner_body)
        self._banner_card.hide()
        self._add(self._banner_card)

        # Per-probe cards
        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._add(self._cards_widget)
        self._empty_state = EmptyState(
            "No checks to show yet",
            "Run a health report to populate hardware, security, and recovery checks.",
            "Run Health Report",
            self.refresh,
        )
        self._empty_state.hide()
        self._add(self._empty_state)

        # Raw report (hidden; surfaced via toggle for support use)
        self._raw_toggle = QPushButton("Show technical details")
        self._raw_toggle.setCheckable(True)
        self._raw_toggle.setChecked(False)
        self._raw_toggle.toggled.connect(self._toggle_raw)
        self._raw_toggle.hide()
        self._add(self._raw_toggle)

        self._report = QTextEdit()
        self._report.document().setMaximumBlockCount(5000)
        self._report.setReadOnly(True)
        self._report.setMinimumHeight(220)
        self._report.hide()
        self._add(self._report)

        self._add(self._make_security_card())
        self._add(self._make_signin_card())
        self._add(self._make_storage_sense_card())

        self._stretch()
    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        QTimer.singleShot(0, self.refresh)


    def _set_status(self, state: str, text: str) -> None:
        self._status_lbl.set_state(state, text)

    # ── Security at a glance ────────────────────────────────────────────────
    def _make_security_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Security at a glance")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "The Security checklist, KythOS edition — what protects this "
            "PC and whether it's active right now."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        self._security_rows = QVBoxLayout()
        self._security_rows.setSpacing(6)
        layout.addLayout(self._security_rows)

        worker = DataWorker("security", _collect_security_status)
        worker.result.connect(self._on_security_status)
        self._security_worker = worker
        _release_worker_when_finished(self, "_security_worker", worker)
        worker.start()
        return card

    def _on_security_status(self, _key: str, rows: list):
        glyphs = {"ok": "✓", "warn": "!", "dim": "·"}
        styles = {"ok": "status-ok", "warn": "status-warn", "dim": "status-dim"}
        for status, area, text in rows:
            row = QHBoxLayout()
            row.setSpacing(10)
            mark = QLabel(glyphs.get(status, "·"))
            mark.setObjectName(styles.get(status, "status-dim"))
            mark.setFixedWidth(16)
            row.addWidget(mark)
            area_lbl = QLabel(area)
            area_lbl.setObjectName("card-summary")
            area_lbl.setMinimumWidth(110)
            row.addWidget(area_lbl)
            text_lbl = QLabel(text)
            text_lbl.setObjectName("card-copy")
            text_lbl.setWordWrap(True)
            row.addWidget(text_lbl, 1)
            self._security_rows.addLayout(row)

    # ── Sign-in options ─────────────────────────────────────────────────────
    def _make_signin_card(self) -> QFrame:
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
        self._signin_status.setText("Checking sign-in options…")
        self._clear_signin_rows()
        worker = DataWorker("signin", _collect_signin_status)
        worker.result.connect(self._on_signin_status)
        self._signin_worker = worker
        _release_worker_when_finished(self, "_signin_worker", worker)
        worker.start()

    def _on_signin_status(self, _key: str, rows: list):
        glyphs = {"ok": "✓", "warn": "!", "dim": "·"}
        styles = {"ok": "status-ok", "warn": "status-warn", "dim": "status-dim"}
        for status, area, text in rows:
            row = QHBoxLayout()
            row.setSpacing(10)
            mark = QLabel(glyphs.get(status, "·"))
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
        user = shlex.quote(getpass.getuser())
        command = (
            f"fprintd-enroll {user}; code=$?; echo; "
            "if [ $code -eq 0 ]; then echo 'Fingerprint enrollment complete.'; "
            "else echo 'Fingerprint enrollment did not complete.'; fi; "
            "read -rp 'Press Enter to close…'"
        )
        for terminal in ("konsole", "kgx", "gnome-terminal"):
            if not shutil.which(terminal):
                continue
            try:
                if terminal == "konsole":
                    subprocess.Popen([terminal, "-e", "bash", "-lc", command])
                else:
                    subprocess.Popen([terminal, "--", "bash", "-lc", command])
                self._signin_status.setText("Follow the fingerprint prompts in the terminal window.")
                return
            except OSError:
                continue
        self._open_signin_settings("kcm_users", "User Accounts")

    def _open_signin_settings(self, module: str, label: str):
        for cmd in (["kcmshell6", module], ["systemsettings", module], ["systemsettings"]):
            if not shutil.which(cmd[0]):
                continue
            try:
                subprocess.Popen(cmd)
                self._signin_status.setText("")
                return
            except OSError:
                continue
        self._signin_status.setText(f"Could not open {label} in this session.")

    def _open_wallet(self):
        for binary in ("kwalletmanager5", "kwalletmanager6"):
            if shutil.which(binary):
                try:
                    subprocess.Popen([binary])
                    self._signin_status.setText("")
                    return
                except OSError:
                    continue
        self._signin_status.setText("KWallet Manager is not installed; saved credentials still use the KWallet service.")

    # ── Storage Sense ───────────────────────────────────────────────────────
    def _make_storage_sense_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Storage Sense — automatic cleanup")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Once a week: empties Recycle Bin items older than 30 days, removes "
            "unused Flatpak runtimes, and trims old logs. Your files are never "
            "touched — only things already thrown away or no longer used."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._storage_sense_btn = QPushButton()
        self._storage_sense_btn.clicked.connect(self._toggle_storage_sense)
        btns.addWidget(self._storage_sense_btn)
        run_now_btn = QPushButton("Clean Up Now")
        run_now_btn.setToolTip("Runs one cleanup pass immediately.")
        run_now_btn.clicked.connect(self._run_storage_sense_now)
        btns.addWidget(run_now_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self._storage_sense_status = QLabel("")
        self._storage_sense_status.setObjectName("card-copy")
        self._storage_sense_status.setWordWrap(True)
        self._storage_sense_status.hide()
        layout.addWidget(self._storage_sense_status)
        self._refresh_storage_sense_btn()
        return card

    def _refresh_storage_sense_btn(self):
        if _storage_sense_enabled():
            self._storage_sense_btn.setText("Turn Off Storage Sense")
            self._storage_sense_btn.setObjectName("")
        else:
            self._storage_sense_btn.setText("Turn On Storage Sense")
            self._storage_sense_btn.setObjectName("primary")
        _restyle(self._storage_sense_btn)

    def _toggle_storage_sense(self):
        action = "disable" if _storage_sense_enabled() else "enable"
        try:
            r = subprocess.run(
                ["systemctl", "--user", action, "--now", "kyth-storage-sense.timer"],
                capture_output=True, text=True, timeout=15,
            )
        except Exception as exc:
            self._storage_sense_status.setText(f"✗ {exc}")
            self._storage_sense_status.show()
            return
        if r.returncode == 0:
            self._storage_sense_status.setText(
                "✓ Storage Sense is on — cleanup runs weekly in the background."
                if action == "enable" else "Storage Sense is off."
            )
        else:
            detail = (r.stderr or r.stdout).strip()
            self._storage_sense_status.setText(
                f"✗ Could not {action} the cleanup timer: {detail or 'unknown error'}. "
                "If you updated recently, restart once so the new timer is available."
            )
        self._storage_sense_status.show()
        self._refresh_storage_sense_btn()

    def _run_storage_sense_now(self):
        try:
            subprocess.Popen(["systemd-run", "--user", "--collect", "/usr/bin/kyth-storage-sense"])
            self._storage_sense_status.setText("✓ Cleanup started in the background.")
        except OSError as exc:
            self._storage_sense_status.setText(f"✗ {exc}")
        self._storage_sense_status.show()

    def _clear_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._probe_cards = {}

    def _build_summary_banner(self, probes: list[HardwareProbe]) -> None:
        errs  = [p for p in probes if p.status == "err"]
        warns = [p for p in probes if p.status == "warn"]
        oks   = [p for p in probes if p.status == "ok"]
        if errs:
            self._banner_card.setObjectName("card-accent-err")
            self._banner_title.setText(
                f"{len(errs)} issue{'s' if len(errs) != 1 else ''} found"
            )
            self._banner_body.setText(
                "Some hardware or system checks need attention. "
                "Review the items below and follow the suggested fixes."
            )
        elif warns:
            self._banner_card.setObjectName("card-accent-warn")
            self._banner_title.setText(
                f"{len(warns)} warning{'s' if len(warns) != 1 else ''}"
            )
            self._banner_body.setText(
                "Everything is mostly working but some things could be improved. "
                "Check the items below for details."
            )
        else:
            self._banner_card.setObjectName("card-accent-ok")
            self._banner_title.setText(f"All {len(oks)} checks passed")
            self._banner_body.setText("Your hardware and system stack look healthy.")
        _restyle(self._banner_card)
        self._banner_card.show()

    def refresh(self):
        self._refresh_btn.setEnabled(False)
        self._copy_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._issue_btn.setEnabled(False)
        self._set_status("running", "Gathering system information…")
        self._progress.show()
        self._base_report = ""
        self._health_report = ""
        self._banner_card.hide()
        self._empty_state.hide()
        self._raw_toggle.hide()
        self._report.hide()
        self._report.setPlainText("")
        self._clear_cards()

        self._worker = HardwareProbeWorker()
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, probes: list[HardwareProbe]):
        self._progress.hide()
        self._refresh_btn.setEnabled(True)
        _finish_worker(self)
        self._last_probes = probes
        self._base_report = _diagnostics_report(probes)

        self._build_summary_banner(probes)
        self._clear_cards()
        if probes:
            self._empty_state.hide()
            for probe in probes:
                card = HardwareCard(probe)
                self._probe_cards[probe.title] = card
                self._cards_layout.addWidget(card)
        else:
            self._empty_state.show()

        levels = {p.status for p in probes}
        if "err" in levels:
            self._set_status("err", "Issues found — running extended checks…")
        elif "warn" in levels:
            self._set_status("warn", "Warnings found — running extended checks…")
        else:
            self._set_status("ok", "Hardware checks passed — running extended checks…")

        self._health_worker = DataWorker("health", _health_command_report)
        self._health_worker.result.connect(self._on_health_done)
        self._health_worker.failed.connect(self._on_health_failed)
        self._health_worker.start()

    def _on_health_done(self, _key: str, report: str):
        _finish_worker(self, "_health_worker")
        self._health_report = str(report)
        recs = _health_recommendations(self._base_report + self._health_report)
        self._report.setPlainText(self._base_report + recs + self._health_report)
        self._copy_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._issue_btn.setEnabled(True)
        self._raw_toggle.show()

        has_failures = (
            re.search(r"^FAIL\s+", self._health_report, re.MULTILINE)
            or re.search(r"^FAIL:\s*[1-9]", self._health_report, re.MULTILINE)
            or "Result: not daily-driver ready" in self._health_report
        )
        has_warnings = (
            re.search(r"^WARN\s+", self._health_report, re.MULTILINE)
            or re.search(r"^WARN:\s*[1-9]", self._health_report, re.MULTILINE)
            or "Result: controller readiness has warnings" in self._health_report
            or "Result: resume readiness has warnings" in self._health_report
        )
        if has_failures:
            self._set_status("err", "Issues found — check the details above.")
        elif has_warnings:
            self._set_status("warn", "Warnings found — review the items above.")
        else:
            self._set_status("ok", "All checks completed successfully.")

    def _on_health_failed(self, _key: str, message: str):
        _finish_worker(self, "_health_worker")
        self._health_report = f"\nKythOS Health Command Output\n==========================\n\nfailed: {message}\n"
        self._report.setPlainText(self._base_report + self._health_report)
        self._copy_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._issue_btn.setEnabled(True)
        self._raw_toggle.show()
        self._set_status("err", f"Extended checks failed: {message}")

    def _on_failed(self, message: str):
        self._progress.hide()
        self._refresh_btn.setEnabled(True)
        _finish_worker(self)
        self._set_status("err", f"Failed: {message}")

    def _toggle_raw(self, checked: bool):
        self._raw_toggle.setText(
            "Hide technical details" if checked else "Show technical details"
        )
        self._report.setVisible(checked)

    def _copy_report(self):
        QApplication.clipboard().setText(self._report.toPlainText())
        self._set_status("ok", "Report copied to clipboard.")

    def _save_report(self):
        default = os.path.expanduser(f"~/Documents/kyth-health-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save Health Report", default, "Text Files (*.txt);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._report.toPlainText())
            self._set_status("ok", f"Saved to {path}.")
        except OSError as exc:
            self._set_status("err", f"Could not save: {exc}")

    def _report_issue(self):
        report = self._report.toPlainText().strip()
        if not report:
            self._set_status("warn", "Run a health report first.")
            return
        report_dir = os.path.expanduser("~/.local/state/kyth")
        body_path = os.path.join(report_dir, f"health-report-issue-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md")
        body = (
            "## What happened\n\n"
            "Describe what you were doing and what went wrong.\n\n"
            "## KythOS health report\n\n"
            "```text\n"
            f"{report}\n"
            "```\n"
        )
        try:
            os.makedirs(report_dir, exist_ok=True)
            with open(body_path, "w", encoding="utf-8") as fh:
                fh.write(body)
            subprocess.Popen([
                "/usr/bin/kyth-report-issue",
                "--title", "KythOS health report issue",
                "--body-file", body_path,
                "--label", "bug",
            ])
            self._set_status("ok", "Opening a prefilled GitHub issue.")
        except OSError as exc:
            self._set_status("err", f"Could not prepare issue: {exc}")
