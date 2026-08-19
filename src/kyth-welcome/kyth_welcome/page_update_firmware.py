# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.runtime import release_worker_when_finished, guard_disposed
from .services.workers.updates import FirmwareCheckWorker
from .services.updates import UpdateProbeResult
from .qt import QHBoxLayout, QLabel, QPushButton, QTimer, QVBoxLayout
from .widgets import _make_card


class _FirmwareUpdateMixin:
    """Firmware update checks and fwupdmgr upgrades (EFI capsule updates)."""

    def _build_firmware_card(self):
        fw_card, fw_layout = _make_card()
        fw_header = QHBoxLayout()
        fw_header.setSpacing(12)
        self._fw_icon = QLabel("↻")
        self._fw_icon.setObjectName("fw-icon-dim")
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

    def _check_firmware(self) -> None:
        if self._fw_check_worker is not None and self._fw_check_worker.isRunning():
            return
        if self._worker is not None:
            return
        self._fw_icon.setText("↻")
        self._fw_icon.setObjectName("fw-icon-dim")
        restyle(self._fw_icon)
        self._fw_status_lbl.setText("Checking for firmware updates…")
        self._fw_btn.hide()
        old_timer = getattr(self, "_fw_deadline_timer", None)
        if old_timer is not None:
            try:
                old_timer.stop()
                old_timer.deleteLater()
            except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
                pass
        self._fw_deadline_timer = QTimer(self)
        self._fw_deadline_timer.setSingleShot(True)
        self._fw_deadline_timer.timeout.connect(self._on_firmware_timeout)
        self._fw_deadline_timer.start(30000)
        self._fw_check_worker = FirmwareCheckWorker()
        self._fw_check_worker.result.connect(guard_disposed(self._on_firmware_check_result))
        release_worker_when_finished(self, "_fw_check_worker", self._fw_check_worker)
        self._fw_check_worker.start()

    def _on_firmware_timeout(self) -> None:
        if self._fw_check_worker is None or not self._fw_check_worker.isRunning():
            return
        self._on_firmware_check_result(UpdateProbeResult.error(
            "firmware",
            "Firmware check timed out after 30 s. fwupdmgr may be slow offline — click Refresh to retry.",
        ))

    def _on_firmware_check_result(self, result: UpdateProbeResult) -> None:
        if getattr(self, "_fw_deadline_timer", None):
            try:
                self._fw_deadline_timer.stop()
            except Exception:
                pass
        if result.state == "error":
            self._fw_icon.setText("—")
            self._fw_icon.setObjectName("fw-icon-dim")
            restyle(self._fw_icon)
            self._fw_status_lbl.setText(result.detail or "Firmware check unavailable.")
            self._fw_btn.hide()
        elif int(result.value) == 0:
            self._fw_icon.setText("✓")
            self._fw_icon.setObjectName("fw-icon-ok")
            restyle(self._fw_icon)
            self._fw_status_lbl.setText("Firmware up to date.")
            self._fw_btn.hide()
        else:
            count = int(result.value)
            noun = "update" if count == 1 else "updates"
            self._fw_icon.setText("↓")
            self._fw_icon.setObjectName("fw-icon-warn")
            restyle(self._fw_icon)
            self._fw_status_lbl.setText(
                f"{count} firmware {noun} available. "
                "Updates download now and are flashed during the next reboot."
            )
            self._fw_btn.setText(f"Update Firmware ({count})")
            self._fw_btn.setToolTip(f"Download and stage {count} firmware {noun} for next reboot (fwupdmgr upgrade)")
            if self._worker is None:
                self._fw_btn.show()

    def _run_firmware_update(self) -> None:
        # flock around /run/kyth-fwupd.lock — the same lock
        # kyth_shared.system.firmware.stage_firmware_batch() and
        # kyth-full-update take — so a user clicking this button can't launch
        # a second fwupdmgr write while kyth-update-watcher's timer is
        # mid-flash on the same device. -w 60: wait for the watcher's own
        # (usually sub-minute) run rather than silently racing it.
        self._start_operation(
            "firmware",
            "Updating firmware…",
            ["flock", "-w", "60", "/run/kyth-fwupd.lock", "fwupdmgr", "upgrade", "--no-reboot-check"],
            "Firmware Update",
        )
