# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.launch import popen
from .services.runtime import Worker
from .qt import (
    QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)
from .widgets import CollapsibleLogPanel, _make_card


class _DeveloperTabMixin:
    # ── Tab 5: Developer ──────────────────────────────────────────────────────

    def _build_developer_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel("Developer Workstation Environment")
        title.setObjectName("section-title")
        layout.addWidget(title)

        ai_card, ai_layout = _make_card()
        ai_title = QLabel("KythOS Developer & AI Container (kyth-ai-dev)")
        ai_title.setObjectName("card-title")
        ai_layout.addWidget(ai_title)

        ai_desc = QLabel(
            "Unified local developer & AI Distrobox container housing VS Code, Google Antigravity IDE, Node.js, Azure CLI, GitHub CLI, Claude Code, Codex CLI, Headroom, Ollama, llama.cpp, Rust, and Python. Exports applications and CLI tools directly to your desktop menu and PATH."
        )
        ai_desc.setWordWrap(True)
        ai_layout.addWidget(ai_desc)

        ai_btn_row = QHBoxLayout()
        ai_btn_row.setSpacing(10)
        self._ai_setup_btn = QPushButton("Setup / Export Apps")
        self._ai_setup_btn.setObjectName("primary")
        self._ai_status_btn = QPushButton("Status")
        self._ai_enter_btn = QPushButton("Enter Shell")
        self._ai_start_btn = QPushButton("Start AI Service")
        self._ai_stop_btn = QPushButton("Stop AI Service")
        self._ai_delete_btn = QPushButton("Delete")
        self._ai_delete_btn.setObjectName("danger")
        self._ai_setup_btn.clicked.connect(lambda _=False: self._ai_run("setup"))
        self._ai_status_btn.clicked.connect(lambda _=False: self._ai_run("status"))
        self._ai_enter_btn.clicked.connect(self._ai_enter_box)
        self._ai_start_btn.clicked.connect(lambda _=False: self._ai_run("start"))
        self._ai_stop_btn.clicked.connect(lambda _=False: self._ai_run("stop"))
        self._ai_delete_btn.clicked.connect(lambda _=False: self._ai_run("remove"))
        for btn in (
            self._ai_setup_btn,
            self._ai_status_btn,
            self._ai_enter_btn,
            self._ai_start_btn,
            self._ai_stop_btn,
            self._ai_delete_btn,
        ):
            ai_btn_row.addWidget(btn)
        ai_btn_row.addStretch(1)
        ai_layout.addLayout(ai_btn_row)

        self._ai_status_lbl = QLabel("Ready.")
        self._ai_status_lbl.setObjectName("status-muted")
        ai_layout.addWidget(self._ai_status_lbl)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.hide()
        ai_layout.addWidget(self._ai_progress)

        self._ai_log_panel = CollapsibleLogPanel()
        ai_layout.addWidget(self._ai_log_panel)
        layout.addWidget(ai_card)
        layout.addStretch(1)
        return page

    def _ai_buttons(self):
        return tuple(
            btn for btn in (
                getattr(self, "_ai_setup_btn", None),
                getattr(self, "_ai_status_btn", None),
                getattr(self, "_ai_enter_btn", None),
                getattr(self, "_ai_start_btn", None),
                getattr(self, "_ai_stop_btn", None),
                getattr(self, "_ai_delete_btn", None),
            ) if btn is not None
        )

    def _ai_set_running(self, running: bool):
        for btn in self._ai_buttons():
            btn.setEnabled(not running)
        if hasattr(self, "_ai_progress"):
            self._ai_progress.setVisible(running)

    def _ai_run(self, action: str):
        if getattr(self, "_ai_worker", None) and self._ai_worker.isRunning():
            return
        if action == "remove":
            answer = QMessageBox.question(
                self,
                "Remove Developer Environment",
                "Remove the kyth-ai-dev Distrobox? Downloaded models and your home directory files will be kept.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._ai_set_running(True)
        self._ai_status_lbl.setObjectName("status-muted")
        self._ai_status_lbl.setText(f"Running {action}...")
        self._ai_log_panel.reset()
        self._ai_log_panel.toggle.show()
        command = ["/usr/bin/kyth-ai-dev", action]
        self._ai_worker = Worker(command)
        self._ai_worker.line.connect(self._ai_on_line)
        self._ai_worker.done.connect(lambda code: self._ai_on_done(action, code))
        self._ai_worker.start()

    def _ai_on_line(self, line: str):
        self._ai_log_panel.append(line)

    def _ai_on_done(self, action: str, code: int):
        self._ai_set_running(False)
        ok = code == 0
        self._ai_status_lbl.setObjectName("status-ok" if ok else "status-err")
        if ok:
            labels = {
                "setup": "Developer & AI environment is ready. IDEs and tools exported.",
                "status": "Status check finished.",
                "start": "Local model service started.",
                "stop": "Local model service stopped.",
                "remove": "Developer environment removed; models were left in your home directory.",
            }
            self._ai_status_lbl.setText(labels.get(action, "Finished."))
        else:
            self._ai_status_lbl.setText(f"{action.capitalize()} failed (exit code {code}).")
        restyle(self._ai_status_lbl)

    def _ai_enter_box(self):
        try:
            popen(["konsole", "-e", "/usr/bin/kyth-ai-dev", "enter"])
        except Exception as exc:
            QMessageBox.warning(self, "Developer Environment", f"Could not open the developer shell:\n{exc}")
