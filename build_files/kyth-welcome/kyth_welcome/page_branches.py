import logging
import time

# __KYTH_GENERATED_IMPORTS__
from .services.launch import reboot
from .core_base import (
    DownloadMonitor, _bootc_image_timestamp, _branch_display_name, _get_rx_bytes, _human_bytes, _human_bytes_pair,
    _image_tag_for_channel, _parse_size_bytes, _restyle, _set_session_inhibit, _with_idle_inhibit,
)
from .services.runtime import Worker, _finish_worker
from .core_base import REGISTRY, _bootc_image_digest, _current_branch
from .qt import (
    QApplication, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QTimer, Qt,
)
from .widgets import (
    Page, _make_card, _set_log_panel,
)

_logger = logging.getLogger(__name__)

# ── Page: Branches ────────────────────────────────────────────────────────────
class BranchesPage(Page):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._dl_monitor = None
        self._dl_total = 0
        self._dl_speed = 0
        self._dl_eta = 0
        self._op_start_ts = 0.0
        self._current_phase = ""
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(5000)
        self._heartbeat.timeout.connect(self._heartbeat_tick)

        self._page_header(
            "Advanced",
            "Channels",
            "Choose which KythOS image stream this system follows.",
        )

        # Compact current deployment state bar
        state_card, state_layout = _make_card()
        state_layout.setSpacing(4)
        state_top = QHBoxLayout()
        state_top.setSpacing(16)
        state_branch_lbl = QLabel("Running:")
        state_branch_lbl.setObjectName("card-copy")
        state_branch_lbl.setStyleSheet("color: #888888; min-width: 64px;")
        state_top.addWidget(state_branch_lbl)
        self._state_branch_val = QLabel()
        self._state_branch_val.setObjectName("card-copy")
        state_top.addWidget(self._state_branch_val, 1)
        state_layout.addLayout(state_top)

        state_bottom = QHBoxLayout()
        state_bottom.setSpacing(16)
        state_digest_lbl = QLabel("Digest:")
        state_digest_lbl.setObjectName("card-copy")
        state_digest_lbl.setStyleSheet("color: #888888; min-width: 64px;")
        state_bottom.addWidget(state_digest_lbl)
        self._state_digest_val = QLabel()
        self._state_digest_val.setObjectName("card-copy")
        self._state_digest_val.setStyleSheet(
            "font-family: 'Noto Mono', 'Cascadia Code', monospace; font-size: 12px;"
        )
        self._state_digest_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        state_bottom.addWidget(self._state_digest_val, 1)
        self._state_copy_btn = QPushButton("Copy")
        self._state_copy_btn.setFixedWidth(56)
        self._state_copy_btn.hide()
        self._state_digest_full = ""
        self._state_copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(f"sha256:{self._state_digest_full}")
        )
        state_bottom.addWidget(self._state_copy_btn)
        state_layout.addLayout(state_bottom)
        self._add(state_card)

        # Branch selector cards
        selector_row = QHBoxLayout()
        selector_row.setSpacing(14)

        stable_card, stable_layout = _make_card()
        stable_title = QLabel("Stable")
        stable_title.setObjectName("card-title")
        stable_layout.addWidget(stable_title)
        stable_desc = QLabel(
            "Daily rebuilds from the main branch. Thoroughly tested before tagging.\n"
            "Recommended for most users."
        )
        stable_desc.setObjectName("card-copy")
        stable_desc.setWordWrap(True)
        stable_layout.addWidget(stable_desc)
        self._stable_build_lbl = QLabel()
        self._stable_build_lbl.setObjectName("card-copy")
        self._stable_build_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        self._stable_build_lbl.hide()
        stable_layout.addWidget(self._stable_build_lbl)
        self._stable_btn = QPushButton("Switch to Stable")
        self._stable_btn.clicked.connect(lambda: self._switch(_image_tag_for_channel("latest")))
        stable_layout.addWidget(self._stable_btn)
        selector_row.addWidget(stable_card, 1)

        testing_card, testing_layout = _make_card()
        testing_title = QLabel("Testing")
        testing_title.setObjectName("card-title")
        testing_layout.addWidget(testing_title)
        testing_desc = QLabel(
            "Tracks the testing branch — latest features and changes as they land.\n"
            "May occasionally be unstable."
        )
        testing_desc.setObjectName("card-copy")
        testing_desc.setWordWrap(True)
        testing_layout.addWidget(testing_desc)
        self._testing_build_lbl = QLabel()
        self._testing_build_lbl.setObjectName("card-copy")
        self._testing_build_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        self._testing_build_lbl.hide()
        testing_layout.addWidget(self._testing_build_lbl)
        self._testing_btn = QPushButton("Switch to Testing")
        self._testing_btn.clicked.connect(lambda: self._switch(_image_tag_for_channel("testing")))
        testing_layout.addWidget(self._testing_btn)
        selector_row.addWidget(testing_card, 1)

        self._add_layout(selector_row)
        self._divider()

        self._status_lbl = QLabel()
        self._status_lbl.hide()
        self._add(self._status_lbl)

        self._activity_lbl = QLabel()
        self._activity_lbl.setObjectName("card-copy")
        self._activity_lbl.setWordWrap(True)
        self._activity_lbl.hide()
        self._add(self._activity_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._add(self._progress)

        self._log_toggle = QPushButton("Show details")
        self._log_toggle.setCheckable(True)
        self._log_toggle.clicked.connect(lambda checked: _set_log_panel(self._log_toggle, self._log, checked))
        self._log_toggle.hide()
        self._add(self._log_toggle)

        self._log = QTextEdit()
        self._log.document().setMaximumBlockCount(5000)
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)
        self._log.hide()
        self._add(self._log)

        self._reboot_btn = QPushButton("Reboot to Apply")
        self._reboot_btn.setObjectName("primary")
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(reboot)
        self._add(self._reboot_btn)
        self._stretch()

        self._refresh_current()

    def _refresh_current(self):
        tag = _current_branch()
        booted_ts = _bootc_image_timestamp("booted")
        booted_digest = _bootc_image_digest("booted")

        # State bar
        branch_text = _branch_display_name(tag)
        if booted_ts:
            branch_text += f"  ·  built {booted_ts}"
        self._state_branch_val.setText(branch_text)

        if booted_digest:
            short, full = booted_digest
            self._state_digest_val.setText(f"{short}…")
            self._state_digest_full = full
            self._state_copy_btn.show()
        else:
            self._state_digest_val.setText("—")
            self._state_copy_btn.hide()

        # Branch cards
        if tag in ("latest", "latest-cachy"):
            self._stable_btn.setObjectName("branch-active")
            self._stable_btn.setText("On Stable  (current)")
            self._stable_build_lbl.setText(f"Running: built {booted_ts}" if booted_ts else "")
            self._stable_build_lbl.setVisible(bool(booted_ts))
            self._testing_btn.setObjectName("branch-inactive")
            self._testing_btn.setText("Switch to Testing")
            self._testing_build_lbl.hide()
        elif tag in ("testing", "testing-cachy"):
            self._stable_btn.setObjectName("branch-inactive")
            self._stable_btn.setText("Switch to Stable")
            self._stable_build_lbl.hide()
            self._testing_btn.setObjectName("branch-active")
            self._testing_btn.setText("On Testing  (current)")
            self._testing_build_lbl.setText(f"Running: built {booted_ts}" if booted_ts else "")
            self._testing_build_lbl.setVisible(bool(booted_ts))
        else:
            self._stable_btn.setObjectName("branch-inactive")
            self._stable_btn.setText("Switch to Stable")
            self._stable_build_lbl.hide()
            self._testing_btn.setObjectName("branch-inactive")
            self._testing_btn.setText("Switch to Testing")
            self._testing_build_lbl.hide()

        _restyle(self._stable_btn)
        _restyle(self._testing_btn)

    def _switch(self, tag: str):
        ref = f"{REGISTRY}:{tag}"
        self._stop_dl_monitor()
        self._dl_total = 0
        self._dl_speed = 0
        self._dl_eta = 0
        self._op_start_ts = time.monotonic()
        self._current_phase = ""
        self._log.clear()
        self._log.append(f"→ bootc switch {ref}\n")
        self._log_toggle.show()
        _set_log_panel(self._log_toggle, self._log, False)
        self._progress.setRange(0, 0)
        self._progress.show()
        self._status_lbl.setText("Switching branch…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        _restyle(self._status_lbl)
        self._reboot_btn.hide()
        self._stable_btn.setEnabled(False)
        self._testing_btn.setEnabled(False)

        self._worker = Worker(_with_idle_inhibit(["sudo", "bootc", "switch", ref], "KythOS is switching branch"))
        _set_session_inhibit(self, "KythOS is switching the system branch")
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_done)
        self._worker.start()
        self._update_activity()
        self._heartbeat.start()

    def _stop_dl_monitor(self):
        if self._dl_monitor is not None:
            self._dl_monitor.stop()
            self._dl_monitor.wait()
            self._dl_monitor.deleteLater()
            self._dl_monitor = None

    def _on_line(self, text: str):
        if "layers needed:" in text and self._dl_monitor is None:
            try:
                m = text.split("layers needed:")[1]
                size_str = m.split("(")[1].rstrip(")") if "(" in m else ""
                total = _parse_size_bytes(size_str)
                if total > 0:
                    self._dl_total = total
                    self._progress.setRange(0, 1000)
                    self._dl_monitor = DownloadMonitor(total, _get_rx_bytes())
                    self._dl_monitor.stats.connect(self._on_dl_stats)
                    self._dl_monitor.start()
            except Exception:
                _logger.debug("_on_line: failed to parse download size from %r", text, exc_info=True)
        self._log.append(text)
        self._log.ensureCursorVisible()

    def _on_dl_stats(self, downloaded: int, total: int, speed_bps: int, eta_sec: int):
        self._dl_speed = speed_bps
        self._dl_eta = eta_sec
        if total > 0:
            self._progress.setValue(int(min(downloaded / total, 1.0) * 1000))
        if speed_bps > 100_000:
            dl_dl, dl_total = _human_bytes_pair(downloaded, total)
            dl_str = f"{dl_dl} / {dl_total}"
            speed_str = f"{_human_bytes(speed_bps)}/s"
            if eta_sec > 60:
                eta_mins, eta_secs = divmod(eta_sec, 60)
                eta_str = f"~{eta_mins}m {eta_secs:02d}s remaining"
            elif eta_sec > 0:
                eta_str = f"~{eta_sec}s remaining"
            else:
                eta_str = ""
            parts = [dl_str, speed_str]
            if eta_str:
                parts.append(eta_str)
            self._activity_lbl.setText("  ·  ".join(parts))
            self._activity_lbl.show()

    def _update_activity(self):
        elapsed = int(time.monotonic() - self._op_start_ts) if self._op_start_ts else 0
        mins, secs = divmod(elapsed, 60)
        elapsed_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        phase = self._current_phase or "Switching branch…"
        self._activity_lbl.setText(f"{phase}  ·  {elapsed_str} elapsed")
        self._activity_lbl.show()

    def _heartbeat_tick(self):
        if self._worker is None:
            self._heartbeat.stop()
            return
        self._update_activity()

    def _on_done(self, code: int):
        self._heartbeat.stop()
        self._stop_dl_monitor()
        self._progress.hide()
        self._activity_lbl.hide()
        self._stable_btn.setEnabled(True)
        self._testing_btn.setEnabled(True)
        _finish_worker(self)
        _set_session_inhibit(self, None)

        if code == 0:
            self._status_lbl.setText("Branch staged — reboot to apply.")
            self._status_lbl.setObjectName("status-ok")
            self._log.append("\nDone. Reboot to boot into the new branch.")
            self._reboot_btn.show()
        else:
            self._status_lbl.setText(f"Switch failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")

        _restyle(self._status_lbl)
        self._refresh_current()
