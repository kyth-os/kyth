import time

# __KYTH_GENERATED_IMPORTS__
from .services.launch import reboot
from .core_base import restyle, run_worker, set_session_inhibit
from .services.process import format_dl_progress_line, format_elapsed, with_idle_inhibit
from .services.runtime import finish_worker, start_or_extend_dl_monitor, stop_download_monitor
from .services.privileged import bootc_action
from .services.bootc import REGISTRY, bootc_image_digest, bootc_image_timestamp, branch_display_name, branches_view, current_branch, image_tag_for_channel
from .qt import (
    QApplication, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QTimer, Qt,
)
from .widgets import (
    Page, _make_card, _set_log_panel,
)

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
        state_branch_lbl.setObjectName("prop-key")
        state_branch_lbl.setMinimumWidth(64)
        state_top.addWidget(state_branch_lbl)
        self._state_branch_val = QLabel()
        self._state_branch_val.setObjectName("card-copy")
        state_top.addWidget(self._state_branch_val, 1)
        state_layout.addLayout(state_top)

        state_bottom = QHBoxLayout()
        state_bottom.setSpacing(16)
        state_digest_lbl = QLabel("Digest:")
        state_digest_lbl.setObjectName("prop-key")
        state_digest_lbl.setMinimumWidth(64)
        state_bottom.addWidget(state_digest_lbl)
        self._state_digest_val = QLabel()
        self._state_digest_val.setObjectName("mono-inline")
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
        self._stable_build_lbl.setObjectName("caption-text")
        self._stable_build_lbl.hide()
        stable_layout.addWidget(self._stable_build_lbl)
        self._stable_btn = QPushButton("Switch to Stable")
        self._stable_btn.clicked.connect(lambda: self._switch(image_tag_for_channel("latest")))
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
        self._testing_build_lbl.setObjectName("caption-text")
        self._testing_build_lbl.hide()
        testing_layout.addWidget(self._testing_build_lbl)
        self._testing_btn = QPushButton("Switch to Testing")
        self._testing_btn.clicked.connect(lambda: self._switch(image_tag_for_channel("testing")))
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
        tag = current_branch()
        booted_ts = bootc_image_timestamp("booted")
        booted_digest = bootc_image_digest("booted")

        # State bar
        branch_text = branch_display_name(tag)
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
        view = branches_view(tag, booted_ts)
        self._stable_btn.setObjectName(view.stable.object_name)
        self._stable_btn.setText(view.stable.button_text)
        self._stable_build_lbl.setText(view.stable.build_label_text)
        self._stable_build_lbl.setVisible(view.stable.build_label_visible)
        self._testing_btn.setObjectName(view.testing.object_name)
        self._testing_btn.setText(view.testing.button_text)
        self._testing_build_lbl.setText(view.testing.build_label_text)
        self._testing_build_lbl.setVisible(view.testing.build_label_visible)

        restyle(self._stable_btn)
        restyle(self._testing_btn)

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
        restyle(self._status_lbl)
        self._reboot_btn.hide()
        self._stable_btn.setEnabled(False)
        self._testing_btn.setEnabled(False)

        run_worker(
            self,
            with_idle_inhibit(
                bootc_action("switch", ref).command(),
                "KythOS is switching branch",
            ),
            session_inhibit_reason="KythOS is switching the system branch",
            on_line=self._on_line,
            on_done=self._on_done,
        )
        self._update_activity()
        self._heartbeat.start()

    def _stop_dl_monitor(self):
        stop_download_monitor(self._dl_monitor)
        self._dl_monitor = None

    def _on_line(self, text: str):
        self._dl_monitor, self._dl_total, started, progress_ready = start_or_extend_dl_monitor(
            text, self._dl_monitor, self._dl_total,
        )
        if progress_ready:
            self._progress.setRange(0, 1000)
        if started:
            self._dl_monitor.stats.connect(self._on_dl_stats)
            self._dl_monitor.start()
        self._log.append(text)
        self._log.ensureCursorVisible()

    def _on_dl_stats(self, downloaded: int, total: int, speed_bps: int, eta_sec: int):
        self._dl_speed = speed_bps
        self._dl_eta = eta_sec
        if total > 0:
            self._progress.setValue(int(min(downloaded / total, 1.0) * 1000))
        if speed_bps > 100_000:
            self._activity_lbl.setText(format_dl_progress_line(downloaded, total, speed_bps, eta_sec))
            self._activity_lbl.show()

    def _update_activity(self):
        elapsed = int(time.monotonic() - self._op_start_ts) if self._op_start_ts else 0
        phase = self._current_phase or "Switching branch…"
        self._activity_lbl.setText(f"{phase}  ·  {format_elapsed(elapsed)} elapsed")
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
        finish_worker(self)
        set_session_inhibit(self, None)

        if code == 0:
            self._status_lbl.setText("Branch staged — reboot to apply.")
            self._status_lbl.setObjectName("status-ok")
            self._log.append("\nDone. Reboot to boot into the new branch.")
            self._reboot_btn.show()
        else:
            self._status_lbl.setText(f"Switch failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")

        restyle(self._status_lbl)
        self._refresh_current()
