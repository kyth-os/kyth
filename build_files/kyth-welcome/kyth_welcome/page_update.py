# __KYTH_GENERATED_IMPORTS__
from .qt import QTimer, single_shot
from .widgets import Page
from .page_update_auto import _AutoUpdateMixin
from .page_update_availability import _UpdateAvailabilityMixin
from .page_update_firmware import _FirmwareUpdateMixin
from .page_update_ops import _UpdateOpsMixin

# ── Page: Update ──────────────────────────────────────────────────────────────
class UpdatePage(_UpdateOpsMixin, _UpdateAvailabilityMixin, _AutoUpdateMixin, _FirmwareUpdateMixin, Page):
    """Split by concern across sibling modules: running update operations
    (page_update_ops), checking availability (page_update_availability), the
    automatic-update schedule (page_update_auto), and firmware (page_update_firmware).
    This file only owns page-wide state and build order.
    """

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

        self._build_availability_card()
        self._build_summary_card()
        self._build_manual_actions_card()
        self._build_progress_section()
        self._build_firmware_card()
        self._build_auto_update_card()
        single_shot(self, 300, self._refresh_auto_update_status)

        self._stretch()

        self._refresh_summary()

    def showEvent(self, event):
        super().showEvent(event)
        if self._check_state == "idle":
            self._check_for_update()
        self._check_firmware()
