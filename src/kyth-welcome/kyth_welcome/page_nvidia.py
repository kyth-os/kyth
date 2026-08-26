
# __KYTH_GENERATED_IMPORTS__
from .services.launch import reboot
from .core_base import (
    restyle, run_worker, set_session_inhibit,
)
from .services.hardware import (
    _akmod_nvidia_built, _akmod_nvidia_installed, _detect_nvidia, _hw_setup_done, _hw_setup_service_state,
    _nvidia_module_loaded, _secureboot_state, nvidia_status_view,
    gpu_switch_current_mode, gpu_switch_set_mode, gpu_switch_supported_modes,
    is_hybrid_system, supergfxctl_available,
)
from .services.runtime import guard_disposed,  DataWorker, finish_worker
from .services.privileged import helper_action
from .qt import (
    QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTimer,
)
from .widgets import (
    CollapsibleLogPanel, Page, _make_card,
)

# ── Page: NVIDIA Drivers ──────────────────────────────────────────────────────
class NvidiaPage(Page):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._status_worker = None
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

        # ── Hybrid graphics — supergfxctl mode switch ────────────────────────
        # Hidden by default: only shown once _fetch_status_facts confirms
        # this machine actually has a second GPU to switch to. supergfxctl
        # itself stays opt-in (ujust install-asus-tools) — detected here,
        # never installed from this page.
        self._gpu_switch_card, gpu_switch_layout = _make_card()
        self._gpu_switch_card.hide()
        gpu_switch_title = QLabel("Hybrid Graphics")
        gpu_switch_title.setObjectName("card-title")
        gpu_switch_layout.addWidget(gpu_switch_title)
        self._gpu_switch_status = QLabel("Checking…")
        self._gpu_switch_status.setObjectName("card-copy")
        self._gpu_switch_status.setWordWrap(True)
        gpu_switch_layout.addWidget(self._gpu_switch_status)
        gpu_switch_row = QHBoxLayout()
        gpu_switch_row.setSpacing(8)
        self._gpu_mode_combo = QComboBox()
        self._gpu_mode_combo.setMinimumWidth(160)
        gpu_switch_row.addWidget(self._gpu_mode_combo)
        self._gpu_apply_btn = QPushButton("Apply")
        self._gpu_apply_btn.setObjectName("primary")
        self._gpu_apply_btn.clicked.connect(self._apply_gpu_mode)
        gpu_switch_row.addWidget(self._gpu_apply_btn)
        gpu_switch_row.addStretch()
        gpu_switch_layout.addLayout(gpu_switch_row)
        self._add(self._gpu_switch_card)

        self._stretch()

        self._gpu_mode_worker = None
        self._gpu_modes_populated = False
        self._refresh_status()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._refresh_status()

    def hideEvent(self, event):  # noqa: N802
        self._poll_timer.stop()
        super().hideEvent(event)

    @staticmethod
    def _fetch_status_facts() -> dict:
        """Run off the GUI thread by _refresh_status()'s DataWorker.
        _detect_nvidia (lspci), _nvidia_module_loaded (lsmod),
        _akmod_nvidia_built (modinfo), _akmod_nvidia_installed (rpm -q), and
        _hw_setup_service_state (systemctl is-active) are all
        subprocess-backed — _hw_setup_done() just reads a local JSON file.
        _secureboot_state (mokutil) is also cached — missing mokutil -> unknown."""
        from kyth_shared.akmods_lock import akmods_build_in_progress

        hybrid = is_hybrid_system()
        return {
            "has_gpu": _detect_nvidia(),
            "loaded": _nvidia_module_loaded(),
            "built": _akmod_nvidia_built(),
            "installed": _akmod_nvidia_installed(),
            "hw_setup_done": _hw_setup_done(),
            "svc_state": _hw_setup_service_state(),
            "secureboot": _secureboot_state(),
            "akmods_busy": akmods_build_in_progress(),
            "hybrid": hybrid,
            "supergfx_available": supergfxctl_available() if hybrid else False,
            "gpu_mode": gpu_switch_current_mode() if hybrid else "",
            "gpu_modes": gpu_switch_supported_modes() if hybrid else (),
        }

    def _refresh_status(self):
        # Called from __init__, from the 8s poll timer while an akmod build
        # runs in the background, and after a manual build finishes — none
        # of those may block the GUI thread on the subprocess probes above,
        # so the actual gathering happens on a DataWorker and this just
        # kicks it off (a call while a previous one is still in flight is a
        # no-op; the next poll tick retries).
        if self._status_worker is not None:
            return
        worker = DataWorker("nvidia-status-facts", self._fetch_status_facts)
        self._status_worker = worker
        worker.result.connect(guard_disposed(lambda _key, facts: self._apply_status_facts(facts)))
        worker.failed.connect(lambda _key, _message: None)
        worker.finished.connect(lambda: setattr(self, "_status_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _apply_status_facts(self, facts: dict) -> None:
        view = nvidia_status_view(
            has_gpu=facts["has_gpu"],
            loaded=facts["loaded"],
            built=facts["built"],
            installed=facts["installed"],
            hw_setup_done=facts["hw_setup_done"],
            svc_state=facts["svc_state"],
            secureboot=facts.get("secureboot", "unknown"),
            akmods_busy=bool(facts.get("akmods_busy")),
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

        self._apply_gpu_switch_facts(facts)

    def _apply_gpu_switch_facts(self, facts: dict) -> None:
        self._gpu_switch_card.setVisible(bool(facts.get("hybrid")))
        if not facts.get("hybrid"):
            return
        if not facts.get("supergfx_available"):
            self._gpu_switch_status.setText(
                "This machine has a second GPU to switch to, but supergfxctl isn't "
                "installed. Run: ujust install-asus-tools"
            )
            self._gpu_mode_combo.setEnabled(False)
            self._gpu_apply_btn.setEnabled(False)
            restyle(self._gpu_switch_status)
            return
        self._gpu_mode_combo.setEnabled(True)
        self._gpu_apply_btn.setEnabled(True)
        mode = str(facts.get("gpu_mode") or "")
        modes = facts.get("gpu_modes") or ()
        if not self._gpu_modes_populated and modes:
            self._gpu_mode_combo.clear()
            self._gpu_mode_combo.addItems(list(modes))
            self._gpu_modes_populated = True
        if mode:
            idx = self._gpu_mode_combo.findText(mode)
            if idx >= 0:
                self._gpu_mode_combo.setCurrentIndex(idx)
            self._gpu_switch_status.setText(f"Current mode: {mode}")
        else:
            self._gpu_switch_status.setText("Pick a mode and apply.")
        restyle(self._gpu_switch_status)

    def _apply_gpu_mode(self) -> None:
        if self._gpu_mode_worker is not None:
            return
        mode = self._gpu_mode_combo.currentText()
        if not mode:
            return
        self._gpu_apply_btn.setEnabled(False)
        self._gpu_switch_status.setText(f"Switching to {mode}…")
        restyle(self._gpu_switch_status)

        worker = DataWorker("gpu-switch-set-mode", lambda: gpu_switch_set_mode(mode))
        self._gpu_mode_worker = worker
        worker.result.connect(guard_disposed(lambda _key, result: self._on_gpu_mode_applied(result)))
        worker.failed.connect(guard_disposed(lambda _key, message: self._on_gpu_mode_applied((False, str(message)))))
        worker.finished.connect(lambda: setattr(self, "_gpu_mode_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_gpu_mode_applied(self, result: object) -> None:
        self._gpu_apply_btn.setEnabled(True)
        ok, message = result if isinstance(result, tuple) and len(result) == 2 else (False, str(result))
        self._gpu_switch_status.setText(message or ("Done." if ok else "Failed."))
        self._gpu_switch_status.setObjectName("status-ok" if ok else "status-err")
        restyle(self._gpu_switch_status)

    def _run_install(self):
        self._build_module()

    def _build_module(self):
        from kyth_shared.akmods_lock import akmods_build_in_progress

        if _hw_setup_service_state() == "activating" or akmods_build_in_progress():
            self._log_panel.reset(
                "A NVIDIA module build is already running. This page will update when it finishes.\n"
            )
            self._refresh_status()
            return
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
        # S3: cancelled (Esc on ksshaskpass) must not invalidate 300s cache nor show err
        from .services.runtime import Worker

        if code == Worker.CANCELLED:
            self._log_panel.append("\nCancelled — no change.")
            self._status_lbl.setText("Cancelled — no change.")
            self._status_lbl.setObjectName("status-warn")
            restyle(self._status_lbl)
        elif code == 0:
            try:
                from kyth_shared.system.probe import invalidate_nvidia
                invalidate_nvidia()
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
                pass
            self._log_panel.append("\nDone. Reboot to activate NVIDIA drivers.")
            self._reboot_btn.show()
        else:
            self._log_panel.append(f"\nInstallation failed (exit code {code}).")
        self._refresh_status()
