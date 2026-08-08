import os
import shutil
from .services.launch import flatpak_run, popen
from .core_base import apply_install_badge, restyle
from .services.flatpak import _is_flatpak_installed
from .services.runtime import Worker, finish_worker
from .services.creator import (
    davinci_download_dir, davinci_flatpak_app_id, davinci_zip_candidates,
)
from .qt import (
    QDesktopServices, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QUrl, QVBoxLayout, QWidget, Qt,
)
from .widgets import CollapsibleLogPanel, _divider, _make_card


class _CreatorTabMixin:
    # ── Tab 4: Creator ────────────────────────────────────────────────────────

    def _build_creator_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        intro = QLabel(
            "Recording, streaming, video editing, and audio tools. "
            "AMD GPU + Mesa RADV gives excellent hardware acceleration in DaVinci Resolve."
        )
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._cr_tool_refs = []
        for i in range(0, len(self._CR_TOOLS), 2):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            for tool in self._CR_TOOLS[i:i + 2]:
                tile, refs = self._make_cr_tool_tile(tool)
                row_layout.addWidget(tile, 1)
                self._cr_tool_refs.append(refs)
            if len(self._CR_TOOLS[i:i + 2]) == 1:
                row_layout.addStretch(1)
            row_widget = QWidget()
            row_widget.setLayout(row_layout)
            layout.addWidget(row_widget)

        layout.addWidget(_divider())

        dv_section_head = QLabel("DaVinci Resolve")
        dv_section_head.setObjectName("section-heading")
        layout.addWidget(dv_section_head)
        dv_section_sub = QLabel(
            "Download the Linux ZIP from Blackmagic, then click Install from Download. "
            "Kyth will auto-detect the ZIP in your Downloads folder or let you pick it manually, "
            "then package Resolve as a local Flatpak for you."
        )
        dv_section_sub.setObjectName("card-copy")
        dv_section_sub.setWordWrap(True)
        layout.addWidget(dv_section_sub)

        dv_card, dv_layout = _make_card()
        dv_top = QHBoxLayout()
        dv_title = QLabel("DaVinci Resolve")
        dv_title.setObjectName("card-title")
        dv_top.addWidget(dv_title)
        dv_top.addStretch()
        self._dv_badge = QLabel()
        self._dv_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dv_top.addWidget(self._dv_badge)
        dv_layout.addLayout(dv_top)
        dv_desc = QLabel(
            "Professional non-linear video editor, color grader, visual effects, and audio "
            "post-production suite from Blackmagic Design. The free tier is industry-grade."
        )
        dv_desc.setObjectName("card-copy")
        dv_desc.setWordWrap(True)
        dv_layout.addWidget(dv_desc)
        dv_btn_row = QHBoxLayout()
        dv_btn_row.setSpacing(10)
        dv_dl_btn = QPushButton("Download from Blackmagic")
        dv_dl_btn.setObjectName("primary")
        dv_dl_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://www.blackmagicdesign.com/products/davinciresolve")
            )
        )
        dv_btn_row.addWidget(dv_dl_btn)
        self._dv_choose_btn = QPushButton("Choose ZIP…")
        self._dv_choose_btn.clicked.connect(self._pick_davinci_zip)
        dv_btn_row.addWidget(self._dv_choose_btn)
        self._dv_install_btn = QPushButton("Install from Download")
        self._dv_install_btn.setObjectName("primary")
        self._dv_install_btn.clicked.connect(self._install_davinci)
        dv_btn_row.addWidget(self._dv_install_btn)
        self._dv_launch_btn = QPushButton("Launch")
        self._dv_launch_btn.hide()
        self._dv_launch_btn.clicked.connect(self._launch_davinci)
        dv_btn_row.addWidget(self._dv_launch_btn)
        dv_btn_row.addStretch()
        dv_layout.addLayout(dv_btn_row)
        self._dv_zip_hint = QLabel()
        self._dv_zip_hint.setWordWrap(True)
        dv_layout.addWidget(self._dv_zip_hint)
        self._dv_op_status = QLabel()
        self._dv_op_status.hide()
        dv_layout.addWidget(self._dv_op_status)
        self._dv_progress = QProgressBar()
        self._dv_progress.setRange(0, 0)
        self._dv_progress.hide()
        dv_layout.addWidget(self._dv_progress)
        self._dv_log_panel = CollapsibleLogPanel(max_height=120)
        dv_layout.addWidget(self._dv_log_panel)
        layout.addWidget(dv_card)

        # ── Creator Capture Hub (Phase 8) ──
        layout.addWidget(self._make_creator_capture_hub_card())

        self._refresh_cr_status()
        return tab

    def _make_cr_tool_tile(self, tool: dict) -> tuple[QFrame, dict]:
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
        install_btn.clicked.connect(lambda _=False, t=tool: self._install_cr_tool(t))
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
            lambda _=False, t=tool: self._uninstall_cr_tool(t)
        )
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

        log_panel = CollapsibleLogPanel(max_height=100)
        layout.addWidget(log_panel)

        refs = {
            "tool": tool, "install": install_btn, "launch": launch_btn, "uninstall": uninstall_btn,
            "status": status_lbl, "progress": progress, "log_panel": log_panel,
        }
        return card, refs

    def _refresh_cr_status(self):
        for refs in self._cr_tool_refs:
            installed = _is_flatpak_installed(refs["tool"]["flatpak"])
            refs["install"].setVisible(not installed)
            refs["launch"].setVisible(installed)
            refs["uninstall"].setVisible(installed)

        if hasattr(self, "_dv_badge"):
            dv_installed = davinci_flatpak_app_id() is not None
            apply_install_badge(self._dv_badge, dv_installed)
            self._dv_install_btn.setVisible(not dv_installed)
            self._dv_launch_btn.setVisible(dv_installed)
            self._refresh_davinci_zip_hint()

    def _install_cr_tool(self, tool: dict):
        if self._cr_tool_worker and self._cr_tool_worker.isRunning():
            return
        active_refs = next(r for r in self._cr_tool_refs if r["tool"] is tool)
        self._cr_active_tool_refs = active_refs
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        self._dv_install_btn.setEnabled(False)
        log_panel = active_refs["log_panel"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log_panel.reset(f"→ flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo\n→ flatpak install -y flathub {tool['flatpak']}\n")
        progress.show()
        status_lbl.setText(f"Installing {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        restyle(status_lbl)
        self._cr_tool_worker = Worker([
            "bash", "-c",
            f"flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {tool['flatpak']}",
        ])
        self._cr_tool_worker.line.connect(log_panel.append)
        self._cr_tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_cr_tool_install_done(code, name)
        )
        self._cr_tool_worker.start()

    def _on_cr_tool_install_done(self, code: int, name: str):
        active_refs = self._cr_active_tool_refs
        active_refs["progress"].hide()
        finish_worker(self, attr="_cr_tool_worker")
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._dv_install_btn.setEnabled(True)
        if code == 0:
            active_refs["status"].setText(f"{name} installed.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log_panel"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Installation failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        restyle(active_refs["status"])
        self._refresh_cr_status()

    def _uninstall_cr_tool(self, tool: dict):
        if self._cr_tool_worker and self._cr_tool_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, f"Uninstall {tool['name']}",
            f"Remove {tool['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active_refs = next(r for r in self._cr_tool_refs if r["tool"] is tool)
        self._cr_active_tool_refs = active_refs
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        self._dv_install_btn.setEnabled(False)
        log_panel = active_refs["log_panel"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log_panel.reset(f"→ flatpak uninstall -y {tool['flatpak']}\n")
        progress.show()
        status_lbl.setText(f"Uninstalling {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        restyle(status_lbl)
        self._cr_tool_worker = Worker(
            ["flatpak", "uninstall", "-y", tool["flatpak"]]
        )
        self._cr_tool_worker.line.connect(log_panel.append)
        self._cr_tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_cr_tool_uninstall_done(code, name)
        )
        self._cr_tool_worker.start()

    def _on_cr_tool_uninstall_done(self, code: int, name: str):
        active_refs = self._cr_active_tool_refs
        active_refs["progress"].hide()
        finish_worker(self, attr="_cr_tool_worker")
        if code == 0:
            active_refs["status"].setText(f"{name} uninstalled.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log_panel"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Uninstall failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        restyle(active_refs["status"])
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._dv_install_btn.setEnabled(True)
        self._refresh_cr_status()

    def _make_creator_capture_hub_card(self) -> QFrame:
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Creator Capture Hub — OBS, HDR, microphone and Game Bar")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "One place for what creators notice first: OBS + obs-vkcapture, per-game HDR, PipeWire microphone routing, and Windows Game Bar equivalents (Win+G capture, Win+Alt+R record). GoXLR/Stream Deck profiles from your Windows drive are detected below when present."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        self._capture_status = QLabel("Click Scan Capture Stack to check OBS, HDR, and audio routing.")
        self._capture_status.setObjectName("card-copy")
        self._capture_status.setWordWrap(True)
        layout.addWidget(self._capture_status)
        self._capture_rows = QVBoxLayout()
        self._capture_rows.setSpacing(6)
        layout.addLayout(self._capture_rows)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        scan_btn = QPushButton("Scan Capture Stack")
        scan_btn.setObjectName("primary")
        scan_btn.clicked.connect(self._scan_capture_stack)
        btns.addWidget(scan_btn)
        obs_btn = QPushButton("Open OBS")
        obs_btn.clicked.connect(lambda _=False: popen(["flatpak", "run", "com.obsproject.Studio"]) if shutil.which("flatpak") else None)
        btns.addWidget(obs_btn)
        hdr_btn = QPushButton("HDR per-game")
        hdr_btn.clicked.connect(lambda _=False: popen(["/usr/bin/kyth-hdr-per-game"]) if os.path.exists("/usr/bin/kyth-hdr-per-game") else None)
        btns.addWidget(hdr_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _scan_capture_stack(self):
        from .services.runtime import DataWorker, release_worker_when_finished
        self._capture_status.setText("Scanning capture stack…")
        restyle(self._capture_status)
        while self._capture_rows.count():
            it = self._capture_rows.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        def _scan():
            try:
                from kyth_welcome.services.peripherals_hub import scan_peripherals
                peri = scan_peripherals()
                # Also probe OBS + GoXLR/OBS profile presence on Windows drives
                obs_installed = False
                try:
                    from kyth_welcome.services.flatpak import _is_flatpak_installed
                    obs_installed = _is_flatpak_installed("com.obsproject.Studio")
                except Exception:
                    pass
                goxlr_found = False
                try:
                    from kyth_welcome.services.gaming.windows_partitions import _probe_windows_partitions
                    for p in _probe_windows_partitions() or []:
                        mp = p.get("mountpoint") or ""
                        if mp and os.path.isdir(os.path.join(mp, "Users")):
                            # Look for GoXLR / TC-Helicon / Stream Deck profiles
                            for prof in (p.get("user_profiles") or []):
                                base = prof.get("path", "")
                                for rel in ("AppData/Local/TC-Helicon/GoXLR", "AppData/Roaming/Elgato/StreamDeck", "Documents/OBS Studio"):
                                    if os.path.isdir(os.path.join(base, rel)):
                                        goxlr_found = True
                except Exception:
                    pass
                return {"peripherals": peri, "obs": obs_installed, "goxlr": goxlr_found}
            except Exception as exc:
                return {"error": str(exc)}

        w = DataWorker("capture-scan", _scan)
        w.result.connect(self._on_capture_result)
        w.failed.connect(lambda _k, m: self._capture_status.setText(f"Scan failed: {m}"))
        self._capture_worker = w
        release_worker_when_finished(self, "_capture_worker", w)
        w.start()

    def _on_capture_result(self, _key: str, data: dict):
        if data.get("error"):
            self._capture_status.setText(f"Scan failed: {data['error']}")
            restyle(self._capture_status)
            return
        peri = data.get("peripherals") or {}
        hdr_detail = (peri.get("hdr") or {}).get("detail", "")
        audio_detail = (peri.get("audio") or {}).get("detail", "")
        obs = data.get("obs")
        goxlr = data.get("goxlr")
        rows = [
            ("OBS Studio", "Installed" if obs else "Not installed — install from tiles above", "ok" if obs else "warn"),
            ("HDR per-game", hdr_detail or "HDR probe unavailable", "ok"),
            ("Audio routing", audio_detail or "Audio probe unavailable", "ok"),
            ("Windows capture profiles", "GoXLR/Stream Deck/OBS profiles found on Windows drive — copy from Rescued Game Saves / Documents" if goxlr else "No GoXLR/Stream Deck profiles on mounted Windows drive", "ok" if goxlr else "dim"),
        ]
        for label, detail, status in rows:
            row = QFrame()
            row.setObjectName({"ok": "hw-card-ok", "warn": "hw-card-warn", "dim": "hw-card-dim"}.get(status, "hw-card-dim"))
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 7, 12, 7)
            rl.setSpacing(10)
            l = QLabel(label)
            l.setObjectName("card-subtitle")
            l.setMinimumWidth(150)
            rl.addWidget(l)
            d = QLabel(detail)
            d.setObjectName("card-copy")
            d.setWordWrap(True)
            rl.addWidget(d, 1)
            self._capture_rows.addWidget(row)
        self._capture_status.setText("Scan complete — use Open OBS / HDR per-game for the next step.")
        self._capture_status.setObjectName("status-ok")
        restyle(self._capture_status)

    def _pick_davinci_zip(self):
        start_dir = self._dv_selected_zip or davinci_download_dir()
        if os.path.isfile(start_dir):
            start_dir = os.path.dirname(start_dir)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select DaVinci Resolve Linux ZIP",
            start_dir,
            "ZIP archives (*.zip);;All Files (*)",
        )
        if not path:
            return
        self._dv_selected_zip = path
        self._refresh_davinci_zip_hint()

    def _refresh_davinci_zip_hint(self):
        selected = self._dv_selected_zip
        if selected and os.path.isfile(selected):
            self._dv_zip_hint.setText(f"Selected ZIP: {selected}")
            self._dv_zip_hint.setObjectName("status-ok")
            restyle(self._dv_zip_hint)
            return

        self._dv_selected_zip = None
        candidates = davinci_zip_candidates()
        if candidates:
            self._dv_zip_hint.setText(f"Auto-detected ZIP: {candidates[0]}")
            self._dv_zip_hint.setObjectName("status-dim")
        else:
            self._dv_zip_hint.setText(
                f"No DaVinci ZIP found yet. Download it to {davinci_download_dir()} or click Choose ZIP…"
            )
            self._dv_zip_hint.setObjectName("status-warn")
        restyle(self._dv_zip_hint)

    def _launch_davinci(self):
        app_id = davinci_flatpak_app_id()
        if not app_id:
            QMessageBox.warning(self, "DaVinci Resolve", "DaVinci Resolve is not installed yet.")
            return
        flatpak_run(app_id)

    def _install_davinci(self):
        if self._dv_worker and self._dv_worker.isRunning():
            return

        if not shutil.which("flatpak-builder"):
            self._dv_log_panel.reset("Missing required tool: flatpak-builder\n")
            self._dv_log_panel.append("Update KythOS to the latest image, then try again.\n")
            self._dv_op_status.setText(
                "DaVinci installer tools are missing. Please run a system update first."
            )
            self._dv_op_status.setObjectName("status-warn")
            self._dv_op_status.show()
            restyle(self._dv_op_status)
            return

        zip_path = self._dv_selected_zip if self._dv_selected_zip and os.path.isfile(self._dv_selected_zip) else ""
        if not zip_path:
            candidates = davinci_zip_candidates()
            zip_path = candidates[0] if candidates else ""
        if not zip_path:
            self._dv_log_panel.reset("No DaVinci Resolve Linux ZIP was found.\n")
            self._dv_log_panel.append(
                f"Download the ZIP from Blackmagic to {davinci_download_dir()} or click Choose ZIP… and retry.\n"
            )
            self._dv_op_status.setText("Download the Linux ZIP first, or choose it manually.")
            self._dv_op_status.setObjectName("status-warn")
            self._dv_op_status.show()
            restyle(self._dv_op_status)
            QMessageBox.warning(
                self,
                "DaVinci Resolve",
                "I couldn't find the downloaded Linux ZIP automatically.\n\n"
                "Download it from Blackmagic first, or click “Choose ZIP…” and select it manually.",
            )
            return

        self._dv_selected_zip = zip_path
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(False)
        self._dv_install_btn.setEnabled(False)
        self._dv_choose_btn.setEnabled(False)
        self._dv_log_panel.reset(f"→ /usr/bin/kyth-davinci-install {zip_path}\n")
        self._dv_log_panel.append(
            "Kyth will repackage the official Blackmagic download as a user Flatpak. "
            "The first build can take a few minutes.\n"
        )
        self._dv_progress.show()
        self._dv_op_status.setText("Building and installing DaVinci Resolve…")
        self._dv_op_status.setObjectName("subheading")
        self._dv_op_status.show()
        restyle(self._dv_op_status)
        self._dv_worker = Worker(["/usr/bin/kyth-davinci-install", zip_path])
        self._dv_worker.line.connect(self._dv_log_panel.append)
        self._dv_worker.done.connect(self._on_davinci_install_done)
        self._dv_worker.start()

    def _on_davinci_install_done(self, code: int):
        self._dv_progress.hide()
        finish_worker(self, attr="_dv_worker")
        for refs in self._cr_tool_refs:
            refs["install"].setEnabled(True)
        self._dv_install_btn.setEnabled(True)
        self._dv_choose_btn.setEnabled(True)
        installed = davinci_flatpak_app_id() is not None
        if code == 0 and installed:
            self._dv_op_status.setText("DaVinci Resolve installed. Launch it from here or the app menu.")
            self._dv_op_status.setObjectName("status-ok")
            self._dv_log_panel.append("\nDone.")
        else:
            self._dv_op_status.setText(
                f"Installation failed (exit {code}). Check the details below — a fresh ZIP or system update may be needed."
            )
            self._dv_op_status.setObjectName("status-err")
        restyle(self._dv_op_status)
        self._refresh_cr_status()
