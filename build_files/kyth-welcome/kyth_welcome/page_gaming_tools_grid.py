# __KYTH_GENERATED_IMPORTS__
from .core_base import cancel_worker, restyle
from .services.launch import popen
from .services.runtime import Worker, finish_worker
from .qt import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
)
from .widgets import CollapsibleLogPanel, _make_card


class _ToolsGridMixin:
    """The 2-column install/launch/uninstall grid of GAMING_TOOLS flatpak tiles."""

    def _build_tools_grid(self):
        self._tool_refs: list[dict] = []
        for i in range(0, len(self._TOOLS), 2):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            for tool in self._TOOLS[i:i + 2]:
                tile, refs = self._make_tool_tile(tool)
                row_layout.addWidget(tile, 1)
                self._tool_refs.append(refs)
            # Pad the last row if odd number of tools
            if len(self._TOOLS[i:i + 2]) == 1:
                row_layout.addStretch(1)
            self._add_layout(row_layout)

        self._tool_worker = None
        self._active_tool_refs = None

    def _make_tool_tile(self, tool: dict) -> tuple[QFrame, dict]:
        card, layout = _make_card()
        layout.setSpacing(8)

        name_lbl = QLabel(tool["name"])
        name_lbl.setObjectName("card-title")
        layout.addWidget(name_lbl)

        desc_lbl = QLabel(tool["desc"])
        desc_lbl.setObjectName("card-copy")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        install_btn = QPushButton("Install")
        install_btn.clicked.connect(
            lambda _=False, t=tool: self._install_tool(t)
        )
        btn_row.addWidget(install_btn)
        launch_btn = QPushButton("Launch")
        launch_btn.hide()
        launch_btn.clicked.connect(
            lambda _=False, cmd=tool["launch"]: popen(cmd)
        )
        btn_row.addWidget(launch_btn)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setObjectName("danger")
        uninstall_btn.hide()
        uninstall_btn.clicked.connect(
            lambda _=False, t=tool: self._uninstall_tool(t)
        )
        btn_row.addWidget(uninstall_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.hide()
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        status_lbl = QLabel()
        status_lbl.setObjectName("subheading")
        status_lbl.hide()
        layout.addWidget(status_lbl)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.hide()
        layout.addWidget(progress)

        log_panel = CollapsibleLogPanel(max_height=100)
        layout.addWidget(log_panel)

        refs = {
            "tool": tool, "install": install_btn, "launch": launch_btn, "uninstall": uninstall_btn,
            "cancel": cancel_btn, "status": status_lbl, "progress": progress,
            "log_panel": log_panel,
        }
        cancel_btn.clicked.connect(lambda _=False, r=refs: self._cancel_tool_operation(r))
        return card, refs

    def _install_tool(self, tool: dict):
        if self._tool_worker and self._tool_worker.isRunning():
            return
        active_refs = next(r for r in self._tool_refs if r["tool"] is tool)
        self._active_tool_refs = active_refs
        for refs in self._tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log_panel = active_refs["log_panel"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log_panel.reset(
            f"→ flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo\n→ flatpak install -y flathub {tool['flatpak']}\n"
        )
        progress.show()
        status_lbl.setText(f"Installing {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        restyle(status_lbl)
        active_refs["cancel"].setEnabled(True)
        active_refs["cancel"].show()
        self._tool_worker = Worker([
            "bash", "-c",
            f"flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {tool['flatpak']}",
        ])
        self._tool_worker.line.connect(log_panel.append)
        self._tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_tool_install_done(code, name)
        )
        self._tool_worker.start()

    def _on_tool_install_done(self, code: int, name: str):
        active_refs = self._active_tool_refs
        active_refs["progress"].hide()
        active_refs["cancel"].hide()
        finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            active_refs["status"].setText(f"{name} installation cancelled.")
            active_refs["status"].setObjectName("status-warn")
            active_refs["log_panel"].append("\nCancelled.")
        elif code == 0:
            active_refs["status"].setText(f"{name} installed.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log_panel"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Installation failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        restyle(active_refs["status"])
        for refs in self._tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._refresh_status()

    def _cancel_tool_operation(self, refs: dict):
        if refs is not self._active_tool_refs:
            return
        reply = QMessageBox.question(
            self,
            "Cancel App Operation?",
            "Stop the running Flatpak operation? Any apps that already finished changing will keep their current state.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cancel_worker(
            self,
            attr="_tool_worker",
            status_lbl=refs["status"],
            log=refs["log_panel"].log,
            cancel_btn=refs["cancel"],
            message="Cancelling app operation…",
        )

    def _uninstall_tool(self, tool: dict):
        if self._tool_worker and self._tool_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, f"Uninstall {tool['name']}",
            f"Remove {tool['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active_refs = next(r for r in self._tool_refs if r["tool"] is tool)
        self._active_tool_refs = active_refs
        for refs in self._tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log_panel = active_refs["log_panel"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log_panel.reset(f"→ flatpak uninstall -y {tool['flatpak']}\n")
        progress.show()
        status_lbl.setText(f"Uninstalling {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        restyle(status_lbl)
        active_refs["cancel"].setEnabled(True)
        active_refs["cancel"].show()
        self._tool_worker = Worker(
            ["flatpak", "uninstall", "-y", tool["flatpak"]]
        )
        self._tool_worker.line.connect(log_panel.append)
        self._tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_tool_uninstall_done(code, name)
        )
        self._tool_worker.start()

    def _on_tool_uninstall_done(self, code: int, name: str):
        active_refs = self._active_tool_refs
        active_refs["progress"].hide()
        active_refs["cancel"].hide()
        finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            active_refs["status"].setText(f"{name} uninstall cancelled.")
            active_refs["status"].setObjectName("status-warn")
            active_refs["log_panel"].append("\nCancelled.")
        elif code == 0:
            active_refs["status"].setText(f"{name} uninstalled.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log_panel"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Uninstall failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        restyle(active_refs["status"])
        for refs in self._tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._refresh_status()
