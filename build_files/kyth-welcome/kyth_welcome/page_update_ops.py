import shutil
import time

# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle, run_worker, set_session_inhibit
from .services.process import format_dl_progress_line, format_elapsed, get_disk_write_bytes, human_bytes, with_idle_inhibit
from .services.bootc import (
    active_bootc_operation, bootc_image_digest, bootc_image_timestamp, bootc_proxy_running, branch_display_name,
    bootc_status_data, current_branch, has_rollback_deployment, has_staged_update, nested_get,
)
from .services.launch import reboot
from .services.runtime import Worker, finish_worker, start_or_extend_dl_monitor, stop_download_monitor
from .services.privileged import bootc_action
from .services.updates import (
    UpdateOperationController, full_update_operation,
    image_update_operation, rollback_operation,
)
from .qt import QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton
from .widgets import CollapsibleLogPanel, _make_card


class _UpdateOpsMixin:
    """Runs full/bootc-upgrade/rollback/firmware operations: the image status
    summary, manual-action buttons, and the shared progress/log/cancel UI that
    every operation streams into."""

    def _build_summary_card(self):
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

    def _build_manual_actions_card(self):
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

        self._full_update_btn = QPushButton("Full Update")
        self._full_update_btn.setObjectName("primary")
        self._full_update_btn.setToolTip("Updates the OS image, Flatpaks, firmware, and KythOS-managed tools")
        self._full_update_btn.clicked.connect(self._run_full_update)
        btn_row.addWidget(self._full_update_btn)

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

    def _build_rollback_explainer_card(self) -> None:
        """Complaint #5: make atomic updates + rollback obvious to Windows switchers."""
        card, layout = _make_card("card-accent-ok")
        title = QLabel("🛡️  Updates are atomic — rollback is one reboot away")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "KythOS is immutable: updates build a new system image and 'stage' it. "
            "Nothing changes until you reboot. If the new image breaks anything, reboot, "
            "hold Shift at the boot menu, and pick the previous deployment — you're back in 30 seconds. "
            "No reinstall, no lost files."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        row = QHBoxLayout()
        row.setSpacing(8)
        how_btn = QPushButton("How staging works")
        how_btn.setToolTip("Stage → Reboot → Try → Roll back if needed (previous build stays cached)")
        how_btn.clicked.connect(lambda _=False: self._check_for_update(force_refresh=True))
        row.addWidget(how_btn)
        # Roll back button already exists; just explain it here
        note = QLabel("Previous build is kept automatically — no backup step needed.")
        note.setObjectName("caption-text")
        note.setWordWrap(True)
        row.addWidget(note, 1)
        layout.addLayout(row)
        self._add(card)

    def _build_progress_section(self):
        self._operation = UpdateOperationController()
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

        # A chatty bootc pull can emit tens of thousands of lines; CollapsibleLogPanel
        # caps the document's block count so unbounded appends don't slow down or
        # balloon memory as the log grows.
        self._log_panel = CollapsibleLogPanel(min_height=200)
        self._log_panel.toggle.setToolTip("Show or hide the update log output")
        self._add(self._log_panel)

        self._reboot_btn = QPushButton("Reboot to Apply")
        self._reboot_btn.setObjectName("primary")
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(reboot)
        self._add(self._reboot_btn)

    def _set_buttons_enabled(self, enabled: bool):
        self._full_update_btn.setEnabled(enabled)
        self._os_btn.setEnabled(enabled)
        self._fw_btn.setEnabled(enabled)
        rollback_ok = enabled and has_rollback_deployment()
        self._rollback_btn.setEnabled(rollback_ok)

    def _set_phase(self, phase: str):
        self._operation.set_phase(phase)
        self._current_phase = phase
        self._status_lbl.setText(phase)
        restyle(self._status_lbl)

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
        self._operation.start(mode)
        self._last_output_ts = self._operation.last_output_at
        self._op_start_ts = self._operation.started_at
        self._current_phase = ""
        self._cancel_blocked = False
        self._cancel_block_reason = ""
        self._log_panel.reset()
        self._log_panel.toggle.show()
        self._progress.setRange(0, 0)
        self._progress.show()
        self._status_lbl.setText(label)
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        restyle(self._status_lbl)
        self._reboot_btn.hide()
        self._cancel_btn.setText("Cancel Update")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.show()
        self._cancel_note.setText("You can cancel while KythOS is checking or downloading. Once the image is being written, the safest path is to let it finish.")
        self._cancel_note.show()
        self._set_buttons_enabled(False)

        run_worker(
            self,
            with_idle_inhibit(cmd, inhibit_reason),
            session_inhibit_reason=inhibit_reason,
            on_line=self._on_line,
            on_done=self._on_done,
        )
        self._update_activity()
        self._update_cancel_state()
        if mode != "rollback":
            self._heartbeat.start()

    def _start_operation_spec(self, operation):
        self._start_operation(
            operation.mode,
            operation.label,
            list(operation.command),
            operation.inhibit_reason,
        )

    def _phase_blocks_cancel(self, phase: str) -> str:
        self._operation.set_phase(phase)
        return self._operation.cancel_block_reason

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
            self._log_panel.append(f"\nCancel unavailable: {self._cancel_block_reason}")
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
        self._log_panel.append("\nCancel requested by user. Waiting for the update process to stop…")
        self._worker.cancel()

    def _run_full_update(self):
        # Storage gate — Windows switcher filled C: then clicks Full Update and gets ENOSPC mid-pull. Block early.
        try:
            free = shutil.disk_usage("/").free
            free_gb = free / (1024**3)
            if free_gb < 10:
                QMessageBox.warning(
                    self, "Low disk space",
                    f"Only {free_gb:.1f} GB free on /. Full Update needs ~6 GB plus Flatpak/buffer — free 10 GB first (try System → Storage or remove large Flatpaks), then retry.",
                )
                return
        except Exception:
            pass
        self._start_operation_spec(full_update_operation())

    def _run_bootc_upgrade(self):
        self._start_operation_spec(
            image_update_operation(lambda: bootc_action("upgrade").command())
        )

    def _run_rollback(self):
        self._start_operation_spec(
            rollback_operation(lambda: bootc_action("rollback").command())
        )

    def _on_line(self, text: str):
        phase = self._operation.receive_line(text)
        self._last_output_ts = self._operation.last_output_at
        if phase:
            self._set_phase(phase)
            self._update_cancel_state()
            if phase != "Downloading image layers…" and self._dl_downloaded >= self._dl_total > 0:
                self._progress.setRange(0, 0)
        # Start or update network monitor when bootc tells us how much to download
        self._dl_monitor, self._dl_total, started, progress_ready = start_or_extend_dl_monitor(
            text, self._dl_monitor, self._dl_total,
        )
        if progress_ready:
            self._progress.setRange(0, 1000)
        if started:
            self._dl_monitor.stats.connect(self._on_dl_stats)
            self._dl_monitor.start()
        self._log_panel.append(text)

    def _stop_dl_monitor(self):
        stop_download_monitor(self._dl_monitor)
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

        download_state = self._operation.update_download(
            downloaded,
            total,
            speed_bps,
            eta_sec,
            proxy_running=bootc_proxy_running(),
        )
        self._dl_low_speed_ticks = self._operation.low_speed_ticks

        # Track consecutive near-zero-speed ticks.
        # Only declare the download done when speed has been near-zero for at
        # least 10 seconds AND the skopeo image-proxy process has exited —
        # skopeo stays alive for the entire pull, so if it's still running the
        # download is definitely still in progress regardless of what the
        # network byte counter says.  The byte-count 99.5% heuristic is removed
        # entirely: /proc/net/dev counts all interface traffic (not just bootc)
        # and the total is an estimate, making it too unreliable to use alone.
        if download_state == "complete":
            _finish_download("Download complete — processing image layers…")
            return

        # While actively transferring: update phase label and show live stats
        if speed_bps > 100_000 and downloaded < total:
            self._set_phase("Downloading image layers…")
        if speed_bps > 100_000:
            self._activity_lbl.setText(format_dl_progress_line(downloaded, total, speed_bps, eta_sec))
            self._activity_lbl.show()

    def _update_activity(self):
        if not active_bootc_operation() and self._worker is None:
            self._activity_lbl.hide()
            return
        # Don't clobber live download stats the dl monitor just wrote
        if self._dl_monitor is not None and self._dl_speed > 100_000:
            return
        elapsed = self._operation.elapsed()
        parts: list[str] = []
        if self._dl_final_bytes > 0:
            parts.append(f"{human_bytes(self._dl_final_bytes)} downloaded")
        parts.append(f"{format_elapsed(elapsed)} elapsed")
        self._activity_lbl.setText("  ·  ".join(parts))
        self._activity_lbl.show()

    def _heartbeat_tick(self):
        if self._worker is None or self._mode not in ("full-update", "update"):
            self._heartbeat.stop()
            self._update_activity()
            return
        # Fallback: if output has been silent for 10+ seconds and we're still
        # showing the download phase, the download finished without triggering
        # the dl monitor's low-speed transition (e.g. no "layers needed:" line).
        previous_phase = self._operation.phase
        current_phase = self._operation.heartbeat_phase()
        if (previous_phase != current_phase
                and self._dl_monitor is None
                and current_phase == "Processing image layers…"):
            self._set_phase(current_phase)
        # During the post-download staging phase, bootc/ostree commit layers to
        # disk without emitting any output. Inject a heartbeat line every tick so
        # the log doesn't look frozen while ostree is writing gigabytes to disk.
        silent_secs = (time.monotonic() - self._last_output_ts) if self._last_output_ts else 0
        if (self._dl_monitor is None
                and self._dl_final_bytes > 0
                and silent_secs >= 5
                and self._worker is not None):
            if self._staging_write_start == 0:
                self._staging_write_start = get_disk_write_bytes()
            written = max(0, get_disk_write_bytes() - self._staging_write_start)
            elapsed = self._operation.elapsed()
            elapsed_str = format_elapsed(elapsed)
            if written >= 1024 * 1024:
                msg = f"  [staging] writing image to disk… {human_bytes(written)} written · {elapsed_str} elapsed"
            else:
                msg = f"  [staging] committing image to repository… {elapsed_str} elapsed"
            self._log_panel.append(msg)
        self._update_activity()

    def _on_done(self, code: int):
        self._heartbeat.stop()
        self._stop_dl_monitor()
        self._progress.hide()
        self._cancel_btn.hide()
        self._cancel_note.hide()
        finish_worker(self)
        set_session_inhibit(self, None)
        self._update_activity()
        self._set_buttons_enabled(True)
        completion = self._operation.completion(
            code,
            staged=code == 0 and has_staged_update(),
        )

        if code == Worker.CANCELLED:
            self._status_lbl.setText(completion.message)
            self._status_lbl.setObjectName(completion.style)
            self._log_panel.append("\nCancelled. You can start the update again when ready.")
            self._check_for_update(force_refresh=True)
        elif code == 0:
            if self._mode == "firmware":
                self._status_lbl.setText("Firmware updates queued — reboot to flash.")
                self._status_lbl.setObjectName("status-ok")
                self._log_panel.append("\nDone. Firmware will be applied during the next reboot (EFI capsule).")
                self._reboot_btn.show()
                self._fw_btn.hide()
                self._fw_status_lbl.setText("Firmware update queued — reboot to apply.")
                self._fw_icon.setText("✓")
                self._fw_icon.setObjectName("fw-icon-blue")
                restyle(self._fw_icon)
                return
            if self._mode == "rollback":
                self._status_lbl.setText("Rollback staged — restart to return to the previous system.")
                self._status_lbl.setObjectName("status-warn")
                self._log_panel.append("\nDone. Restart to switch to the previous deployment.")
                self._reboot_btn.show()
                self._check_for_update(force_refresh=True)
            elif self._mode == "switch":
                self._status_lbl.setText("Branch staged — restart to apply the new channel.")
                self._status_lbl.setObjectName("status-ok")
                self._log_panel.append("\nDone. Restart to boot into the new branch.")
                self._reboot_btn.show()
                self._check_for_update(force_refresh=True)
            elif has_staged_update():
                self._status_lbl.setText("Update staged — restart when you're ready to apply it.")
                self._status_lbl.setObjectName("status-ok")
                self._log_panel.append("\nDone. Your next system image is staged and waiting for restart.")
                self._reboot_btn.show()
                self._check_for_update(force_refresh=True)
            elif self._mode == "full-update":
                self._status_lbl.setText("Update complete — everything is up to date.")
                self._status_lbl.setObjectName("status-ok")
                self._log_panel.append("\nDone. All managed tools and apps are up to date.")
                self._check_for_update(force_refresh=True)
            else:
                self._status_lbl.setText("Already on the latest deployment — no image update was staged.")
                self._status_lbl.setObjectName("status-ok")
                self._log_panel.append("\nNo OS image update was staged. System is current.")
                self._check_for_update(force_refresh=True)
        else:
            self._status_lbl.setText(completion.message)
            self._status_lbl.setObjectName(completion.style)

        restyle(self._status_lbl)
        self._refresh_summary()

    def _refresh_summary(self):
        tag = current_branch()
        branch = branch_display_name(tag)
        booted_ts = bootc_image_timestamp("booted")

        # Running row
        running_text = branch
        if booted_ts:
            running_text += f"  ·  built {booted_ts}"
        self._booted_val.setText(running_text)

        if self._worker is not None:
            self._staged_val.setText("Update in progress…")
            self._staged_val.setObjectName("prop-val")
            restyle(self._staged_val)
            self._rollback_val.setText("—")
            self._rollback_btn.setEnabled(False)
            self._rollback_btn.setText("Roll Back")
            self._reboot_btn.hide()
            return

        staged = has_staged_update()
        rollback = has_rollback_deployment()
        staged_ts = bootc_image_timestamp("staged") if staged else None
        rollback_ts = bootc_image_timestamp("rollback") if rollback else None
        # Low-disk hint in summary (also enforced in _run_full_update) — Slice 2/5 storage gate
        try:
            free_gb = shutil.disk_usage("/").free / (1024**3)
            if free_gb < 10 and not staged:
                self._staged_val.setText(f"Low disk: {free_gb:.1f} GB free — free 10 GB before Full Update")
                self._staged_val.setObjectName("prop-val-warn")
                restyle(self._staged_val)
                # keep warning visible even though staged is None
                self._staged_val.setToolTip(f"Only {free_gb:.1f} GB free on /. Full Update needs ~6 GB + buffer.")
        except Exception:
            free_gb = 999.0

        # Staged row — include pending image ref + short digest when present (5/5 visibility)
        if staged:
            data = bootc_status_data() or {}
            staged_ref = nested_get(data, ("status", "staged", "image", "image")) or nested_get(data, ("status", "staged", "image", "transport_image")) or ""
            staged_digest = bootc_image_digest("staged")
            short = f"  ·  {staged_digest[0]}" if staged_digest else ""
            ref_part = f"{staged_ref.split('@')[0]}" if staged_ref else ""
            # Keep readable: tag or repo, not full digest
            label = ref_part.split("/")[-1] if "/" in ref_part else ref_part
            if staged_ts:
                staged_text = f"{label}{short}  ·  built {staged_ts}  —  reboot to apply" if label else f"built {staged_ts}  —  reboot to apply"
            else:
                staged_text = f"{label}{short}  —  reboot to apply" if label else "Ready — reboot to apply"
            self._staged_val.setText(staged_text)
            self._staged_val.setObjectName("prop-val-blue")
        else:
            self._staged_val.setText("None")
            self._staged_val.setObjectName("prop-val-dim")
        restyle(self._staged_val)

        # Rollback row + button label — also show rollback tag
        if rollback:
            data = bootc_status_data() or {}
            rb_ref = nested_get(data, ("status", "rollback", "image", "image")) or ""
            rb_label = (rb_ref.split("@")[0].split("/")[-1] if rb_ref and "/" in rb_ref else rb_ref.split("@")[0] if rb_ref else "")
            rb_text = f"Available ({rb_label})  ·  built {rollback_ts}" if rollback_ts and rb_label else (f"Available ({rb_label})" if rb_label else (f"Available  ·  built {rollback_ts}" if rollback_ts else "Available"))
            self._rollback_val.setText(rb_text)
            self._rollback_val.setObjectName("prop-val")
            self._rollback_btn.setText(f"Roll Back  ({rollback_ts})" if rollback_ts else "Roll Back")
        else:
            self._rollback_val.setText("None")
            self._rollback_val.setObjectName("prop-val-dim")
            self._rollback_btn.setText("Roll Back")
        restyle(self._rollback_val)

        self._rollback_btn.setEnabled(rollback and self._worker is None)

        # Low-disk gate: disable Full/OS buttons when <10 GB free (also checked at click time)
        low_disk = free_gb < 10
        if low_disk and self._worker is None:
            self._full_update_btn.setEnabled(False)
            self._full_update_btn.setToolTip(f"Low disk: {free_gb:.1f} GB free — free 10 GB before updating")
            self._os_btn.setEnabled(False)
            self._os_btn.setToolTip(f"Low disk: {free_gb:.1f} GB free")
        else:
            self._full_update_btn.setEnabled(self._worker is None)
            self._full_update_btn.setToolTip("Updates the OS image, Flatpaks, firmware, and KythOS-managed tools")
            self._os_btn.setEnabled(self._worker is None)
            self._os_btn.setToolTip("Downloads the next KythOS system image only (bootc upgrade)")

        if staged:
            self._reboot_btn.show()
        else:
            self._reboot_btn.hide()
