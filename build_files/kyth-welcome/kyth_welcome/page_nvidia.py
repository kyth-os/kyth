
# __KYTH_GENERATED_IMPORTS__
from .services.launch import reboot
from .core_base import (
    restyle, run_worker, set_session_inhibit,
)
from .services.hardware import (
    _akmod_nvidia_built, _akmod_nvidia_installed, _detect_nvidia, _hw_setup_done, _hw_setup_service_state,
    _nvidia_module_loaded, nvidia_status_view,
)
from .services.runtime import finish_worker
from .services.privileged import helper_action
from .qt import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QTimer,
)
from .widgets import (
    CollapsibleLogPanel, Page, _make_card,
)

# ── Page: NVIDIA Drivers ──────────────────────────────────────────────────────
class NvidiaPage(Page):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(8000)
        self._poll_timer.timeout.connect(self._refresh_status)

        self._page_header(
            "Advanced",
            "NVIDIA Drivers",
            "Build and verify proprietary NVIDIA kernel modules.",
        )
        self._sub = self._subheading("")

        self._status_lbl = QLabel()
        self._status_lbl.setWordWrap(True)
        self._add(self._status_lbl)

        reality_card, reality_layout = _make_card("card-accent-warn")
        reality_title = QLabel("NVIDIA is supported, but it is the special path")
        reality_title.setObjectName("card-title")
        reality_layout.addWidget(reality_title)
        reality_body = QLabel(
            "KythOS is tuned hardest for AMD and Intel's in-kernel graphics stack. "
            "NVIDIA uses the proprietary kernel module, so driver builds, Secure Boot "
            "enrollment, and a reboot after kernel changes are normal parts of the flow."
        )
        reality_body.setObjectName("card-copy")
        reality_body.setWordWrap(True)
        reality_layout.addWidget(reality_body)
        self._add(reality_card)

        btn_row = QHBoxLayout()
        self._install_btn = QPushButton("Build Driver Now")
        self._install_btn.setObjectName("primary")
        self._install_btn.clicked.connect(self._run_install)
        btn_row.addWidget(self._install_btn)
        btn_row.addStretch()
        self._add_layout(btn_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._add(self._progress)

        self._log_panel = CollapsibleLogPanel(min_height=200)
        self._add(self._log_panel)

        self._reboot_btn = QPushButton("Reboot to Apply")
        self._reboot_btn.setObjectName("primary")
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(reboot)
        self._add(self._reboot_btn)
        self._stretch()

        self._refresh_status()

    def _refresh_status(self):
        view = nvidia_status_view(
            has_gpu=_detect_nvidia(),
            loaded=_nvidia_module_loaded(),
            built=_akmod_nvidia_built(),
            installed=_akmod_nvidia_installed(),
            hw_setup_done=_hw_setup_done(),
            svc_state=_hw_setup_service_state(),
        )

        # Keep polling while the background service is compiling.
        if view.keep_polling and not self._poll_timer.isActive():
            self._poll_timer.start()
        elif not view.keep_polling:
            self._poll_timer.stop()

        self._sub.setText(view.sub_text)
        self._status_lbl.setText(view.status_text)
        self._status_lbl.setObjectName(view.status_style)

        self._install_btn.setVisible(view.install_visible)
        if view.install_visible:
            self._install_btn.setText(view.install_text)

        self._progress.setVisible(view.progress_visible)
        if view.progress_visible:
            self._progress.setRange(0, 0)

        self._reboot_btn.setVisible(view.reboot_visible)

        restyle(self._sub)
        restyle(self._status_lbl)

    def _run_install(self):
        self._build_module()

    def _build_module(self):
        cmd = helper_action("hardware-setup").command()
        self._log_panel.reset("→ Building NVIDIA kernel module via akmods…\n")
        self._progress.show()
        self._install_btn.setEnabled(False)

        run_worker(
            self,
            cmd,
            session_inhibit_reason="KythOS is building NVIDIA kernel module",
            on_line=self._on_line,
            on_done=self._on_done,
        )

    def _on_line(self, text: str):
        self._log_panel.append(text)

    def _on_done(self, code: int):
        self._progress.hide()
        self._install_btn.setEnabled(True)
        finish_worker(self)
        set_session_inhibit(self, None)

        if code == 0:
            self._log_panel.append("\nDone. Reboot to activate NVIDIA drivers.")
            self._reboot_btn.show()
        else:
            self._log_panel.append(f"\nInstallation failed (exit code {code}).")
        self._refresh_status()
