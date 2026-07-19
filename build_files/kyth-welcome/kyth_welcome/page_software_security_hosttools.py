# __KYTH_GENERATED_IMPORTS__
from .core_base import _restyle
from .services.launch import popen
from .services.software import Worker, _finish_worker, _is_flatpak_installed
from .qt import QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QTextEdit, QWidget
from .widgets import _make_card, _set_log_panel


class _HostSecurityToolsMixin:
    """Native (Flatpak) host-side security tools grid: install, launch, uninstall."""

    def _build_host_tools_grid(self, layout):
        host_head = QLabel("Host-side Security Tools")
        host_head.setObjectName("heading")
        host_head.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        layout.addWidget(host_head)
        host_sub = QLabel(
            "These tools run natively on KythOS as Flatpaks — better Wayland integration "
            "and no container overhead for GUI-heavy workflows."
        )
        host_sub.setObjectName("card-copy")
        host_sub.setWordWrap(True)
        layout.addWidget(host_sub)

        self._sec_host_tool_refs = []
        for i in range(0, len(self._SEC_HOST_TOOLS), 2):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            for tool in self._SEC_HOST_TOOLS[i:i + 2]:
                tile, refs = self._make_sec_host_tool_tile(tool)
                row_layout.addWidget(tile, 1)
                self._sec_host_tool_refs.append(refs)
            if len(self._SEC_HOST_TOOLS[i:i + 2]) == 1:
                row_layout.addStretch(1)
            row_widget = QWidget()
            row_widget.setLayout(row_layout)
            layout.addWidget(row_widget)

    def _refresh_sec_host_tools_status(self):
        if not hasattr(self, "_sec_host_tool_refs"):
            return
        for refs in self._sec_host_tool_refs:
            fp_installed = _is_flatpak_installed(refs["tool"]["flatpak"])
            refs["install"].setVisible(not fp_installed)
            refs["launch"].setVisible(fp_installed)
            refs["uninstall"].setVisible(fp_installed)

    def _make_sec_host_tool_tile(self, tool: dict) -> tuple[QFrame, dict]:
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
        install_btn.setObjectName("primary")
        install_btn.clicked.connect(lambda _=False, t=tool: self._sec_install_host_tool(t))
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
        uninstall_btn.clicked.connect(lambda _=False, t=tool: self._sec_uninstall_host_tool(t))
        btn_row.addWidget(uninstall_btn)
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

        log_toggle = QPushButton("Show details")
        log_toggle.setCheckable(True)
        log_toggle.hide()
        layout.addWidget(log_toggle)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setMaximumHeight(100)
        log.hide()
        layout.addWidget(log)

        log_toggle.clicked.connect(
            lambda checked, lt=log_toggle, lg=log: _set_log_panel(lt, lg, checked)
        )

        refs = {
            "tool": tool, "install": install_btn, "launch": launch_btn,
            "uninstall": uninstall_btn, "status": status_lbl,
            "progress": progress, "log_toggle": log_toggle, "log": log,
        }
        return card, refs

    def _sec_install_host_tool(self, tool: dict):
        if self._sec_host_tool_worker and self._sec_host_tool_worker.isRunning():
            return
        active_refs = next(r for r in self._sec_host_tool_refs if r["tool"] is tool)
        self._sec_active_host_refs = active_refs
        for refs in self._sec_host_tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(
            f"→ flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo\n"
            f"→ flatpak install -y flathub {tool['flatpak']}\n"
        )
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Installing {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        self._sec_host_tool_worker = Worker([
            "bash", "-c",
            f"flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {tool['flatpak']}",
        ])
        self._sec_host_tool_worker.line.connect(lambda ln: (
            log.append(ln), log.ensureCursorVisible(),
        ))
        self._sec_host_tool_worker.done.connect(
            lambda code, name=tool["name"]: self._sec_on_host_tool_install_done(code, name)
        )
        self._sec_host_tool_worker.start()

    def _sec_on_host_tool_install_done(self, code: int, name: str):
        active_refs = self._sec_active_host_refs
        active_refs["progress"].hide()
        _finish_worker(self, attr="_sec_host_tool_worker")
        for refs in self._sec_host_tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        if code == 0:
            active_refs["status"].setText(f"{name} installed.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Installation failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        self._refresh_sec_host_tools_status()

    def _sec_uninstall_host_tool(self, tool: dict):
        if self._sec_host_tool_worker and self._sec_host_tool_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, f"Uninstall {tool['name']}",
            f"Remove {tool['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active_refs = next(r for r in self._sec_host_tool_refs if r["tool"] is tool)
        self._sec_active_host_refs = active_refs
        for refs in self._sec_host_tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(f"→ flatpak uninstall -y {tool['flatpak']}\n")
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Uninstalling {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        self._sec_host_tool_worker = Worker(["flatpak", "uninstall", "-y", tool["flatpak"]])
        self._sec_host_tool_worker.line.connect(lambda ln: (
            log.append(ln), log.ensureCursorVisible(),
        ))
        self._sec_host_tool_worker.done.connect(
            lambda code, name=tool["name"]: self._sec_on_host_tool_uninstall_done(code, name)
        )
        self._sec_host_tool_worker.start()

    def _sec_on_host_tool_uninstall_done(self, code: int, name: str):
        active_refs = self._sec_active_host_refs
        active_refs["progress"].hide()
        _finish_worker(self, attr="_sec_host_tool_worker")
        for refs in self._sec_host_tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        if code == 0:
            active_refs["status"].setText(f"{name} uninstalled.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Uninstall failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        self._refresh_sec_host_tools_status()
