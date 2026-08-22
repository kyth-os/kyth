
# __KYTH_GENERATED_IMPORTS__
from .services.launch import reboot_to_apply
from .core_base import restyle, run_worker, set_session_inhibit
from .services.process import with_idle_inhibit
from .services.bootc import REGISTRY, bootc_cancel_block_reason, branch_display_name, current_branch, current_kernel_flavor, image_tag_for_kernel, parse_update_phase
from .services.diagnostics import command_stdout
from .services.runtime import Worker, finish_worker
from .services.privileged import bootc_action
from .qt import (
    QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, single_shot,
)
from .widgets import (
    CollapsibleLogPanel, Page, _make_card,
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
        warn_title.setObjectName("card-title-warn")
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

        self._log_panel = CollapsibleLogPanel(min_height=140)
        self._add(self._log_panel)

        self._reboot_btn = QPushButton("Reboot to Apply")
        self._reboot_btn.setObjectName("primary")
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(reboot_to_apply)
        self._add(self._reboot_btn)
        self._stretch()
    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        single_shot(self, 0, self._refresh)

    def _refresh(self):
        flavor = current_kernel_flavor()
        kernel = command_stdout(["uname", "-r"]) or "unknown"
        channel = branch_display_name(current_branch())
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
            restyle(btn)

    def _switch_kernel(self, flavor: str):
        tag = image_tag_for_kernel(flavor)
        ref = f"{REGISTRY}:{tag}"
        self._current_phase = ""
        self._cancel_blocked = False
        self._cancel_block_reason = ""
        self._log_panel.reset(f"-> sudo bootc switch {ref}\n")
        self._progress.show()
        self._status_lbl.setText("Switching kernel image…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        restyle(self._status_lbl)
        self._reboot_btn.hide()
        self._cancel_btn.setText("Cancel Kernel Switch")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.show()
        self._cancel_note.setText("You can cancel while the kernel image is downloading. Once KythOS starts writing or staging it, let the switch finish.")
        self._cancel_note.show()
        for btn in self._kernel_buttons.values():
            btn.setEnabled(False)

        run_worker(
            self,
            with_idle_inhibit(
                bootc_action("switch", ref).command(),
                "KythOS is switching kernel image",
            ),
            session_inhibit_reason="KythOS is switching kernel image",
            on_line=self._on_line,
            on_done=self._on_done,
        )

    def _on_line(self, text: str):
        phase = parse_update_phase(text.strip(), "switch")
        if phase:
            self._current_phase = phase
            self._status_lbl.setText(phase)
            self._update_cancel_state()
        self._log_panel.append(text)

    def _update_cancel_state(self):
        reason = bootc_cancel_block_reason("switch", self._current_phase)
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
            self._log_panel.append(f"\nCancel unavailable: {self._cancel_block_reason}")
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
        finish_worker(self)
        set_session_inhibit(self, None)
        if code == Worker.CANCELLED:
            self._status_lbl.setText("Kernel switch cancelled.")
            self._status_lbl.setObjectName("status-warn")
            self._log_panel.append("\nCancelled. The current kernel remains selected.")
        elif code == 0:
            self._status_lbl.setText("Kernel image staged — reboot to apply it.")
            self._status_lbl.setObjectName("status-ok")
            self._log_panel.append("\nDone. Reboot to activate the selected kernel.")
            self._reboot_btn.show()
        else:
            self._status_lbl.setText(f"Kernel switch failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
        restyle(self._status_lbl)
        self._refresh()
