import os
import shutil
from datetime import datetime

# __KYTH_GENERATED_IMPORTS__
from .core_base import cancel_worker, restyle
from .services.gaming import heroic_epic_launcher_command, lutris_installer_command
from .services.launch import popen
from .services.flatpak import _is_flatpak_installed
from .services.runtime import Worker, guard_disposed, finish_worker, guard_disposed
from .qt import QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton
from .widgets import CollapsibleLogPanel, _make_card


class _LauncherToolsMixin:
    """Heroic/Lutris-backed installers for Epic, Battle.net, EA App, and Ubisoft Connect."""

    def _build_launcher_setup_card(self):
        self._divider()
        launcher_head = QLabel("Launcher setup")
        launcher_head.setObjectName("card-title")
        self._add(launcher_head)
        launcher_sub = QLabel(
            "Heroic is the recommended default for Epic and GOG. "
            "Install Lutris above, then use the buttons below to start Lutris installers for Battle.net, EA App, and Ubisoft Connect."
        )
        launcher_sub.setObjectName("card-copy")
        launcher_sub.setWordWrap(True)
        self._add(launcher_sub)

        launcher_card, launcher_layout = _make_card()
        launcher_note = QLabel(
            "Recommended pairing: Heroic for Epic/GOG/Amazon libraries, Lutris (install above) for Battle.net, EA App, and Ubisoft Connect, and Bottles for standalone .exe / .msi installers."
        )
        launcher_note.setObjectName("card-copy")
        launcher_note.setWordWrap(True)
        launcher_layout.addWidget(launcher_note)

        launcher_btns = QHBoxLayout()
        launcher_btns.setSpacing(8)

        epic_btn = QPushButton("Open Heroic for Epic")
        epic_btn.clicked.connect(lambda _=False: self._open_heroic_for_epic())
        launcher_btns.addWidget(epic_btn)

        battlenet_btn = QPushButton("Install Battle.net")
        battlenet_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("battlenet", "Battle.net")
        )
        launcher_btns.addWidget(battlenet_btn)

        ea_btn = QPushButton("Install EA App")
        ea_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("lutris:ea-app-standard", "EA App")
        )
        launcher_btns.addWidget(ea_btn)

        ubisoft_btn = QPushButton("Install Ubisoft Connect")
        ubisoft_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("lutris:ubisoft-connect-latest", "Ubisoft Connect")
        )
        launcher_btns.addWidget(ubisoft_btn)

        launcher_btns.addStretch()
        launcher_layout.addLayout(launcher_btns)

        # Launcher status / log (used by Open Heroic / Lutris installer buttons)
        self._tool_op_status = QLabel()
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.hide()
        launcher_layout.addWidget(self._tool_op_status)
        self._tool_progress = QProgressBar()
        self._tool_progress.setRange(0, 0)
        self._tool_progress.hide()
        launcher_layout.addWidget(self._tool_progress)
        self._tool_cancel_btn = QPushButton("Cancel")
        self._tool_cancel_btn.clicked.connect(self._cancel_launcher_tool_operation)
        self._tool_cancel_btn.hide()
        launcher_layout.addWidget(self._tool_cancel_btn)
        self._tool_log_panel = CollapsibleLogPanel(max_height=120)
        launcher_layout.addWidget(self._tool_log_panel)
        self._add(launcher_card)

    def _open_heroic_for_epic(self):
        cmd = heroic_epic_launcher_command()
        self._tool_log_panel.reset(f"→ {' '.join(cmd)}\n")
        self._tool_log_panel.append("Heroic should open. Sign in to Epic Games there to install your library.")
        self._tool_progress.hide()
        self._tool_op_status.setText("Opening Heroic Games Launcher…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        restyle(self._tool_op_status)

        try:
            popen(cmd)
            self._tool_op_status.setText("Heroic opened for Epic sign-in.")
            self._tool_op_status.setObjectName("status-ok")
            restyle(self._tool_op_status)
        except Exception as exc:
            self._tool_log_panel.append(f"\nFailed to start Heroic: {exc}")
            self._tool_op_status.setText("Failed to open Heroic.")
            self._tool_op_status.setObjectName("status-err")
            restyle(self._tool_op_status)
            QMessageBox.warning(self, "Heroic Games Launcher", str(exc))

    def _prepare_epic_lutris_install(self) -> bool:
        prefix = os.path.expanduser("~/Games/epic-games-store")
        cache = os.path.expanduser("~/.cache/lutris/installer/epic-games-store")
        found_paths = [path for path in (prefix, cache) if os.path.exists(path)]
        if not found_paths:
            return True

        notes = []
        winetricks_log = os.path.join(prefix, "winetricks.log")
        if os.path.isfile(winetricks_log):
            try:
                with open(winetricks_log, "r", encoding="utf-8", errors="ignore") as fh:
                    if "corefonts" in fh.read():
                        notes.append("Winetricks already ran in the old Epic prefix (corefonts found).")
            except OSError:
                pass

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Reset old Epic installer state?")
        box.setText(
            "A previous Epic install attempt was found. Lutris/UMU can fail when it reuses a partial Epic prefix."
        )
        detail_lines = []
        detail_lines.extend(notes)
        detail_lines.extend([f"Found: {path}" for path in found_paths])
        detail_lines.append("")
        detail_lines.append("Choose 'Reset and Retry' to move the old state aside and reopen the installer.")
        box.setInformativeText("\n".join(detail_lines))
        reset_btn = box.addButton("Reset and Retry", QMessageBox.ButtonRole.AcceptRole)
        open_btn = box.addButton("Open Anyway", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(reset_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked == cancel_btn:
            self._tool_op_status.setText("Epic installer launch cancelled.")
            self._tool_op_status.setObjectName("subheading")
            self._tool_op_status.show()
            restyle(self._tool_op_status)
            return False
        if clicked == open_btn:
            return True

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._tool_log_panel.reset("Preparing a clean Epic installer retry…\n")
        for path in found_paths:
            backup = f"{path}.bak-{timestamp}"
            try:
                shutil.move(path, backup)
                self._tool_log_panel.append(f"Moved {path} → {backup}")
            except Exception as exc:
                self._tool_log_panel.append(f"Failed to move {path}: {exc}")
                self._tool_op_status.setText("Epic installer reset failed.")
                self._tool_op_status.setObjectName("status-err")
                self._tool_op_status.show()
                restyle(self._tool_op_status)
                QMessageBox.warning(
                    self,
                    "Epic installer reset",
                    f"Could not move {path}:\n{exc}"
                )
                return False

        self._tool_log_panel.append("\nOld installer state was backed up. Relaunching Lutris…")
        self._tool_op_status.setText("Old Epic installer state was backed up. Retrying…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        restyle(self._tool_op_status)
        return True

    def _launch_lutris_installer(self, target: str, name: str):
        if not _is_flatpak_installed("net.lutris.Lutris"):
            self._tool_op_status.setText("Lutris is not installed.")
            self._tool_op_status.setObjectName("status-err")
            self._tool_op_status.show()
            restyle(self._tool_op_status)
            QMessageBox.warning(
                self,
                "Lutris not found",
                f"Lutris is required to install {name}.\n\nInstall it from the Gaming Tools section above."
            )
            return

        if not shutil.which("umu-run"):
            if self._tool_worker and self._tool_worker.isRunning():
                return
            self._tool_log_panel.reset("→ ujust install-umu\n")
            self._tool_progress.show()
            self._tool_cancel_btn.setEnabled(True)
            self._tool_cancel_btn.show()
            self._tool_op_status.setText("umu-launcher not found — installing automatically…")
            self._tool_op_status.setObjectName("subheading")
            self._tool_op_status.show()
            restyle(self._tool_op_status)
            self._tool_worker = Worker(["ujust", "install-umu"])
            self._tool_worker.finished.connect(lambda: setattr(self, "_tool_worker", None))
            self._tool_worker.finished.connect(self._tool_worker.deleteLater)
            self._tool_worker.line.connect(guard_disposed(self._tool_log_panel.append))
            self._tool_worker.done.connect(
            guard_disposed(lambda code, t=target, n=name: self._on_umu_install_done(code, t, n))
            )
            self._tool_worker.start()
            return

        self._tool_log_panel.reset()
        if target == "epic-games-store" and not self._prepare_epic_lutris_install():
            return

        lutris_target = target if target.startswith("lutris:") else f"lutris:install/{target}"
        cmd = lutris_installer_command(lutris_target)
        self._tool_log_panel.reset(f"→ {' '.join(cmd)}\n")
        self._tool_log_panel.append("Lutris should open the installer dialog.")
        self._tool_progress.hide()
        self._tool_op_status.setText(f"Opening {name} installer in Lutris…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        restyle(self._tool_op_status)

        try:
            popen(cmd)
            self._tool_op_status.setText(f"{name} installer opened in Lutris.")
            self._tool_op_status.setObjectName("status-ok")
            restyle(self._tool_op_status)
        except Exception as exc:
            self._tool_log_panel.append(f"\nFailed to start Lutris: {exc}")
            self._tool_op_status.setText(f"Failed to open {name} installer.")
            self._tool_op_status.setObjectName("status-err")
            restyle(self._tool_op_status)
            QMessageBox.warning(self, f"{name} installer", str(exc))

    def _on_umu_install_done(self, code: int, target: str, name: str):
        self._tool_progress.hide()
        self._tool_cancel_btn.hide()
        finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            self._tool_op_status.setText("umu-launcher installation cancelled.")
            self._tool_op_status.setObjectName("status-warn")
            restyle(self._tool_op_status)
            return
        if code != 0:
            self._tool_op_status.setText("umu-launcher installation failed.")
            self._tool_op_status.setObjectName("status-err")
            restyle(self._tool_op_status)
            return
        self._tool_log_panel.append("\numu-launcher installed. Proceeding with installer…")
        self._launch_lutris_installer(target, name)

    def _cancel_launcher_tool_operation(self):
        reply = QMessageBox.question(
            self,
            "Cancel Tool Install?",
            "Stop installing the launcher support tool? You can retry when you are ready.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cancel_worker(
            self,
            attr="_tool_worker",
            status_lbl=self._tool_op_status,
            log=self._tool_log_panel.log,
            cancel_btn=self._tool_cancel_btn,
            message="Cancelling tool install…",
        )