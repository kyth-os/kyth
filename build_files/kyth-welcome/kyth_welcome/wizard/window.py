"""First-run wizard shell (navigation + step composition)."""
from __future__ import annotations

import subprocess

from ..core_base import (
    _load_profile, _mark_wizard_done, _restyle, _running_threads,
)
from ..qt import (  # noqa: E501
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QTimer, QVBoxLayout, QWidget, Qt,
)
from ..ui_tokens import accent_line_style
from .steps_apps import _AppsStepMixin
from .steps_finish import _FinishStepMixin
from .steps_gaming import _GamingStepMixin
from .steps_welcome import _WelcomeStepMixin


class WizardWindow(
    QMainWindow,
    _WelcomeStepMixin,
    _AppsStepMixin,
    _GamingStepMixin,
    _FinishStepMixin,
):
    """Linear first-run wizard. On close writes a sentinel so future launches
    open the hub (MainWindow) instead."""

    _STEP_LABELS = ["Welcome", "Update", "Hardware", "Pick Apps", "Gaming", "All Done"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Welcome to KythOS")
        self.setMinimumSize(840, 600)
        self.resize(980, 700)

        root = QWidget()
        root.setObjectName("content-area")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # ── Header: logo + step progress track ───────────────────────────────
        header = QWidget()
        header.setObjectName("wizard-header")
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(36, 0, 36, 0)
        header_layout.setSpacing(0)

        logo = QLabel("KythOS")
        logo.setObjectName("sidebar-logo")
        header_layout.addWidget(logo)
        header_layout.addStretch()

        # Step progress track (dot + connector + label per step)
        self._step_label_widgets: list[QLabel] = []
        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)

        for i, label in enumerate(self._STEP_LABELS):
            if i > 0:
                connector = QFrame()
                connector.setFixedSize(28, 2)
                connector.setStyleSheet("background: #4a4a4a; border: none;")
                progress_layout.addWidget(connector)

            step_col = QWidget()
            step_col_layout = QVBoxLayout(step_col)
            step_col_layout.setContentsMargins(0, 0, 0, 0)
            step_col_layout.setSpacing(4)
            step_col_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setObjectName("step-dot-inactive")
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            step_col_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignHCenter)

            lbl = QLabel(label)
            lbl.setObjectName("wizard-progress-step")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            step_col_layout.addWidget(lbl, 0, Qt.AlignmentFlag.AlignHCenter)

            progress_layout.addWidget(step_col)
            self._step_label_widgets.append((dot, lbl))  # type: ignore[assignment]

        header_layout.addWidget(progress_widget)
        root_layout.addWidget(header)

        # Accent line
        accent = QFrame()
        accent.setFixedHeight(2)
        accent.setStyleSheet(accent_line_style())
        root_layout.addWidget(accent)

        # ── Content stack ─────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setObjectName("content-area")
        root_layout.addWidget(self._stack, 1)

        self._profile = _load_profile()
        self._handoff_win: QMainWindow | None = None
        # Lazy page imports avoid circular import cycles with the hub package.
        from ..page_gaming import GamingPage
        from ..page_hardware import HardwarePage
        from ..page_update import UpdatePage

        self._update_page = UpdatePage()
        self._hw_page = HardwarePage(wizard_mode=True)
        self._hw_page.action_requested.connect(self._on_hw_action_requested)
        self._gaming_page = GamingPage(wizard_mode=True)
        self._first_run_apps_step = self._make_first_run_apps_step()

        self._steps = [
            self._make_welcome_step(),
            self._wrap_step(
                "Update Your System",
                "Start with the latest OS image and packages before getting started.",
                self._update_page,
            ),
            self._wrap_step(
                "Hardware Check",
                "Checking your GPU, CPU, display, controllers, audio, and peripherals.",
                self._hw_page,
            ),
            self._first_run_apps_step,
            self._make_gaming_step(),
            self._make_finish_step(),
        ]
        for step in self._steps:
            self._stack.addWidget(step)

        # ── Footer ────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("wizard-footer")
        footer.setFixedHeight(68)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(36, 0, 36, 0)
        footer_layout.setSpacing(10)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.clicked.connect(self._go_back)
        footer_layout.addWidget(self._back_btn)
        self._step_hint = QLabel("")
        self._step_hint.setObjectName("wizard-footer-hint")
        self._step_hint.setWordWrap(True)
        footer_layout.addWidget(self._step_hint, 1)

        self._skip_btn = QPushButton("Skip for now")
        self._skip_btn.clicked.connect(self._go_next)
        footer_layout.addWidget(self._skip_btn)

        self._next_btn = QPushButton("Get Started  →")
        self._next_btn.setObjectName("primary")
        self._next_btn.setFixedWidth(160)
        self._next_btn.clicked.connect(self._go_next)
        footer_layout.addWidget(self._next_btn)
        root_layout.addWidget(footer)


        self._current = 0
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(250)
        self._busy_timer.timeout.connect(self._update_nav)
        self._busy_timer.start()
        self._update_nav()

    # ── Step builders ─────────────────────────────────────────────────────────

    def _wrap_step(self, title: str, subtitle: str, page: QWidget) -> QWidget:
        container = QWidget()
        container.setObjectName("content-area")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        intro = QWidget()
        intro.setObjectName("page-header")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(56, 22, 56, 20)
        intro_layout.setSpacing(5)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("heading")
        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setObjectName("subheading")
        intro_layout.addWidget(title_lbl)
        intro_layout.addWidget(subtitle_lbl)
        layout.addWidget(intro)

        layout.addWidget(_divider())
        layout.addWidget(page, 1)
        return container

    def _on_profile_chosen(self, profile: str):
        self._profile = profile
        for key, btn in self._profile_buttons.items():
            btn.setChecked(key == profile)
        _save_profile(profile)
        try:
            subprocess.Popen(["/usr/bin/kyth-apply-role-preset", profile], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603 # nosemgrep
        except OSError:
            pass
        # Re-seed the Pick Apps defaults to match the chosen profile. Only
        # enabled boxes are touched — already-installed apps stay locked.
        wanted = self._PROFILE_DEFAULT_APPS.get(profile, set())
        for check, app_id, _name in self._wizard_extra_checks:
            if check.isEnabled():
                check.setChecked(app_id in wanted)
        self._update_nav()

    def _open_hub_at(self, page_key: str):
        """Hand off from the wizard to the System Hub opened at a page."""
        _mark_wizard_done()
        from ..windows import MainWindow
        main_win = MainWindow()
        main_win.setWindowIcon(QIcon.fromTheme("kyth"))
        main_win.showMaximized()
        main_win._navigate_to(page_key)
        self._handoff_win = main_win
        self.close()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _has_running_operation(self) -> bool:
        return any(t.BLOCKS_CLOSE for t in _running_threads())

    def _update_nav(self):
        idx = self._current
        total = len(self._steps)
        operation_busy = self._has_running_operation()
        hints = [
            "Pick a focus. You can change it later from Home.",
            "Recommended. Updates stage safely and apply after restart.",
            "Recommended. Hardware checks catch driver, display, audio, network, and controller issues early.",
            "Optional. Install extras now, or continue with the game-ready defaults.",
            "Optional. Launcher and Proton tools stay available from Gaming.",
            "System Hub stays in the app menu whenever you need it.",
        ]
        self._step_hint.setText(hints[idx] if idx < len(hints) else "")

        for i, (dot, lbl) in enumerate(self._step_label_widgets):
            if i < idx:
                dot.setObjectName("step-dot-done")
                lbl.setObjectName("wizard-progress-step-done")
            elif i == idx:
                dot.setObjectName("step-dot-active")
                lbl.setObjectName("wizard-progress-step-active")
            else:
                dot.setObjectName("step-dot-inactive")
                lbl.setObjectName("wizard-progress-step")
            _restyle(dot)
            _restyle(lbl)

        self._back_btn.setVisible(idx > 0)
        self._skip_btn.setVisible(0 < idx < total - 1)
        self._back_btn.setEnabled(not operation_busy)
        self._skip_btn.setEnabled(not operation_busy)
        self._next_btn.setEnabled(not operation_busy)
        if hasattr(self, "_finish_work_btn"):
            self._finish_work_btn.setVisible(self._profile == "everyday")

        if idx == total - 1:
            self._next_btn.setText("Close")
        elif idx == 0:
            self._next_btn.setText("Get Started  →")
        else:
            self._next_btn.setText("Next  →")

    def _on_hw_action_requested(self, page_key: str):
        self._open_hub_at(page_key)

    def _go_back(self):
        if self._current > 0:
            self._current -= 1
            self._stack.setCurrentIndex(self._current)
            self._update_nav()

    def _go_next(self):
        if self._current == len(self._steps) - 1:
            _mark_wizard_done()
            self.close()
        else:
            self._current += 1
            self._stack.setCurrentIndex(self._current)
            self._update_nav()

    def closeEvent(self, event):
        if self._has_running_operation():
            QMessageBox.warning(
                self,
                "KythOS Is Busy",
                "A setup task is still running. Cancel it from the current page while cancellation is available, or wait for it to finish before closing.",
            )
            event.ignore()
            self.raise_()
            self.activateWindow()
            return
        _mark_wizard_done()
        super().closeEvent(event)
