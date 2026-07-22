
# __KYTH_GENERATED_IMPORTS__
from .services.launch import reboot
from .core_base import (
    _bootc_cancel_block_reason, _branch_display_name, _current_kernel_flavor, _image_tag_for_kernel,
    _parse_update_phase, _restyle, _set_session_inhibit, _with_idle_inhibit,
)
from .services.diagnostics import _command_stdout
from .services.runtime import Worker, _finish_worker
from .services.privileged import bootc_action
from .core_base import REGISTRY, _current_branch
from .qt import (
    QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QTextEdit, single_shot,
)
from .widgets import (
    Page, _make_card, _set_log_panel,
)

# ── Page: Kernel ──────────────────────────────────────────────────────────────
class KernelPage(Page):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._initial_refresh_started = False
        self._current_phase = ""
        self._cancel_blocked = False
        self._cancel_block_reason = ""

        self._page_header(
            "Advanced",
            "Kernel",
            "Fedora is the recommended default. CachyOS is an opt-in image variant for advanced gaming and low-latency workloads.",
        )

        state_card, state_layout = _make_card()
        state_layout.setSpacing(6)
        state_title = QLabel("Current kernel")
        state_title.setObjectName("card-title")
        state_layout.addWidget(state_title)
        self._current_lbl = QLabel()
        self._current_lbl.setObjectName("card-copy")
        self._current_lbl.setWordWrap(True)
        state_layout.addWidget(self._current_lbl)
        self._add(state_card)

        picker_row = QHBoxLayout()
        picker_row.setSpacing(14)
        self._kernel_buttons: dict[str, QPushButton] = {}
        for flavor, title, copy, button_text in (
            (
                "fedora",
                "Fedora Kernel",
                "Recommended for new users. Best supported by Fedora updates, Secure Boot, NVIDIA akmods, and general troubleshooting.",
                "Use Fedora Kernel",
            ),
            (
                "cachy",
                "CachyOS Kernel",
                "Advanced performance option with CachyOS tuning. Good for users chasing latency or benchmark wins.",
                "Switch to CachyOS",
            ),
        ):
            card, layout = _make_card()
            title_lbl = QLabel(title)
            title_lbl.setObjectName("card-title")
            layout.addWidget(title_lbl)
            body = QLabel(copy)
            body.setObjectName("card-copy")
            body.setWordWrap(True)
            layout.addWidget(body)
            btn = QPushButton(button_text)
            btn.clicked.connect(lambda _=False, f=flavor: self._switch_kernel(f))
            layout.addWidget(btn)
            self._kernel_buttons[flavor] = btn
            picker_row.addWidget(card, 1)
        self._add_layout(picker_row)

        warn, warn_layout = _make_card("card-accent-warn")
        warn_title = QLabel("Advanced users only")
        warn_title.setStyleSheet("color: #d4a843; font-size: 14px; font-weight: 700;")
        warn_layout.addWidget(warn_title)
        warn_body = QLabel(
            "Kernel switches download a different KythOS image and apply after reboot. "
            "CachyOS follows your current Stable or Testing channel. "
            "Roll Back remains available from the boot menu and the Update page if a custom kernel causes trouble."
        )
        warn_body.setObjectName("card-copy")
        warn_body.setWordWrap(True)
        warn_layout.addWidget(warn_body)
        self._add(warn)

        self._status_lbl = QLabel()
        self._status_lbl.hide()
        self._add(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._add(self._progress)

        cancel_row = QHBoxLayout()
        cancel_row.setSpacing(10)
        self._cancel_btn = QPushButton("Cancel Kernel Switch")
        self._cancel_btn.clicked.connect(self._cancel_switch)
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
        self._log_toggle.clicked.connect(lambda checked: _set_log_panel(self._log_toggle, self._log, checked))
        self._log_toggle.hide()
        self._add(self._log_toggle)

        self._log = QTextEdit()
        self._log.document().setMaximumBlockCount(5000)
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(140)
        self._log.hide()
        self._add(self._log)

        self._reboot_btn = QPushButton("Reboot to Apply")
        self._reboot_btn.setObjectName("primary")
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(reboot)
        self._add(self._reboot_btn)
        self._stretch()
    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        single_shot(self, 0, self._refresh)

    def _refresh(self):
        flavor = _current_kernel_flavor()
        kernel = _command_stdout(["uname", "-r"]) or "unknown"
        channel = _branch_display_name(_current_branch())
        names = {"fedora": "Fedora", "cachy": "CachyOS"}
        self._current_lbl.setText(f"{names.get(flavor, flavor)} kernel  ·  {kernel}  ·  {channel}")
        idle = self._worker is None
        for key, btn in self._kernel_buttons.items():
            if key == flavor:
                btn.setObjectName("branch-active")
                btn.setText("Current")
                btn.setEnabled(False)
            else:
                btn.setObjectName("branch-inactive")
                btn.setText({
                    "fedora": "Use Fedora Kernel",
                    "cachy": "Switch to CachyOS",
                }[key])
                btn.setEnabled(idle)
            _restyle(btn)

    def _switch_kernel(self, flavor: str):
        tag = _image_tag_for_kernel(flavor)
        ref = f"{REGISTRY}:{tag}"
        self._current_phase = ""
        self._cancel_blocked = False
        self._cancel_block_reason = ""
        self._log.clear()
        self._log.append(f"-> sudo bootc switch {ref}\n")
        self._log_toggle.show()
        _set_log_panel(self._log_toggle, self._log, False)
        self._progress.show()
        self._status_lbl.setText("Switching kernel image…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        _restyle(self._status_lbl)
        self._reboot_btn.hide()
        self._cancel_btn.setText("Cancel Kernel Switch")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.show()
        self._cancel_note.setText("You can cancel while the kernel image is downloading. Once KythOS starts writing or staging it, let the switch finish.")
        self._cancel_note.show()
        for btn in self._kernel_buttons.values():
            btn.setEnabled(False)

        self._worker = Worker(_with_idle_inhibit(
            bootc_action("switch", ref).command(),
            "KythOS is switching kernel image",
        ))
        _set_session_inhibit(self, "KythOS is switching kernel image")
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_line(self, text: str):
        phase = _parse_update_phase(text.strip(), "switch")
        if phase:
            self._current_phase = phase
            self._status_lbl.setText(phase)
            self._update_cancel_state()
        self._log.append(text)
        self._log.ensureCursorVisible()

    def _update_cancel_state(self):
        reason = _bootc_cancel_block_reason("switch", self._current_phase)
        if reason:
            self._cancel_blocked = True
            self._cancel_block_reason = reason
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setToolTip(reason)
            self._cancel_note.setText(reason)
        elif not self._cancel_blocked:
            self._cancel_btn.setEnabled(True)
            self._cancel_btn.setToolTip("Stop the kernel switch while it is still safe to cancel")

    def _cancel_switch(self):
        if self._worker is None:
            return
        self._update_cancel_state()
        if self._cancel_blocked:
            self._log.append(f"\nCancel unavailable: {self._cancel_block_reason}")
            return
        reply = QMessageBox.question(
            self,
            "Cancel Kernel Switch?",
            "Stop downloading the selected kernel image? You can start the switch again later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._worker is None:
            return
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("Cancelling…")
        self._cancel_note.setText("Cancel requested. Waiting for the kernel switch to stop cleanly…")
        self._status_lbl.setText("Cancelling kernel switch…")
        self._worker.cancel()

    def _on_done(self, code: int):
        self._progress.hide()
        self._cancel_btn.hide()
        self._cancel_note.hide()
        _finish_worker(self)
        _set_session_inhibit(self, None)
        if code == Worker.CANCELLED:
            self._status_lbl.setText("Kernel switch cancelled.")
            self._status_lbl.setObjectName("status-warn")
            self._log.append("\nCancelled. The current kernel remains selected.")
        elif code == 0:
            self._status_lbl.setText("Kernel image staged — reboot to apply it.")
            self._status_lbl.setObjectName("status-ok")
            self._log.append("\nDone. Reboot to activate the selected kernel.")
            self._reboot_btn.show()
        else:
            self._status_lbl.setText(f"Kernel switch failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
        _restyle(self._status_lbl)
        self._refresh()
