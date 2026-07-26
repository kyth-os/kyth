# __KYTH_GENERATED_IMPORTS__
from .core_base import _release_worker_when_finished
from .services.workers.updates import FirmwareCheckWorker
from .services.updates import UpdateProbeResult
from .qt import QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from .widgets import _make_card


class _FirmwareUpdateMixin:
    """Firmware update checks and fwupdmgr upgrades (EFI capsule updates)."""

    def _build_firmware_card(self):
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

    def _on_firmware_check_result(self, result: UpdateProbeResult) -> None:
        if result.state == "error":
            self._fw_icon.setText("—")
            self._fw_icon.setStyleSheet("font-size: 22px; color: #555555;")
            self._fw_status_lbl.setText(result.detail or "Firmware check unavailable.")
            self._fw_btn.hide()
        elif int(result.value) == 0:
            self._fw_icon.setText("✓")
            self._fw_icon.setStyleSheet("font-size: 22px; color: #4caf50;")
            self._fw_status_lbl.setText("Firmware up to date.")
            self._fw_btn.hide()
        else:
            count = int(result.value)
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
