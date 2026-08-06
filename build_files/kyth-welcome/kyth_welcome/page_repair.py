import os
import shutil

# __KYTH_GENERATED_IMPORTS__
from .services.bootc import bootc_image_timestamp, has_rollback_deployment
from .page_repair_components import repair_overview_cards, rollback_card
from .services.launch import kcmshell, popen_privileged
from .services.desktop import REFRESH_DESKTOP_DATABASE_SH
from .services.hardware import detect_nvidia_async
from .services.repair import _read_sys_text, quick_fixes, sleep_mode_label
from .services.flatpak import _is_flatpak_installed
from .services.privileged import systemctl_action
from .services.runtime import DataWorker
from .page_repair_assist import _AssistMixin
from .page_repair_quick import _QuickFixMixin
from .page_repair_reset import _ResetMixin
from .qt import (
    QDesktopServices, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QUrl, single_shot,
)
from .widgets import (
    CollapsibleLogPanel, FlowLayout, Page, _make_card, _make_tip_card,
)


class RepairPage(Page, _QuickFixMixin, _AssistMixin, _ResetMixin):
    def __init__(self, navigate=None):
        super().__init__()
        self._worker = None
        self._snapshot_worker = None
        self._assist_worker = None
        self._setup_worker = None
        # Safe default — has_rollback_deployment() and bootc_image_timestamp()
        # are subprocess-backed. RepairPage is built lazily (on first visit,
        # not at app startup like WelcomePage), but it must still not block
        # on them here; _refresh_rollback_state() below fetches the real
        # values on a background thread and rebuilds the card in place.
        self._has_rollback = False
        self._rollback_timestamp = None
        self._rollback_state_worker = None
        self._nvidia_probe_worker = None
        self._setup_operation = ""
        self._navigate = navigate or (lambda _key: None)

        self._page_header(
            "System",
            "Repair",
            "Reset the OS back to a clean KythOS state. Your personal files in /home are never touched.",
        )

        for card in repair_overview_cards(self._navigate):
            self._add(card)
        self._rollback_insert_index = self._layout.count()
        self._rollback_card, self._rollback_repair_btn = rollback_card(
            self._has_rollback, self._run_rollback, self._navigate, self._rollback_timestamp
        )
        self._add(self._rollback_card)

        self._build_quick_fixes_card()
        self._build_assist_card()
        self._build_printer_card()
        self._build_backup_card()
        self._build_restore_setup_card()
        self._build_snapshot_card()
        self._build_reinstall_card()
        self._build_warning_card()
        self._build_reset_controls()
        self._build_sleep_diagnostics_card()

        self._stretch()
        single_shot(self, 0, self._refresh_rollback_state)
        single_shot(self, 0, self._refresh_nvidia_quick_fixes)

    @staticmethod
    def _fetch_rollback_state() -> tuple[bool, str | None]:
        """Run off the GUI thread by _refresh_rollback_state()'s DataWorker."""
        has_rollback = has_rollback_deployment()
        timestamp = bootc_image_timestamp("rollback") if has_rollback else None
        return has_rollback, timestamp

    def _refresh_rollback_state(self):
        if self._rollback_state_worker is not None:
            return
        self._rollback_state_worker = DataWorker("repair-rollback-state", self._fetch_rollback_state)
        self._rollback_state_worker.result.connect(self._on_rollback_state_ready)
        self._rollback_state_worker.failed.connect(lambda _key, _message: None)
        self._rollback_state_worker.finished.connect(lambda: setattr(self, "_rollback_state_worker", None))
        self._rollback_state_worker.start()

    def _on_rollback_state_ready(self, _key: str, data: object):
        has_rollback, timestamp = data
        self._has_rollback = has_rollback
        self._rollback_timestamp = timestamp
        new_card, new_btn = rollback_card(has_rollback, self._run_rollback, self._navigate, timestamp)
        self._layout.removeWidget(self._rollback_card)
        self._rollback_card.deleteLater()
        self._layout.insertWidget(self._rollback_insert_index, new_card)
        self._rollback_card = new_card
        self._rollback_repair_btn = new_btn

    def _refresh_nvidia_quick_fixes(self):
        detect_nvidia_async(self, self._on_nvidia_quick_fixes_ready)

    def _on_nvidia_quick_fixes_ready(self, has_nvidia: bool):
        if not has_nvidia:
            return
        nvidia_status_btn = QPushButton("NVIDIA Status")
        nvidia_status_btn.setToolTip("Show current NVIDIA driver build status and kernel module load state.")
        nvidia_status_btn.clicked.connect(
            lambda _=False: self._run_quick_fix("NVIDIA Status", ["/usr/bin/kyth-nvidia-status"])
        )
        self._quick_btns.addWidget(nvidia_status_btn)
        nvidia_fix_btn = QPushButton("Retry NVIDIA Build")
        nvidia_fix_btn.setToolTip("Open the NVIDIA Drivers page to retry the kernel module build.")
        nvidia_fix_btn.clicked.connect(lambda _=False: self._navigate("NVIDIA"))
        self._quick_btns.addWidget(nvidia_fix_btn)

    def _build_quick_fixes_card(self) -> None:
        quick, quick_layout = _make_card("card-accent-ok")
        quick_title = QLabel("Quick fixes")
        quick_title.setObjectName("card-title")
        quick_layout.addWidget(quick_title)
        quick_body = QLabel(
            "Try these first. They are non-destructive and aimed at the common "
            "new-desktop moments: app menu entries missing, Flatpaks acting odd, "
            "audio disappearing, or needing a familiar Task Manager."
        )
        quick_body.setObjectName("card-copy")
        quick_body.setWordWrap(True)
        quick_layout.addWidget(quick_body)
        quick_btns = FlowLayout(spacing=8)
        panic_btn = QPushButton("Panic Button")
        panic_btn.setObjectName("primary")
        panic_btn.setToolTip("Run the safe repair bundle: app menu, user polish, Flatpak repair, audio restart, and snapshot.")
        panic_btn.clicked.connect(lambda _=False: self._run_quick_fix("Panic Button", [
            "bash", "-c",
            "set -e; "
            f"{REFRESH_DESKTOP_DATABASE_SH}; "
            "/usr/bin/kyth-user-polish 2>/dev/null || true; "
            "flatpak repair --user 2>/dev/null || true; "
            "systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || true; "
            "/usr/bin/kyth-session-snapshot"
        ]))
        quick_btns.addWidget(panic_btn)
        for fix in quick_fixes():
            btn = QPushButton(fix.label)
            btn.setToolTip(fix.tooltip)
            btn.clicked.connect(
                lambda _=False, f=fix: self._run_quick_fix(f.label, list(f.command))
            )
            quick_btns.addWidget(btn)
        # NVIDIA Status/Retry Build buttons are added later, once
        # _refresh_nvidia_quick_fixes() confirms a GPU is actually present
        # (see __init__) — detecting it is an lspci call, so it must not
        # block this constructor. FlowLayout only supports appending, so
        # they land at the end of the row instead of here once revealed,
        # not mid-row like the other quick fixes.
        self._quick_btns = quick_btns
        task_btn = QPushButton("Open Task Manager")
        task_btn.setObjectName("primary")
        task_btn.setToolTip("Launch the system task manager to inspect running processes and resource usage.")
        task_btn.clicked.connect(self._open_task_manager)
        quick_btns.addWidget(task_btn)
        printer_btn = QPushButton("Setup Printer")
        printer_btn.setToolTip("Enable CUPS and open KDE Printer Settings. Most USB and network printers are detected automatically.")
        printer_btn.clicked.connect(self._open_printer_setup)
        quick_btns.addWidget(printer_btn)
        mixer_btn = QPushButton("Open Volume Mixer")
        mixer_btn.setToolTip("Open per-app volume controls — for familiar per-app mixing.")
        mixer_btn.clicked.connect(self._open_volume_mixer)
        quick_btns.addWidget(mixer_btn)
        defaults_btn = QPushButton("Manage Default Apps")
        defaults_btn.setToolTip("Choose which app opens PDFs, images, video, email, and other file types.")
        defaults_btn.clicked.connect(lambda _=False: kcmshell("filetypes")
            if shutil.which("kcmshell6") else QDesktopServices.openUrl(QUrl("settings://filetypes")))
        quick_btns.addWidget(defaults_btn)
        startup_btn = QPushButton("Manage Startup Apps")
        startup_btn.setToolTip("Control which apps launch at login — for familiar startup-app management.")
        startup_btn.clicked.connect(lambda _=False: kcmshell("autostart")
            if shutil.which("kcmshell6") else None)
        quick_btns.addWidget(startup_btn)
        exe_fix_btn = QPushButton("Fix .exe Files")
        exe_fix_btn.setToolTip(
            "Set Bottles as the default handler for .exe and .msi files, "
            "so double-clicking them opens Bottles instead of the archive manager."
        )
        exe_fix_btn.clicked.connect(self._fix_exe_association)
        quick_btns.addWidget(exe_fix_btn)
        clipboard_btn = QPushButton("Enable Clipboard History")
        clipboard_btn.setToolTip(
            "Turn on KDE clipboard history (Klipper) so you can access recently copied text "
            "— equivalent to a familiar clipboard history tool."
        )
        clipboard_btn.clicked.connect(self._enable_clipboard_history)
        quick_btns.addWidget(clipboard_btn)
        nightlight_btn = QPushButton("Night Light Settings")
        nightlight_btn.setToolTip("Open KDE Night Light / blue light filter settings to set a schedule.")
        nightlight_btn.clicked.connect(self._open_night_light)
        quick_btns.addWidget(nightlight_btn)
        quick_layout.addLayout(quick_btns)
        self._add(quick)

    def _build_assist_card(self) -> None:
        assist_card, assist_layout = _make_card("card-accent-ok")
        assist_title = QLabel("Quick Assist — get or give remote help")
        assist_title.setObjectName("card-title")
        assist_layout.addWidget(assist_title)
        assist_body = QLabel(
            "RustDesk lets a trusted person view or control this PC using a temporary ID "
            "and one-time password. KRDC connects outward to another PC over RDP or VNC. "
            "Stay at the computer, read every permission prompt, and end the session when done."
        )
        assist_body.setObjectName("card-copy")
        assist_body.setWordWrap(True)
        assist_layout.addWidget(assist_body)
        assist_btns = QHBoxLayout()
        assist_btns.setSpacing(8)
        self._rustdesk_btn = QPushButton()
        self._rustdesk_btn.setObjectName("primary")
        self._rustdesk_btn.clicked.connect(self._open_or_install_rustdesk)
        assist_btns.addWidget(self._rustdesk_btn)
        help_btn = QPushButton("Help Another PC")
        help_btn.setToolTip("Open KRDC to connect to an RDP or VNC address.")
        help_btn.clicked.connect(self._open_krdc)
        assist_btns.addWidget(help_btn)
        snapshot_btn = QPushButton("Create Support Snapshot")
        snapshot_btn.setToolTip("Save system details that can be reviewed before granting remote access.")
        snapshot_btn.clicked.connect(self._create_assist_snapshot)
        assist_btns.addWidget(snapshot_btn)
        assist_btns.addStretch()
        assist_layout.addLayout(assist_btns)
        self._assist_status = QLabel("")
        self._assist_status.setObjectName("card-copy")
        self._assist_status.setWordWrap(True)
        assist_layout.addWidget(self._assist_status)
        self._refresh_rustdesk_btn()
        self._add(assist_card)

    def _build_printer_card(self) -> None:
        def _open_cups(_=False):
            popen_privileged(systemctl_action("enable", "cups.service", now=True))
            QDesktopServices.openUrl(QUrl("http://localhost:631"))

        card, _buttons = _make_tip_card(
            "Printer Setup",
            "Most USB and network printers work automatically via CUPS. "
            "Click Setup Printer to enable the print service and open KDE Printer Settings. "
            "If your printer is not listed, click Add Printer and enter its IP address or use the USB connection.\n\n"
            "For older or unusual printers, the CUPS web interface at http://localhost:631 "
            "gives you access to every available driver.",
            buttons=[
                ("Setup Printer", self._open_printer_setup),
                (
                    "Open CUPS Web Interface", _open_cups,
                    "Advanced printer management at http://localhost:631",
                ),
            ],
        )
        self._add(card)

    def _build_backup_card(self) -> None:
        # File History — backups (Pika Backup wraps borg snapshots)
        backup_card, backup_layout = _make_card()
        backup_title = QLabel("File History — automatic backups")
        backup_title.setObjectName("card-title")
        backup_layout.addWidget(backup_title)
        backup_body = QLabel(
            "Like File History-style backup: pick a backup drive (or network location), "
            "and Pika Backup keeps scheduled snapshots of your files. Restore any "
            "earlier version of a file from the same app. Snapshots are deduplicated, "
            "so keeping months of history costs little space."
        )
        backup_body.setObjectName("card-copy")
        backup_body.setWordWrap(True)
        backup_layout.addWidget(backup_body)
        backup_btns = QHBoxLayout()
        backup_btns.setSpacing(8)
        pika_installed = _is_flatpak_installed("org.gnome.World.PikaBackup")
        self._backup_btn = QPushButton("Open Pika Backup" if pika_installed else "Set Up File History")
        self._backup_btn.setObjectName("primary")
        self._backup_btn.setToolTip("Installs Pika Backup from Flathub, then schedule backups of your home folder to a USB drive or network share.")
        self._backup_btn.clicked.connect(self._on_file_history)
        backup_btns.addWidget(self._backup_btn)
        backup_btns.addStretch()
        backup_layout.addLayout(backup_btns)
        self._add(backup_card)

    def _build_restore_setup_card(self) -> None:
        setup_card, setup_layout = _make_card("card-accent-ok")
        setup_title = QLabel("Restore My PC Setup")
        setup_title.setObjectName("card-title")
        setup_layout.addWidget(setup_title)
        setup_body = QLabel(
            "Move your KythOS setup to a reinstall or another PC: installed Flatpaks, "
            "default apps, keyboard shortcuts, desktop preferences, KythOS profile, "
            "network-share definitions, cloud sync folders, and gaming-tool settings. "
            "Passwords, browser sessions, SMB credentials, KWallet data, and cloud OAuth "
            "tokens are deliberately excluded."
        )
        setup_body.setObjectName("card-copy")
        setup_body.setWordWrap(True)
        setup_layout.addWidget(setup_body)
        setup_btns = QHBoxLayout()
        setup_btns.setSpacing(8)
        self._setup_export_btn = QPushButton("Export My Setup")
        self._setup_export_btn.setObjectName("primary")
        self._setup_export_btn.clicked.connect(self._export_setup)
        setup_btns.addWidget(self._setup_export_btn)
        self._setup_restore_btn = QPushButton("Restore From Archive…")
        self._setup_restore_btn.clicked.connect(self._restore_setup)
        setup_btns.addWidget(self._setup_restore_btn)
        setup_btns.addStretch()
        setup_layout.addLayout(setup_btns)
        self._setup_status = QLabel("Keep the archive with your normal personal-file backup.")
        self._setup_status.setObjectName("card-copy")
        self._setup_status.setWordWrap(True)
        setup_layout.addWidget(self._setup_status)
        self._add(setup_card)

    def _build_snapshot_card(self) -> None:
        snapshot_card, snapshot_layout = _make_card()
        snapshot_title = QLabel("Session Snapshot")
        snapshot_title.setObjectName("card-title")
        snapshot_layout.addWidget(snapshot_title)
        snapshot_body = QLabel(
            "Export a plain-text snapshot of this setup: OS image, Flatpaks, gaming paths, "
            "and KythOS checks. Useful before reinstalling, moving to another PC, or asking for help."
        )
        snapshot_body.setObjectName("card-copy")
        snapshot_body.setWordWrap(True)
        snapshot_layout.addWidget(snapshot_body)
        snapshot_btns = QHBoxLayout()
        self._snapshot_btn = QPushButton("Create Snapshot")
        self._snapshot_btn.setToolTip("Export a plain-text report of your OS image, Flatpaks, and hardware checks — useful before reinstalling or when asking for help.")
        self._snapshot_btn.clicked.connect(self._run_session_snapshot)
        snapshot_btns.addWidget(self._snapshot_btn)
        self._snapshot_status = QLabel("")
        self._snapshot_status.setObjectName("card-copy")
        snapshot_btns.addWidget(self._snapshot_status, 1)
        snapshot_layout.addLayout(snapshot_btns)
        self._add(snapshot_card)

    def _build_reinstall_card(self) -> None:
        card, _buttons = _make_tip_card(
            "Install KythOS on another disk",
            "To install KythOS onto a different disk, boot the live ISO — the full graphical "
            "installer is built in. Back up personal files first; the installer erases the disk you select.",
            primary=None,
            buttons=[
                (
                    "Download Live ISO",
                    lambda _=False: QDesktopServices.openUrl(QUrl("https://github.com/mrtrick37/kyth/releases")),
                    "Open the KythOS releases page to download a live ISO for installing on another disk.",
                ),
                (
                    "Open Home Folder",
                    lambda _=False: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.expanduser("~"))),
                    "Open your home folder in the file manager to back up personal files before reinstalling.",
                ),
            ],
        )
        self._add(card)

    def _build_warning_card(self) -> None:
        card, _buttons = _make_tip_card(
            "This action cannot be undone",
            "Running a repair will:\n"
            "  •  Remove any layered packages and custom OS-level changes\n"
            "  •  Reset system configuration to KythOS defaults\n"
            "  •  Leave everything in /home untouched\n"
            "  •  Reboot automatically after staging\n\n"
            "If you only need to undo a bad update, use Roll Back in the Update page first.",
            accent="card-accent-err",
            title_object_name="card-title-err",
        )
        self._add(card)

    def _build_reset_controls(self) -> None:
        confirm_row = QHBoxLayout()
        confirm_row.setSpacing(12)
        confirm_lbl = QLabel("Type  RESET  to unlock:")
        confirm_lbl.setObjectName("card-copy")
        confirm_row.addWidget(confirm_lbl)
        self._confirm_edit = QLineEdit()
        self._confirm_edit.setFixedWidth(130)
        self._confirm_edit.setPlaceholderText("RESET")
        self._confirm_edit.textChanged.connect(self._on_confirm_text)
        confirm_row.addWidget(self._confirm_edit)
        confirm_row.addStretch()
        self._add_layout(confirm_row)

        btn_row = QHBoxLayout()
        self._reset_btn = QPushButton("Repair Install")
        self._reset_btn.setObjectName("danger")
        self._reset_btn.setToolTip("Reset layered packages and system config to KythOS defaults. /home is untouched. This cannot be undone.")
        self._reset_btn.setEnabled(False)
        self._reset_btn.clicked.connect(self._run_reset)
        btn_row.addWidget(self._reset_btn)
        btn_row.addStretch()
        self._add_layout(btn_row)

        self._status_lbl = QLabel()
        self._status_lbl.hide()
        self._add(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._add(self._progress)

        self._log_panel = CollapsibleLogPanel(min_height=120)
        self._add(self._log_panel)

    def _build_sleep_diagnostics_card(self) -> None:
        sleep_card, sleep_layout = _make_card()
        sleep_title = QLabel("Sleep / Wake Reliability")
        sleep_title.setObjectName("card-title")
        sleep_layout.addWidget(sleep_title)

        mem_sleep = _read_sys_text("/sys/power/mem_sleep")
        sleep_state = _read_sys_text("/sys/power/state")
        current_mode = sleep_mode_label(mem_sleep)

        sleep_body = QLabel(
            f"Current sleep mode: {current_mode}\n"
            f"Available states: {sleep_state.strip() or 'unknown'}\n\n"
            "KythOS disables hybrid sleep and suspend-then-hibernate by default — "
            "these are common causes of black screens on wake for gaming PCs. "
            "If you get a black screen when resuming from sleep, try 'Force Deep Sleep' below."
        )
        sleep_body.setObjectName("card-copy")
        sleep_body.setWordWrap(True)
        sleep_layout.addWidget(sleep_body)
        sleep_btns = QHBoxLayout()
        sleep_btns.setSpacing(8)
        deep_sleep_btn = QPushButton("Force Deep Sleep (S3)")
        deep_sleep_btn.setToolTip(
            "Writes 'deep' to /sys/power/mem_sleep for this session, overriding s2idle. "
            "Effective immediately; reverts on reboot. If sleep works correctly after this, "
            "add mem_sleep_default=deep to your kernel parameters permanently."
        )
        deep_sleep_btn.clicked.connect(self._force_deep_sleep)
        sleep_btns.addWidget(deep_sleep_btn)
        wakeup_btn = QPushButton("Show Wake Sources")
        wakeup_btn.setToolTip("List devices that can wake the system from sleep. Useful for diagnosing spurious wake-ups.")
        wakeup_btn.clicked.connect(self._show_wakeup_sources)
        sleep_btns.addWidget(wakeup_btn)
        sleep_btns.addStretch()
        sleep_layout.addLayout(sleep_btns)
        self._sleep_fix_status = QLabel()
        self._sleep_fix_status.setObjectName("card-copy")
        self._sleep_fix_status.setWordWrap(True)
        sleep_layout.addWidget(self._sleep_fix_status)
        self._add(sleep_card)
