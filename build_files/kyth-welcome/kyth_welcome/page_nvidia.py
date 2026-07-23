
# __KYTH_GENERATED_IMPORTS__
from .services.launch import reboot
from .core_base import (
    _restyle, _run_worker, _set_session_inhibit,
)
from .services.hardware import (
    _akmod_nvidia_built, _akmod_nvidia_installed, _detect_nvidia, _hw_setup_done, _hw_setup_service_state,
    _nvidia_module_loaded,
)
from .services.runtime import _finish_worker
from .services.privileged import helper_action
from .qt import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QTimer,
)
from .widgets import (
    Page, _make_card, _set_log_panel,
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

        self._log_toggle = QPushButton("Show details")
        self._log_toggle.setCheckable(True)
        self._log_toggle.clicked.connect(lambda checked: _set_log_panel(self._log_toggle, self._log, checked))
        self._log_toggle.hide()
        self._add(self._log_toggle)

        self._log = QTextEdit()
        self._log.document().setMaximumBlockCount(5000)
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(200)
        self._log.hide()
        self._add(self._log)

        self._reboot_btn = QPushButton("Reboot to Apply")
        self._reboot_btn.setObjectName("primary")
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(reboot)
        self._add(self._reboot_btn)
        self._stretch()

        self._refresh_status()

    def _refresh_status(self):
        has_gpu = _detect_nvidia()
        loaded = _nvidia_module_loaded()
        built = _akmod_nvidia_built()
        installed = _akmod_nvidia_installed()
        svc_state = _hw_setup_service_state()
        auto_building = svc_state == "activating"

        # Keep polling while the background service is compiling.
        if auto_building and not self._poll_timer.isActive():
            self._poll_timer.start()
        elif not auto_building:
            self._poll_timer.stop()

        if not has_gpu:
            self._sub.setText("No NVIDIA GPU detected in this system.")
            self._status_lbl.setText("No NVIDIA hardware found.")
            self._status_lbl.setObjectName("status-dim")
            self._install_btn.hide()
            self._progress.hide()
        elif loaded:
            self._sub.setText("NVIDIA GPU detected.")
            self._status_lbl.setText("Drivers are active and the kernel module is loaded.")
            self._status_lbl.setObjectName("status-ok")
            self._install_btn.hide()
            self._progress.hide()
        elif built:
            self._sub.setText("NVIDIA GPU detected.")
            self._status_lbl.setText("Drivers installed — reboot to activate.")
            self._status_lbl.setObjectName("status-warn")
            self._install_btn.hide()
            self._progress.hide()
            self._reboot_btn.show()
        elif auto_building:
            # kyth-hw-setup is running akmods in the background right now.
            self._sub.setText("NVIDIA GPU detected.")
            self._status_lbl.setText(
                "Building NVIDIA kernel module automatically — this takes 5–15 minutes.\n"  # noqa: RUF001 — en dash, deliberate typography
                "You can keep using the system. This page will update when the build finishes."
            )
            self._status_lbl.setObjectName("subheading")
            self._install_btn.hide()
            self._progress.setRange(0, 0)
            self._progress.show()
        elif _hw_setup_done() and svc_state == "failed":
            # Service ran but akmods failed — offer a manual retry.
            self._sub.setText("NVIDIA GPU detected — automatic build failed.")
            self._status_lbl.setText(
                "kyth-hw-setup could not build the kernel module. "
                "Check journalctl -u kyth-hw-setup for details, then click below to retry."
            )
            self._status_lbl.setObjectName("status-err")
            self._install_btn.setText("Retry Build")
            self._install_btn.show()
            self._progress.hide()
        elif installed:
            # Service hasn't run yet or was reset — offer a manual kick-off.
            self._sub.setText("NVIDIA GPU detected.")
            self._status_lbl.setText(
                "Kernel module will be compiled automatically on next boot, "
                "or click below to build it now."
            )
            self._status_lbl.setObjectName("subheading")
            self._install_btn.setText("Build Driver Now")
            self._install_btn.show()
            self._progress.hide()
        else:
            # akmod-nvidia missing — should never happen on a correctly built image.
            self._sub.setText("NVIDIA GPU detected — driver package missing.")
            self._status_lbl.setText(
                "akmod-nvidia is not installed. This is unexpected on KythOS.\n"
                "Run: rpm-ostree install akmod-nvidia, then reboot and return here."
            )
            self._status_lbl.setObjectName("status-err")
            self._install_btn.hide()
            self._progress.hide()

        _restyle(self._sub)
        _restyle(self._status_lbl)

    def _run_install(self):
        self._build_module()

    def _build_module(self):
        cmd = helper_action("hardware-setup").command()
        self._log.clear()
        self._log.append("→ Building NVIDIA kernel module via akmods…\n")
        self._log_toggle.show()
        _set_log_panel(self._log_toggle, self._log, False)
        self._progress.show()
        self._install_btn.setEnabled(False)

        _run_worker(
            self,
            cmd,
            session_inhibit_reason="KythOS is building NVIDIA kernel module",
            on_line=self._on_line,
            on_done=self._on_done,
        )

    def _on_line(self, text: str):
        self._log.append(text)
        self._log.ensureCursorVisible()

    def _on_done(self, code: int):
        self._progress.hide()
        self._install_btn.setEnabled(True)
        _finish_worker(self)
        _set_session_inhibit(self, None)

        if code == 0:
            self._log.append("\nDone. Reboot to activate NVIDIA drivers.")
            self._reboot_btn.show()
        else:
            self._log.append(f"\nInstallation failed (exit code {code}).")
        self._refresh_status()
