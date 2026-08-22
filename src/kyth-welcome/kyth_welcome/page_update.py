# __KYTH_GENERATED_IMPORTS__
from .lazy_page import compose_on_first_init
from .qt import QTimer, single_shot
from .widgets import Page, _make_section_header
from .services.updates import UpdateCheckCoordinator


def _load_update_mixins() -> tuple[type, ...]:
    from .page_update_auto import _AutoUpdateMixin
    from .page_update_availability import _UpdateAvailabilityMixin
    from .page_update_firmware import _FirmwareUpdateMixin
    from .page_update_ops import _UpdateOpsMixin
    return (_UpdateOpsMixin, _UpdateAvailabilityMixin, _AutoUpdateMixin, _FirmwareUpdateMixin)


# ── Page: Update ──────────────────────────────────────────────────────────────
# Mixins load on first construction so opening System Hub does not import
# bootc/update ops modules until the user navigates here.
@compose_on_first_init(_load_update_mixins)
class UpdatePage(Page):
    """Split by concern across sibling modules: running update operations
    (page_update_ops), checking availability (page_update_availability), the
    automatic-update schedule (page_update_auto), and firmware (page_update_firmware).
    This file only owns page-wide state and build order.
    """

    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _k: None)
        self._worker = None
        self._dl_monitor = None
        self._dl_total = 0
        self._dl_downloaded = 0
        self._dl_speed = 0
        self._dl_eta = 0
        self._mode = "full-update"
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
        self._check_coordinator = UpdateCheckCoordinator()
        self._flatpak_count = 0
        self._remote_manifest = ""
        self._check_state = "idle"   # idle | checking | available | uptodate | error
        self._check_ts = ""
        self._summary_worker = None

        self._page_header(
            "System",
            "Updates",
            "Check update status, stage new images, and restart when you are ready.",
        )

        hdr, _ = _make_section_header("Status", "Unified — image + Flatpak + firmware in one Hub")
        self._add(hdr)
        self._build_unified_updates_card()
        self._build_availability_card()
        self._build_summary_card()
        hdr2, _ = _make_section_header("Actions", "Stage the next image or roll back")
        self._add(hdr2)
        self._build_manual_actions_card()
        self._build_rollback_explainer_card()
        hdr3, _ = _make_section_header("Progress", "Download and staging log")
        self._add(hdr3)
        self._build_progress_section()
        hdr4, _ = _make_section_header("Devices", "Firmware and automatic updates")
        self._add(hdr4)
        self._build_firmware_card()
        self._build_auto_update_card()
        self._build_windows_update_style_card()
        single_shot(self, 300, self._refresh_auto_update_status)

        self._stretch()

        self._refresh_summary()

    def _build_unified_updates_card(self):
        from .widgets import _make_card
        from .qt import QLabel, QHBoxLayout, QPushButton, QVBoxLayout, QFrame
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Unified updates — one Hub, no store hop")
        title.setObjectName("card-title")
        layout.addWidget(title)
        intro = QLabel("Image (bootc), Flatpak apps, and firmware (LVFS/fwupdmgr) — all checked together in System Hub. Uses cached probes (60s bootc / 30s flatpak) and skips offline checks.")
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._unified_bootc_lbl = QLabel("Image: checking…")
        self._unified_bootc_lbl.setObjectName("card-copy")
        self._unified_bootc_lbl.setWordWrap(True)
        row.addWidget(self._unified_bootc_lbl, 1)
        self._unified_flatpak_lbl = QLabel("Flatpak: checking…")
        self._unified_flatpak_lbl.setObjectName("card-copy")
        self._unified_flatpak_lbl.setWordWrap(True)
        row.addWidget(self._unified_flatpak_lbl, 1)
        self._unified_fw_lbl = QLabel("Firmware: checking…")
        self._unified_fw_lbl.setObjectName("card-copy")
        self._unified_fw_lbl.setWordWrap(True)
        row.addWidget(self._unified_fw_lbl, 1)
        layout.addLayout(row)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        check_all = QPushButton("Check all now")
        check_all.setObjectName("primary")
        check_all.setToolTip("Runs bootc + flatpak + firmware checks together (respects cache + offline skip)")
        check_all.clicked.connect(lambda _=False: (self._check_for_update(), self._check_firmware(), self._refresh_unified()))
        btn_row.addWidget(check_all)
        hub_btn = QPushButton("Open Guardian → Fix My System")
        hub_btn.clicked.connect(lambda _=False: self._navigate("Guardian"))
        btn_row.addWidget(hub_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        self._add(card)

    def _refresh_unified(self):
        try:
            from .services.updates import update_availability_view
            from .services.bootc import has_staged_update, has_rollback_deployment
            from kyth_shared.system.firmware import get_firmware_summary  # type: ignore
            # bootc
            try:
                view = update_availability_view()
                self._unified_bootc_lbl.setText(f"Image: {view.get('state','unknown')} — staged={has_staged_update()} rollback={has_rollback_deployment()}")
            except Exception as e:
                self._unified_bootc_lbl.setText(f"Image: unavailable ({e})")
            # flatpak count already in _flatpak_count
            self._unified_flatpak_lbl.setText(f"Flatpak: {getattr(self, '_flatpak_count', '?')} pending" if hasattr(self, "_flatpak_count") else "Flatpak: checking…")
            # firmware
            try:
                fw = get_firmware_summary()  # may not exist
                self._unified_fw_lbl.setText(f"Firmware: {fw}")
            except Exception:
                self._unified_fw_lbl.setText("Firmware: see Devices card below")
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        if self._check_state == "idle":
            self._check_for_update()
        self._check_firmware()
