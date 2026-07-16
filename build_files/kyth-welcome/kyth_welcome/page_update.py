import json
import subprocess
import time
from datetime import datetime

# __KYTH_GENERATED_IMPORTS__
from .core_base import (
    DownloadMonitor, _active_bootc_operation, _bootc_cancel_block_reason, _bootc_image_timestamp,
    _bootc_proxy_running, _branch_display_name, _get_disk_write_bytes, _get_rx_bytes, _has_rollback_deployment,
    _has_staged_update, _human_bytes, _human_bytes_pair, _parse_size_bytes, _parse_update_phase,
    _release_worker_when_finished, _restyle, _set_session_inhibit, _with_idle_inhibit,
)
from .services.software import (
    Worker, _finish_worker,
)
from .services.updates import (
    FirmwareCheckWorker, UpdateCheckWorker, _current_branch, FlatpakCheckWorker, ChangelogWorker,
)
from .qt import (  # noqa: E501
    QCheckBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QTextEdit, QTimer, QVBoxLayout, Qt,
)
from .widgets import (  # noqa: E501
    Page, _make_card, _set_log_panel,
)

# ── Page: Update ──────────────────────────────────────────────────────────────
class UpdatePage(Page):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._dl_monitor = None
        self._dl_total = 0
        self._dl_downloaded = 0
        self._dl_speed = 0
        self._dl_eta = 0
        self._mode = "topgrade"
        self._last_output_ts = 0.0
        self._op_start_ts = 0.0
        self._current_phase = ""
        self._cancel_blocked = False
        self._cancel_block_reason = ""
        self._staging_write_start = 0
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(5000)
        self._heartbeat.timeout.connect(self._heartbeat_tick)
        self._check_worker = None
        self._flatpak_check_worker = None
        self._flatpak_checked = False
        self._system_checked = False
        self._flatpak_count = 0
        self._remote_manifest = ""
        self._check_state = "idle"   # idle | checking | available | uptodate | error
        self._check_ts = ""

        self._page_header(
            "System",
            "Updates",
            "Check update status, stage new images, and restart when you are ready.",
        )

        # ── Update availability ───────────────────────────────────────────────
        avail_card, avail_layout = _make_card()
        avail_layout.setSpacing(0)

        avail_hero = QHBoxLayout()
        avail_hero.setSpacing(16)
        avail_hero.setContentsMargins(0, 0, 0, 0)

        self._avail_icon = QLabel("○")
        self._avail_icon.setFixedWidth(40)
        self._avail_icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self._avail_icon.setStyleSheet("font-size: 28px; color: #555555;")
        avail_hero.addWidget(self._avail_icon)

        avail_text_col = QVBoxLayout()
        avail_text_col.setSpacing(4)
        avail_text_col.setContentsMargins(0, 0, 0, 0)
        self._avail_title = QLabel("Checking for updates…")
        self._avail_title.setObjectName("card-title")
        avail_text_col.addWidget(self._avail_title)
        self._avail_lbl = QLabel()
        self._avail_lbl.setObjectName("card-copy")
        self._avail_lbl.setWordWrap(True)
        avail_text_col.addWidget(self._avail_lbl)
        avail_hero.addLayout(avail_text_col, 1)

        avail_btn_col = QVBoxLayout()
        avail_btn_col.setSpacing(6)
        avail_btn_col.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self._update_now_btn = QPushButton("Update Now")
        self._update_now_btn.setObjectName("primary")
        self._update_now_btn.setMinimumWidth(120)
        self._update_now_btn.hide()
        self._update_now_btn.clicked.connect(self._run_topgrade)
        avail_btn_col.addWidget(self._update_now_btn)
        self._restart_now_btn = QPushButton("Restart Now")
        self._restart_now_btn.setObjectName("primary")
        self._restart_now_btn.setMinimumWidth(120)
        self._restart_now_btn.hide()
        self._restart_now_btn.clicked.connect(lambda: subprocess.Popen(["systemctl", "reboot"]))
        avail_btn_col.addWidget(self._restart_now_btn)
        self._check_btn = QPushButton("Check Now")
        self._check_btn.setEnabled(False)
        self._check_btn.setMinimumWidth(120)
        self._check_btn.clicked.connect(self._check_for_update)
        avail_btn_col.addWidget(self._check_btn)
        avail_hero.addLayout(avail_btn_col)

        avail_layout.addLayout(avail_hero)
        self._avail_card = avail_card
        self._add(self._avail_card)

        # Status summary
        self._summary_card, summary_layout = _make_card()
        summary_layout.setSpacing(6)
        summary_title = QLabel("Image status")
        summary_title.setObjectName("card-title")
        summary_layout.addWidget(summary_title)

        def _state_row(label_text: str) -> tuple[QHBoxLayout, QLabel]:
            row = QHBoxLayout()
            row.setSpacing(12)
            key = QLabel(label_text)
            key.setObjectName("prop-key")
            key.setMinimumWidth(76)
            row.addWidget(key)
            val = QLabel()
            val.setObjectName("prop-val")
            val.setWordWrap(False)
            row.addWidget(val, 1)
            return row, val

        booted_row, self._booted_val = _state_row("Running:")
        staged_row, self._staged_val = _state_row("Staged:")
        rollback_row, self._rollback_val = _state_row("Rollback:")
        for row in (booted_row, staged_row, rollback_row):
            summary_layout.addLayout(row)
        self._add(self._summary_card)

        # Manual actions
        action_card, action_layout = _make_card()
        action_title = QLabel("Manual actions")
        action_title.setObjectName("card-title")
        action_layout.addWidget(action_title)
        action_body = QLabel(
            "Full Update handles the OS image, Flatpaks, and managed tools. "
            "OS Image Only stages just the next bootable image."
        )
        action_body.setObjectName("card-copy")
        action_body.setWordWrap(True)
        action_layout.addWidget(action_body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._topgrade_btn = QPushButton("Full Update")
        self._topgrade_btn.setObjectName("primary")
        self._topgrade_btn.setToolTip("Updates the OS image, Flatpaks, and all topgrade-managed tools in one pass")
        self._topgrade_btn.clicked.connect(self._run_topgrade)
        btn_row.addWidget(self._topgrade_btn)

        self._os_btn = QPushButton("OS Image Only")
        self._os_btn.setToolTip("Downloads the next KythOS system image only (bootc upgrade)")
        self._os_btn.clicked.connect(self._run_bootc_upgrade)
        btn_row.addWidget(self._os_btn)

        self._rollback_btn = QPushButton("Roll Back")
        self._rollback_btn.setToolTip("Stage the previous deployment for your next boot")
        self._rollback_btn.clicked.connect(self._run_rollback)
        btn_row.addWidget(self._rollback_btn)
        btn_row.addStretch()
        action_layout.addLayout(btn_row)
        self._add(action_card)

        # Status + activity
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("subheading")
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

        cancel_row = QHBoxLayout()
        cancel_row.setSpacing(10)
        self._cancel_btn = QPushButton("Cancel Update")
        self._cancel_btn.setToolTip("Stop the running update while it is still safe to cancel")
        self._cancel_btn.clicked.connect(self._cancel_operation)
        self._cancel_btn.hide()
        cancel_row.addWidget(self._cancel_btn)
        self._cancel_note = QLabel("")
        self._cancel_note.setObjectName("card-copy")
        self._cancel_note.setWordWrap(True)
        self._cancel_note.hide()
        cancel_row.addWidget(self._cancel_note, 1)
        cancel_row.addStretch()
        self._add_layout(cancel_row)

        self._log_toggle = QPushButton("Show details")
        self._log_toggle.setCheckable(True)
        self._log_toggle.setToolTip("Show or hide the update log output")
        self._log_toggle.clicked.connect(lambda checked: self._set_log_expanded(checked))
        self._log_toggle.hide()
        self._add(self._log_toggle)

        self._log = QTextEdit()
        # A chatty bootc pull can emit tens of thousands of lines; unbounded
        # QTextEdit appends get slower and eat memory as the document grows.
        self._log.document().setMaximumBlockCount(5000)
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(200)
        self._log.hide()
        self._add(self._log)

        self._reboot_btn = QPushButton("Reboot to Apply")
        self._reboot_btn.setObjectName("primary")
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(lambda: subprocess.Popen(["systemctl", "reboot"]))
        self._add(self._reboot_btn)

        # ── Firmware updates ──────────────────────────────────────────────────
        fw_card, fw_layout = _make_card()
        fw_header = QHBoxLayout()
        fw_header.setSpacing(12)
        self._fw_icon = QLabel("↻")
        self._fw_icon.setStyleSheet("font-size: 22px; color: #555555;")
        self._fw_icon.setFixedWidth(32)
        fw_text_col = QVBoxLayout()
        fw_text_col.setSpacing(2)
        fw_title = QLabel("Firmware updates")
        fw_title.setObjectName("card-title")
        self._fw_status_lbl = QLabel("Checking for firmware updates…")
        self._fw_status_lbl.setObjectName("card-copy")
        self._fw_status_lbl.setWordWrap(True)
        fw_text_col.addWidget(fw_title)
        fw_text_col.addWidget(self._fw_status_lbl)
        self._fw_btn = QPushButton("Update Firmware")
        self._fw_btn.setObjectName("primary")
        self._fw_btn.setMinimumWidth(150)
        self._fw_btn.hide()
        self._fw_btn.clicked.connect(self._run_firmware_update)
        fw_btn_col = QVBoxLayout()
        fw_btn_col.addWidget(self._fw_btn)
        fw_btn_col.addStretch()
        fw_header.addLayout(fw_text_col, 1)
        fw_header.addLayout(fw_btn_col)
        fw_layout.addLayout(fw_header)
        self._fw_check_worker = None
        self._add(fw_card)

        # ── Automatic update schedule ─────────────────────────────────────────
        auto_card, auto_layout = _make_card()
        auto_title = QLabel("Automatic updates")
        auto_title.setObjectName("card-title")
        auto_layout.addWidget(auto_title)
        auto_status_row = QHBoxLayout()
        auto_status_row.setSpacing(24)

        auto_state_col = QVBoxLayout()
        auto_state_col.setSpacing(8)

        def _au_row(label: str) -> tuple[QHBoxLayout, QLabel]:
            row = QHBoxLayout()
            row.setSpacing(8)
            k = QLabel(label)
            k.setObjectName("prop-key")
            k.setMinimumWidth(96)
            row.addWidget(k)
            v = QLabel("—")
            v.setObjectName("prop-val")
            row.addWidget(v, 1)
            return row, v

        last_row, self._au_last_lbl      = _au_row("Last check:")
        result_row, self._au_result_lbl  = _au_row("Result:")
        reason_row, self._au_reason_lbl  = _au_row("Reason:")
        flatpak_row, self._au_flatpak_lbl = _au_row("Flatpak:")
        for row in (last_row, result_row, reason_row, flatpak_row):
            auto_state_col.addLayout(row)
        auto_status_row.addLayout(auto_state_col, 1)

        auto_ctrl_col = QVBoxLayout()
        auto_ctrl_col.setSpacing(8)
        auto_ctrl_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._au_enable_toggle = QCheckBox("Enabled")
        self._au_enable_toggle.setObjectName("card-copy")
        self._au_enable_toggle.stateChanged.connect(self._toggle_auto_update)
        auto_ctrl_col.addWidget(self._au_enable_toggle)
        au_trigger_btn = QPushButton("Check Now")
        au_trigger_btn.setToolTip("Manually trigger the update watcher (requires authentication)")
        au_trigger_btn.clicked.connect(self._run_auto_update_now)
        auto_ctrl_col.addWidget(au_trigger_btn)
        auto_status_row.addLayout(auto_ctrl_col)

        auto_layout.addLayout(auto_status_row)
        self._add(auto_card)
        QTimer.singleShot(300, self._refresh_auto_update_status)

        self._stretch()

        self._refresh_summary()

    def _set_buttons_enabled(self, enabled: bool):
        self._topgrade_btn.setEnabled(enabled)
        self._os_btn.setEnabled(enabled)
        self._fw_btn.setEnabled(enabled)
        rollback_ok = enabled and _has_rollback_deployment()
        self._rollback_btn.setEnabled(rollback_ok)

    def _set_log_expanded(self, expanded: bool):
        _set_log_panel(self._log_toggle, self._log, expanded)

    def _set_phase(self, phase: str):
        self._current_phase = phase
        self._status_lbl.setText(phase)
        _restyle(self._status_lbl)

    def _start_operation(self, mode: str, label: str, cmd: list[str], inhibit_reason: str):
        self._stop_dl_monitor()
        self._dl_total = 0
        self._dl_downloaded = 0
        self._dl_speed = 0
        self._dl_eta = 0
        self._dl_final_bytes = 0
        self._dl_low_speed_ticks = 0
        self._staging_write_start = 0
        self._mode = mode
        self._last_output_ts = time.monotonic()
        self._op_start_ts = time.monotonic()
        self._current_phase = ""
        self._cancel_blocked = False
        self._cancel_block_reason = ""
        self._log.clear()
        self._log_toggle.show()
        self._set_log_expanded(False)
        self._progress.setRange(0, 0)
        self._progress.show()
        self._status_lbl.setText(label)
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        _restyle(self._status_lbl)
        self._reboot_btn.hide()
        self._cancel_btn.setText("Cancel Update")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.show()
        self._cancel_note.setText("You can cancel while KythOS is checking or downloading. Once the image is being written, the safest path is to let it finish.")
        self._cancel_note.show()
        self._set_buttons_enabled(False)

        self._worker = Worker(_with_idle_inhibit(cmd, inhibit_reason))
        _set_session_inhibit(self, inhibit_reason)
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_done)
        self._worker.start()
        self._update_activity()
        self._update_cancel_state()
        if mode != "rollback":
            self._heartbeat.start()

    def _phase_blocks_cancel(self, phase: str) -> str:
        return _bootc_cancel_block_reason(self._mode, phase)

    def _update_cancel_state(self):
        if self._worker is None:
            self._cancel_btn.hide()
            self._cancel_note.hide()
            return
        reason = self._phase_blocks_cancel(self._current_phase)
        if reason:
            self._cancel_blocked = True
            self._cancel_block_reason = reason
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setToolTip(reason)
            self._cancel_note.setText(reason)
        elif not self._cancel_blocked:
            self._cancel_btn.setEnabled(True)
            self._cancel_btn.setToolTip("Stop the running update while it is still safe to cancel")

    def _cancel_operation(self):
        if self._worker is None:
            return
        self._update_cancel_state()
        if self._cancel_blocked:
            self._log.append(f"\nCancel unavailable: {self._cancel_block_reason}")
            self._log.ensureCursorVisible()
            return
        reply = QMessageBox.question(
            self,
            "Cancel Update?",
            "Stop the running update now? Anything already downloaded can usually be reused later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._worker is None:
            return
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("Cancelling…")
        self._cancel_note.setText("Cancel requested. Waiting for the update process to stop cleanly…")
        self._status_lbl.setText("Cancelling update…")
        self._log.append("\nCancel requested by user. Waiting for the update process to stop…")
        self._log.ensureCursorVisible()
        self._worker.cancel()

    def _run_topgrade(self):
        self._start_operation(
            "topgrade",
            "Running full system update via topgrade…",
            ["topgrade", "--yes", "--no-retry"],
            "KythOS is running a full system update",
        )

    def _run_bootc_upgrade(self):
        self._start_operation(
            "update",
            "Downloading the next KythOS OS image…",
            ["sudo", "bootc", "upgrade"],
            "KythOS is downloading a system update",
        )

    def _run_rollback(self):
        self._start_operation(
            "rollback",
            "Staging the previous deployment for next boot…",
            ["sudo", "bootc", "rollback"],
            "KythOS is staging a system rollback",
        )

    def _on_line(self, text: str):
        self._last_output_ts = time.monotonic()
        phase = _parse_update_phase(text.strip(), self._mode)
        if phase:
            self._set_phase(phase)
            self._update_cancel_state()
            if phase != "Downloading image layers…" and self._dl_downloaded >= self._dl_total > 0:
                self._progress.setRange(0, 0)
        # Start or update network monitor when bootc tells us how much to download
        if "layers needed:" in text:
            try:
                m = text.split("layers needed:")[1]
                size_str = m.split("(")[1].rstrip(")") if "(" in m else ""
                total = _parse_size_bytes(size_str)
                if total > 0:
                    if self._dl_monitor is None:
                        self._dl_total = total
                        self._progress.setRange(0, 1000)
                        self._dl_monitor = DownloadMonitor(total, _get_rx_bytes())
                        self._dl_monitor.stats.connect(self._on_dl_stats)
                        self._dl_monitor.start()
                    elif total > self._dl_total:
                        # A later phase reports a larger download — update in place
                        self._dl_total = total
                        self._dl_monitor._total = total
                        self._progress.setRange(0, 1000)
            except Exception:
                pass
        self._log.append(text)
        self._log.ensureCursorVisible()

    def _stop_dl_monitor(self):
        if self._dl_monitor is not None:
            self._dl_monitor.stop()
            self._dl_monitor.wait()
            self._dl_monitor.deleteLater()
            self._dl_monitor = None

    def _on_dl_stats(self, downloaded: int, total: int, speed_bps: int, eta_sec: int):
        self._dl_downloaded = downloaded
        self._dl_speed = speed_bps
        self._dl_eta = eta_sec
        if total > 0:
            self._progress.setValue(int(min(downloaded / total, 1.0) * 1000))

        def _finish_download(phase: str):
            self._dl_final_bytes = downloaded
            self._progress.setRange(0, 0)
            self._set_phase(phase)
            self._update_cancel_state()
            self._update_activity()
            self._stop_dl_monitor()

        # Track consecutive near-zero-speed ticks.
        # Only declare the download done when speed has been near-zero for at
        # least 10 seconds AND the skopeo image-proxy process has exited —
        # skopeo stays alive for the entire pull, so if it's still running the
        # download is definitely still in progress regardless of what the
        # network byte counter says.  The byte-count 99.5% heuristic is removed
        # entirely: /proc/net/dev counts all interface traffic (not just bootc)
        # and the total is an estimate, making it too unreliable to use alone.
        if speed_bps <= 100_000:
            self._dl_low_speed_ticks += 1
        else:
            self._dl_low_speed_ticks = 0

        if self._dl_low_speed_ticks >= 10 and downloaded > 0 and not _bootc_proxy_running():
            _finish_download("Download complete — processing image layers…")
            return

        # While actively transferring: update phase label and show live stats
        if speed_bps > 100_000 and downloaded < total:
            self._set_phase("Downloading image layers…")
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
        if not _active_bootc_operation() and self._worker is None:
            self._activity_lbl.hide()
            return
        # Don't clobber live download stats the dl monitor just wrote
        if self._dl_monitor is not None and self._dl_speed > 100_000:
            return
        elapsed = int(time.monotonic() - self._op_start_ts) if self._op_start_ts else 0
        mins, secs = divmod(elapsed, 60)
        elapsed_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        parts: list[str] = []
        if self._dl_final_bytes > 0:
            parts.append(f"{_human_bytes(self._dl_final_bytes)} downloaded")
        parts.append(f"{elapsed_str} elapsed")
        self._activity_lbl.setText("  ·  ".join(parts))
        self._activity_lbl.show()

    def _heartbeat_tick(self):
        if self._worker is None or self._mode not in ("topgrade", "update"):
            self._heartbeat.stop()
            self._update_activity()
            return
        # Fallback: if output has been silent for 10+ seconds and we're still
        # showing the download phase, the download finished without triggering
        # the dl monitor's low-speed transition (e.g. no "layers needed:" line).
        if (self._current_phase == "Downloading image layers…"
                and self._dl_monitor is None
                and self._last_output_ts
                and time.monotonic() - self._last_output_ts > 10):
            self._set_phase("Processing image layers…")
        # During the post-download staging phase, bootc/ostree commit layers to
        # disk without emitting any output. Inject a heartbeat line every tick so
        # the log doesn't look frozen while ostree is writing gigabytes to disk.
        silent_secs = (time.monotonic() - self._last_output_ts) if self._last_output_ts else 0
        if (self._dl_monitor is None
                and self._dl_final_bytes > 0
                and silent_secs >= 5
                and self._worker is not None):
            if self._staging_write_start == 0:
                self._staging_write_start = _get_disk_write_bytes()
            written = max(0, _get_disk_write_bytes() - self._staging_write_start)
            elapsed = int(time.monotonic() - self._op_start_ts) if self._op_start_ts else 0
            mins, secs_part = divmod(elapsed, 60)
            elapsed_str = f"{mins}m {secs_part:02d}s" if mins else f"{secs_part}s"
            if written >= 1024 * 1024:
                msg = f"  [staging] writing image to disk… {_human_bytes(written)} written · {elapsed_str} elapsed"
            else:
                msg = f"  [staging] committing image to repository… {elapsed_str} elapsed"
            self._log.append(msg)
            self._log.ensureCursorVisible()
        self._update_activity()

    def _on_done(self, code: int):
        self._heartbeat.stop()
        self._stop_dl_monitor()
        self._progress.hide()
        self._cancel_btn.hide()
        self._cancel_note.hide()
        _finish_worker(self)
        _set_session_inhibit(self, None)
        self._update_activity()
        self._set_buttons_enabled(True)

        if code == Worker.CANCELLED:
            self._status_lbl.setText("Update cancelled. The running operation was stopped.")
            self._status_lbl.setObjectName("status-warn")
            self._log.append("\nCancelled. You can start the update again when ready.")
            self._check_for_update()
        elif code == 0:
            if self._mode == "firmware":
                self._status_lbl.setText("Firmware updates queued — reboot to flash.")
                self._status_lbl.setObjectName("status-ok")
                self._log.append("\nDone. Firmware will be applied during the next reboot (EFI capsule).")
                self._reboot_btn.show()
                self._fw_btn.hide()
                self._fw_status_lbl.setText("Firmware update queued — reboot to apply.")
                self._fw_icon.setText("✓")
                self._fw_icon.setStyleSheet("font-size: 22px; color: #4fc1ff;")
                return
            if self._mode == "rollback":
                self._status_lbl.setText("Rollback staged — restart to return to the previous system.")
                self._status_lbl.setObjectName("status-warn")
                self._log.append("\nDone. Restart to switch to the previous deployment.")
                self._reboot_btn.show()
                self._check_for_update()
            elif self._mode == "switch":
                self._status_lbl.setText("Branch staged — restart to apply the new channel.")
                self._status_lbl.setObjectName("status-ok")
                self._log.append("\nDone. Restart to boot into the new branch.")
                self._reboot_btn.show()
                self._check_for_update()
            elif _has_staged_update():
                self._status_lbl.setText("Update staged — restart when you're ready to apply it.")
                self._status_lbl.setObjectName("status-ok")
                self._log.append("\nDone. Your next system image is staged and waiting for restart.")
                self._reboot_btn.show()
                self._check_for_update()
            elif self._mode == "topgrade":
                self._status_lbl.setText("Update complete — everything is up to date.")
                self._status_lbl.setObjectName("status-ok")
                self._log.append("\nDone. All managed tools and apps are up to date.")
                self._check_for_update()
            else:
                self._status_lbl.setText("Already on the latest deployment — no image update was staged.")
                self._status_lbl.setObjectName("status-ok")
                self._log.append("\nNo OS image update was staged. System is current.")
                self._check_for_update()
        else:
            label = {
                "topgrade": "topgrade", "update": "bootc upgrade",
                "rollback": "bootc rollback", "switch": "bootc switch",
                "firmware": "fwupdmgr upgrade",
            }.get(self._mode, "operation")
            self._status_lbl.setText(f"{label} failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")

        _restyle(self._status_lbl)
        self._refresh_summary()

    def _refresh_summary(self):
        tag = _current_branch()
        branch = _branch_display_name(tag)
        booted_ts = _bootc_image_timestamp("booted")

        # Running row
        running_text = branch
        if booted_ts:
            running_text += f"  ·  built {booted_ts}"
        self._booted_val.setText(running_text)

        if self._worker is not None:
            self._staged_val.setText("Update in progress…")
            self._staged_val.setStyleSheet("")
            self._rollback_val.setText("—")
            self._rollback_btn.setEnabled(False)
            self._rollback_btn.setText("Roll Back")
            self._reboot_btn.hide()
            return

        staged = _has_staged_update()
        rollback = _has_rollback_deployment()
        staged_ts = _bootc_image_timestamp("staged") if staged else None
        rollback_ts = _bootc_image_timestamp("rollback") if rollback else None

        # Staged row
        if staged:
            staged_text = f"built {staged_ts}  —  reboot to apply" if staged_ts else "Ready — reboot to apply"
            self._staged_val.setText(staged_text)
            self._staged_val.setStyleSheet("color: #5b9cf6;")
        else:
            self._staged_val.setText("None")
            self._staged_val.setStyleSheet("color: #888888;")

        # Rollback row + button label
        if rollback:
            rb_text = f"Available  ·  built {rollback_ts}" if rollback_ts else "Available"
            self._rollback_val.setText(rb_text)
            self._rollback_val.setStyleSheet("")
            self._rollback_btn.setText(f"Roll Back  ({rollback_ts})" if rollback_ts else "Roll Back")
        else:
            self._rollback_val.setText("None")
            self._rollback_val.setStyleSheet("color: #888888;")
            self._rollback_btn.setText("Roll Back")

        self._rollback_btn.setEnabled(rollback and self._worker is None)

        if staged:
            self._reboot_btn.show()
        else:
            self._reboot_btn.hide()

    def showEvent(self, event):
        super().showEvent(event)
        if self._check_state == "idle":
            self._check_for_update()
        self._check_firmware()

    def _check_for_update(self):
        if (self._check_worker and self._check_worker.isRunning()) or (self._flatpak_check_worker and self._flatpak_check_worker.isRunning()):
            return
        self._check_state = "checking"
        self._check_btn.setEnabled(False)
        self._avail_card.setObjectName("card")
        _restyle(self._avail_card)
        self._avail_icon.setText("○")
        self._avail_icon.setStyleSheet("font-size: 28px; color: #555555;")
        self._avail_title.setText("Checking for updates…")
        self._avail_lbl.setText("")
        self._update_now_btn.hide()
        self._restart_now_btn.hide()

        self._system_checked = False
        self._flatpak_checked = False
        self._flatpak_count = 0
        self._remote_manifest = ""

        # Start system update check
        self._check_worker = UpdateCheckWorker()
        self._check_worker.result.connect(self._on_system_check_result)
        _release_worker_when_finished(self, "_check_worker", self._check_worker)
        self._check_worker.start()

        # Start flatpak update check
        self._flatpak_check_worker = FlatpakCheckWorker()
        self._flatpak_check_worker.result.connect(self._on_flatpak_check_result)
        _release_worker_when_finished(self, "_flatpak_check_worker", self._flatpak_check_worker)
        self._flatpak_check_worker.start()

    def _on_system_check_result(self, state: str, remote_ts: str, manifest_raw: str):
        self._system_checked = True
        self._check_state = state
        self._check_ts = datetime.now().strftime("%H:%M")
        self._check_ts_details = remote_ts
        self._remote_manifest = manifest_raw
        self._update_ui_after_check()

    def _on_flatpak_check_result(self, count: int):
        self._flatpak_checked = True
        self._flatpak_count = count
        self._update_ui_after_check()

    def _update_ui_after_check(self):
        if not self._system_checked or not self._flatpak_checked:
            return

        self._check_btn.setEnabled(True)
        ts_hint = f"  ·  Checked at {self._check_ts}"
        built = f"  ·  built {self._check_ts_details}" if self._check_ts_details else ""

        staged = _has_staged_update()
        flatpak_count = self._flatpak_count

        # Update the automatic updates status card locally with the fresh counts
        self._au_last_lbl.setText(self._check_ts)
        if flatpak_count > 0:
            noun = "update" if flatpak_count == 1 else "updates"
            self._au_flatpak_lbl.setText(f"{flatpak_count} {noun} pending")
            self._au_flatpak_lbl.setStyleSheet("color: #ffa726;")
        else:
            self._au_flatpak_lbl.setText("Up to date")
            self._au_flatpak_lbl.setStyleSheet("color: #4caf50;")

        if staged:
            self._avail_card.setObjectName("card-accent-ok")
            _restyle(self._avail_card)
            self._avail_icon.setText("↻")
            self._avail_icon.setStyleSheet("font-size: 28px; color: #4fc1ff;")
            self._avail_title.setText("Restart required")
            staged_ts = _bootc_image_timestamp("staged")
            built_staged = f"  ·  built {staged_ts}" if staged_ts else ""
            
            flatpak_part = ""
            if flatpak_count > 0:
                noun = "update" if flatpak_count == 1 else "updates"
                flatpak_part = f" Additionally, {flatpak_count} Flatpak {noun} can be installed."

            self._avail_lbl.setText(
                f"A new image is staged and waiting{built_staged}.{flatpak_part} "
                f"Restart now or later — your current system stays available as a fallback.{ts_hint}"
            )
            self._restart_now_btn.show()
            self._update_now_btn.hide()
        elif self._check_state == "available":
            self._avail_card.setObjectName("card-accent-warn")
            _restyle(self._avail_card)
            self._avail_icon.setText("↓")
            self._avail_icon.setStyleSheet("font-size: 28px; color: #d4a843;")
            self._avail_title.setText("Update available")
            
            flatpak_part = ""
            if flatpak_count > 0:
                noun = "update" if flatpak_count == 1 else "updates"
                flatpak_part = f" and {flatpak_count} Flatpak {noun} are pending"

            self._avail_lbl.setText(
                f"A new system image is ready{built}{flatpak_part}. "
                f"Run a full update to download and install them.{ts_hint}"
            )
            self._update_now_btn.show()
            self._restart_now_btn.hide()
        elif flatpak_count > 0:
            self._avail_card.setObjectName("card-accent-warn")
            _restyle(self._avail_card)
            self._avail_icon.setText("↓")
            self._avail_icon.setStyleSheet("font-size: 28px; color: #d4a843;")
            self._avail_title.setText("App updates available")
            noun = "update is" if flatpak_count == 1 else "updates are"
            self._avail_lbl.setText(
                f"Your system OS is up to date, but {flatpak_count} Flatpak app {noun} available. "
                f"Run a full update to install them.{ts_hint}"
            )
            self._update_now_btn.show()
            self._restart_now_btn.hide()
        elif self._check_state == "uptodate":
            self._avail_card.setObjectName("card-accent-ok")
            _restyle(self._avail_card)
            self._avail_icon.setText("✓")
            self._avail_icon.setStyleSheet("font-size: 28px; color: #4caf50;")
            self._avail_title.setText("Up to date")
            self._avail_lbl.setText(f"Running the latest image{built}.{ts_hint}")
            self._update_now_btn.hide()
            self._restart_now_btn.hide()
        else:
            self._avail_card.setObjectName("card")
            _restyle(self._avail_card)
            self._avail_icon.setText("⚠")
            self._avail_icon.setStyleSheet("font-size: 28px; color: #888888;")
            self._avail_title.setText("Check unavailable")
            self._avail_lbl.setText(
                f"Could not reach the update server — check your network connection.{ts_hint}"
            )
            self._update_now_btn.hide()
            self._restart_now_btn.hide()

    def _refresh_auto_update_status(self) -> None:
        status = {}
        try:
            with open("/var/lib/kyth/update-watcher-status.json") as f:
                status = json.load(f)
        except Exception:
            pass

        ts = status.get("ts", 0)
        if ts:
            try:
                ts_str = datetime.fromtimestamp(ts).strftime("%b %d %H:%M")
            except Exception:
                ts_str = str(ts)
        else:
            ts_str = "Never"
        self._au_last_lbl.setText(ts_str)

        result = status.get("result", "")
        _colors = {"upgraded": "#4caf50", "no_change": "#b0bccf", "skipped": "#ffa726", "error": "#ef5350"}
        self._au_result_lbl.setText(result.replace("_", " ").title() if result else "—")
        self._au_result_lbl.setStyleSheet(f"color: {_colors.get(result, '#b0bccf')};")
        self._au_reason_lbl.setText(status.get("reason") or "—")

        flatpak_count = status.get("flatpak_updates", 0)
        if flatpak_count > 0:
            noun = "update" if flatpak_count == 1 else "updates"
            self._au_flatpak_lbl.setText(f"{flatpak_count} {noun} pending")
            self._au_flatpak_lbl.setStyleSheet("color: #ffa726;")
        else:
            self._au_flatpak_lbl.setText("Up to date")
            self._au_flatpak_lbl.setStyleSheet("color: #4caf50;")

from .services.dbus_utils import is_systemd_unit_enabled

        # Reflect timer enabled state
        enabled = is_systemd_unit_enabled("kyth-update-watcher.timer")
        self._au_enable_toggle.blockSignals(True)
        self._au_enable_toggle.setChecked(enabled)
        self._au_enable_toggle.blockSignals(False)

    def _toggle_auto_update(self, state: int) -> None:
        cmd = "enable" if state else "disable"
        try:
            subprocess.Popen(
                ["pkexec", "systemctl", cmd, "--now", "kyth-update-watcher.timer"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _run_auto_update_now(self) -> None:
        try:
            subprocess.Popen(
                ["pkexec", "systemctl", "start", "kyth-update-watcher.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # ── Firmware update ───────────────────────────────────────────────────────

    def _check_firmware(self) -> None:
        if self._fw_check_worker is not None and self._fw_check_worker.isRunning():
            return
        if self._worker is not None:
            return
        self._fw_icon.setText("↻")
        self._fw_icon.setStyleSheet("font-size: 22px; color: #555555;")
        self._fw_status_lbl.setText("Checking for firmware updates…")
        self._fw_btn.hide()
        self._fw_check_worker = FirmwareCheckWorker()
        self._fw_check_worker.result.connect(self._on_firmware_check_result)
        _release_worker_when_finished(self, "_fw_check_worker", self._fw_check_worker)
        self._fw_check_worker.start()

    def _on_firmware_check_result(self, count: int, summary: str) -> None:
        if count < 0:
            self._fw_icon.setText("—")
            self._fw_icon.setStyleSheet("font-size: 22px; color: #555555;")
            self._fw_status_lbl.setText("fwupd not available.")
            self._fw_btn.hide()
        elif count == 0:
            self._fw_icon.setText("✓")
            self._fw_icon.setStyleSheet("font-size: 22px; color: #4caf50;")
            self._fw_status_lbl.setText("Firmware up to date.")
            self._fw_btn.hide()
        else:
            noun = "update" if count == 1 else "updates"
            self._fw_icon.setText("↓")
            self._fw_icon.setStyleSheet("font-size: 22px; color: #d4a843;")
            self._fw_status_lbl.setText(
                f"{count} firmware {noun} available. "
                "Updates download now and are flashed during the next reboot."
            )
            if self._worker is None:
                self._fw_btn.show()

    def _run_firmware_update(self) -> None:
        self._start_operation(
            "firmware",
            "Updating firmware…",
            ["fwupdmgr", "upgrade", "--no-reboot-check"],
            "Firmware Update",
        )
