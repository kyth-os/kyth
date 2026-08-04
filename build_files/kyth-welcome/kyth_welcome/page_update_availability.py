from datetime import datetime

# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.bootc import bootc_image_timestamp, has_staged_update, update_availability_view
from .services.runtime import release_worker_when_finished
from .services.launch import reboot
from .services.updates import AvailabilityCheckResult, UpdateProbeResult
from .services.workers.updates import FlatpakCheckWorker, UpdateCheckWorker
from .qt import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, Qt
from .widgets import _make_card


class _UpdateAvailabilityMixin:
    """Checks for a staged/available system image and pending Flatpak updates,
    and drives the "Update availability" hero card."""

    def _build_availability_card(self):
        avail_card, avail_layout = _make_card()
        avail_layout.setSpacing(0)

        avail_hero = QHBoxLayout()
        avail_hero.setSpacing(16)
        avail_hero.setContentsMargins(0, 0, 0, 0)

        self._avail_icon = QLabel("○")
        self._avail_icon.setFixedWidth(40)
        self._avail_icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self._avail_icon.setObjectName("avail-icon-dim")
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
        self._update_now_btn.clicked.connect(self._run_full_update)
        avail_btn_col.addWidget(self._update_now_btn)
        self._restart_now_btn = QPushButton("Restart Now")
        self._restart_now_btn.setObjectName("primary")
        self._restart_now_btn.setMinimumWidth(120)
        self._restart_now_btn.hide()
        self._restart_now_btn.clicked.connect(reboot)
        avail_btn_col.addWidget(self._restart_now_btn)
        self._check_btn = QPushButton("Check Now")
        self._check_btn.setEnabled(False)
        self._check_btn.setMinimumWidth(120)
        self._check_btn.clicked.connect(lambda: self._check_for_update(force_refresh=True))
        avail_btn_col.addWidget(self._check_btn)
        avail_hero.addLayout(avail_btn_col)

        avail_layout.addLayout(avail_hero)
        self._avail_card = avail_card
        self._add(self._avail_card)

    def _check_for_update(self, *, force_refresh: bool = False):
        if (self._check_worker and self._check_worker.isRunning()) or (self._flatpak_check_worker and self._flatpak_check_worker.isRunning()):
            return
        self._check_state = "checking"
        self._check_btn.setEnabled(False)
        self._avail_card.setObjectName("card")
        restyle(self._avail_card)
        self._avail_icon.setText("○")
        self._avail_icon.setObjectName("avail-icon-dim")
        restyle(self._avail_icon)
        self._avail_title.setText("Checking for updates…")
        self._avail_lbl.setText("")
        self._update_now_btn.hide()
        self._restart_now_btn.hide()

        self._check_coordinator.begin()
        self._flatpak_count = 0
        self._remote_manifest = ""

        # Start system update check
        self._check_worker = UpdateCheckWorker(use_cached_snapshot=not force_refresh)
        self._check_worker.result.connect(self._on_system_check_result)
        release_worker_when_finished(self, "_check_worker", self._check_worker)
        self._check_worker.start()

        # Start flatpak update check
        self._flatpak_check_worker = FlatpakCheckWorker()
        self._flatpak_check_worker.result.connect(self._on_flatpak_check_result)
        release_worker_when_finished(self, "_flatpak_check_worker", self._flatpak_check_worker)
        self._flatpak_check_worker.start()

    def _on_system_check_result(self, result: UpdateProbeResult):
        self._accept_update_probe(result)

    def _on_flatpak_check_result(self, result: UpdateProbeResult):
        self._accept_update_probe(result)

    def _accept_update_probe(self, result: UpdateProbeResult):
        completed = self._check_coordinator.accept(result)
        if completed is None:
            return
        self._finish_availability_check(completed)

    def _finish_availability_check(self, completed: AvailabilityCheckResult):
        self._check_state = completed.system_state
        self._check_ts = datetime.now().strftime("%H:%M")
        self._check_ts_details = completed.system_detail
        self._remote_manifest = completed.manifest_raw
        self._flatpak_count = completed.flatpak_count
        self._check_btn.setEnabled(True)
        flatpak_count = self._flatpak_count
        staged = has_staged_update()

        # Update the automatic updates status card locally with the fresh counts
        self._au_last_lbl.setText(self._check_ts)
        if flatpak_count > 0:
            noun = "update" if flatpak_count == 1 else "updates"
            self._au_flatpak_lbl.setText(f"{flatpak_count} {noun} pending")
            self._au_flatpak_lbl.setObjectName("prop-val-orange")
        else:
            self._au_flatpak_lbl.setText("Up to date")
            self._au_flatpak_lbl.setObjectName("prop-val-green")
        restyle(self._au_flatpak_lbl)

        view = update_availability_view(
            staged=staged,
            check_state=self._check_state,
            flatpak_count=flatpak_count,
            check_ts=self._check_ts,
            check_ts_details=self._check_ts_details,
            staged_ts=bootc_image_timestamp("staged") if staged else None,
        )
        self._avail_card.setObjectName(view.card_style)
        restyle(self._avail_card)
        self._avail_icon.setText(view.icon_text)
        self._avail_icon.setObjectName(view.icon_style)
        restyle(self._avail_icon)
        self._avail_title.setText(view.title)
        self._avail_lbl.setText(view.body)
        self._update_now_btn.setVisible(view.update_btn_visible)
        self._restart_now_btn.setVisible(view.restart_btn_visible)
