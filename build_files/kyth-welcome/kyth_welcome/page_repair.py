import os
import shlex
import shutil
import subprocess
from pathlib import Path

# __KYTH_GENERATED_IMPORTS__
from .core import (  # noqa: E501
    Worker, _bootc_image_timestamp, _command_stdout, _detect_nvidia, _finish_worker, _has_rollback_deployment, _install_flatpak_inline, _is_flatpak_installed, _restyle, _set_session_inhibit, _with_idle_inhibit,
)
from .qt import (  # noqa: E501
    QDesktopServices, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QTextEdit, QTimer, QUrl,
)
from .widgets import (  # noqa: E501
    Page, _make_card, _make_flow_step, _set_log_panel,
)


def _read_sys_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""

# ── Page: Repair ──────────────────────────────────────────────────────────────
class RepairPage(Page):
    def __init__(self, navigate=None):
        super().__init__()
        self._worker = None
        self._snapshot_worker = None
        self._assist_worker = None
        self._setup_worker = None
        self._has_rollback = _has_rollback_deployment()
        self._setup_operation = ""
        self._navigate = navigate or (lambda _key: None)

        self._page_header(
            "System",
            "Repair",
            "Reset the OS back to a clean KythOS state. Your personal files in /home are never touched.",
        )

        # Info card
        info, info_layout = _make_card()
        info_title = QLabel("What repair changes and what it preserves")
        info_title.setObjectName("card-title")
        info_layout.addWidget(info_title)
        info_body = QLabel(
            "Repair resets layered packages, system configuration, and the OS image to KythOS defaults. "
            "It does not replace a proper backup. Files in /home are left in place, so this is "
            "a safe way to recover a broken OS — but keep your saves, projects, and documents "
            "backed up somewhere external."
        )
        info_body.setObjectName("card-copy")
        info_body.setWordWrap(True)
        info_layout.addWidget(info_body)
        self._add(info)

        order_card, order_layout = _make_card("card-accent-ok")
        order_title = QLabel("Best repair order")
        order_title.setObjectName("card-title")
        order_layout.addWidget(order_title)
        for i, (title, copy) in enumerate((
            ("Quick fixes", "Refresh menus, repair Flatpaks, restart audio or Bluetooth, and collect a snapshot first."),
            ("Roll back", "If trouble started after an update, stage the previous image before changing anything else."),
            ("Repair install", "Use the destructive OS reset only after quick fixes and rollback do not match the problem."),
        ), 1):
            order_layout.addWidget(_make_flow_step(i, title, copy))
        self._add(order_card)

        immutable, immutable_layout = _make_card("card-accent-ok")
        immutable_title = QLabel("Why system files are read-only")
        immutable_title.setObjectName("card-title")
        immutable_layout.addWidget(immutable_title)
        immutable_body = QLabel(
            "KythOS protects the base OS like a game console image: /usr is read-only while "
            "you are using the system, and OS changes arrive as a new bootable deployment. "
            "That is why updates can be rolled back cleanly. Install apps with Flatpak, use "
            "Distrobox for development tools, keep personal files in /home, and let KythOS "
            "updates replace the base system instead of editing it by hand."
        )
        immutable_body.setObjectName("card-copy")
        immutable_body.setWordWrap(True)
        immutable_layout.addWidget(immutable_body)
        immutable_btns = QHBoxLayout()
        immutable_btns.setSpacing(8)
        update_help_btn = QPushButton("Open Update Page")
        update_help_btn.setToolTip("Open the Update page to run a system update or roll back to the previous image.")
        update_help_btn.clicked.connect(lambda _=False: self._navigate("Update"))
        immutable_btns.addWidget(update_help_btn)
        software_help_btn = QPushButton("Open App Store")
        software_help_btn.setToolTip("Open the App Store to browse Flatpak apps and curated Kyth picks.")
        software_help_btn.clicked.connect(lambda _=False: self._navigate("App Store"))
        immutable_btns.addWidget(software_help_btn)
        immutable_btns.addStretch()
        immutable_layout.addLayout(immutable_btns)
        self._add(immutable)

        # Undo last update
        rollback, rollback_layout = _make_card("card-accent-warn" if self._has_rollback else None)
        rollback_title = QLabel("Undo last update")
        rollback_title.setObjectName("card-title")
        rollback_layout.addWidget(rollback_title)
        rollback_ts = _bootc_image_timestamp("rollback")
        rollback_body = QLabel(
            (
                "A previous system image is available. Rollback restores that image on the next boot; "
                "your files, saves, and projects in /home stay in place."
                + (f"\n\nPrevious image built: {rollback_ts}" if rollback_ts else "")
            )
            if self._has_rollback
            else (
                "No previous system image is available right now. After the next OS update, "
                "KythOS will keep a rollback target here so you can undo a bad update."
            )
        )
        rollback_body.setObjectName("card-copy")
        rollback_body.setWordWrap(True)
        rollback_layout.addWidget(rollback_body)
        rollback_btns = QHBoxLayout()
        rollback_btns.setSpacing(8)
        self._rollback_repair_btn = QPushButton("Rollback and Reboot")
        self._rollback_repair_btn.setObjectName("primary")
        self._rollback_repair_btn.setToolTip("Activate the previous OS image on the next boot. Your files in /home stay untouched.")
        self._rollback_repair_btn.setEnabled(self._has_rollback)
        self._rollback_repair_btn.clicked.connect(self._run_rollback)
        rollback_btns.addWidget(self._rollback_repair_btn)
        update_btn = QPushButton("Open Update Page")
        update_btn.setToolTip("Open the Update page to run a system update or roll back to the previous image.")
        update_btn.clicked.connect(lambda _=False: self._navigate("Update"))
        rollback_btns.addWidget(update_btn)
        rollback_btns.addStretch()
        rollback_layout.addLayout(rollback_btns)
        self._add(rollback)

        # Quick fixes
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
        quick_btns = QHBoxLayout()
        quick_btns.setSpacing(8)
        panic_btn = QPushButton("Panic Button")
        panic_btn.setObjectName("primary")
        panic_btn.setToolTip("Run the safe repair bundle: app menu, user polish, Flatpak repair, audio restart, and snapshot.")
        panic_btn.clicked.connect(lambda _=False: self._run_quick_fix("Panic Button", [
            "bash", "-c",
            "set -e; "
            "update-desktop-database \"$HOME/.local/share/applications\" 2>/dev/null || true; "
            "kbuildsycoca6 --noincremental 2>/dev/null || true; "
            "/usr/bin/kyth-user-polish 2>/dev/null || true; "
            "flatpak repair --user 2>/dev/null || true; "
            "systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || true; "
            "/usr/bin/kyth-session-snapshot"
        ]))
        quick_btns.addWidget(panic_btn)
        for label, tip, cmd in (
            ("Refresh App Menu",  "Rebuild the application menu database. Fixes missing app icons and entries after installs.",
             ["bash", "-c", "update-desktop-database \"$HOME/.local/share/applications\" 2>/dev/null || true; kbuildsycoca6 --noincremental"]),
            ("Apply User Polish", "Re-apply KythOS default theme, fonts, and KDE settings to your user profile.",
             ["/usr/bin/kyth-user-polish"]),
            ("Retry Game Apps",   "Restart the Flatpak install service to retry installing Steam, Lutris, and other game apps.",
             ["sudo", "-A", "systemctl", "restart", "kyth-default-flatpaks.service"]),
            ("Fix Flatpak Apps",  "Repair the Flatpak user installation. Fixes corrupted or missing app runtimes.",
             ["flatpak", "repair", "--user"]),
            ("Restart Audio",     "Restart PipeWire, PipeWire-Pulse, and WirePlumber. Fixes audio that has stopped working.",
             ["systemctl", "--user", "restart", "pipewire", "pipewire-pulse", "wireplumber"]),
            ("Restart Bluetooth", "Restart the Bluetooth service. Fixes controllers and headsets that won't pair or connect.",
             ["sudo", "-A", "systemctl", "restart", "bluetooth"]),
        ):
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, c=cmd, l=label: self._run_quick_fix(l, c))
            quick_btns.addWidget(btn)
        if _detect_nvidia():
            nvidia_status_btn = QPushButton("NVIDIA Status")
            nvidia_status_btn.setToolTip("Show current NVIDIA driver build status and kernel module load state.")
            nvidia_status_btn.clicked.connect(
                lambda _=False: self._run_quick_fix("NVIDIA Status", ["/usr/bin/kyth-nvidia-status"])
            )
            quick_btns.addWidget(nvidia_status_btn)
            nvidia_fix_btn = QPushButton("Retry NVIDIA Build")
            nvidia_fix_btn.setToolTip("Open the NVIDIA Drivers page to retry the kernel module build.")
            nvidia_fix_btn.clicked.connect(lambda _=False: self._navigate("NVIDIA"))
            quick_btns.addWidget(nvidia_fix_btn)
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
        defaults_btn.clicked.connect(lambda _=False: subprocess.Popen(["kcmshell6", "filetypes"])
            if shutil.which("kcmshell6") else QDesktopServices.openUrl(QUrl("settings://filetypes")))
        quick_btns.addWidget(defaults_btn)
        startup_btn = QPushButton("Manage Startup Apps")
        startup_btn.setToolTip("Control which apps launch at login — for familiar startup-app management.")
        startup_btn.clicked.connect(lambda _=False: subprocess.Popen(["kcmshell6", "autostart"])
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
        quick_btns.addStretch()
        quick_layout.addLayout(quick_btns)
        self._add(quick)

        # Quick Assist replacement
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

        # Printer setup card
        printer_card, printer_layout = _make_card()
        printer_title = QLabel("Printer Setup")
        printer_title.setObjectName("card-title")
        printer_layout.addWidget(printer_title)
        printer_body = QLabel(
            "Most USB and network printers work automatically via CUPS. "
            "Click Setup Printer to enable the print service and open KDE Printer Settings. "
            "If your printer is not listed, click Add Printer and enter its IP address or use the USB connection.\n\n"
            "For older or unusual printers, the CUPS web interface at http://localhost:631 "
            "gives you access to every available driver."
        )
        printer_body.setObjectName("card-copy")
        printer_body.setWordWrap(True)
        printer_layout.addWidget(printer_body)
        printer_btns = QHBoxLayout()
        printer_btns.setSpacing(8)
        printer_open_btn = QPushButton("Setup Printer")
        printer_open_btn.setObjectName("primary")
        printer_open_btn.clicked.connect(self._open_printer_setup)
        printer_btns.addWidget(printer_open_btn)
        cups_btn = QPushButton("Open CUPS Web Interface")
        cups_btn.setToolTip("Advanced printer management at http://localhost:631")
        cups_btn.clicked.connect(lambda _=False: (
            subprocess.Popen(["sudo", "systemctl", "enable", "--now", "cups"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
            QDesktopServices.openUrl(QUrl("http://localhost:631"))
        ))
        printer_btns.addWidget(cups_btn)
        printer_btns.addStretch()
        printer_layout.addLayout(printer_btns)
        self._add(printer_card)

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

        # Restore My PC Setup
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

        # Session snapshot
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

        # Reinstall on another disk
        reinstall_card, reinstall_layout = _make_card()
        reinstall_title = QLabel("Install KythOS on another disk")
        reinstall_title.setObjectName("card-title")
        reinstall_layout.addWidget(reinstall_title)
        reinstall_body = QLabel(
            "To install KythOS onto a different disk, boot the live ISO — the full graphical "
            "installer is built in. Back up personal files first; the installer erases the disk you select."
        )
        reinstall_body.setObjectName("card-copy")
        reinstall_body.setWordWrap(True)
        reinstall_layout.addWidget(reinstall_body)
        reinstall_btns = QHBoxLayout()
        reinstall_btns.setSpacing(8)
        iso_btn = QPushButton("Download Live ISO")
        iso_btn.setToolTip("Open the KythOS releases page to download a live ISO for installing on another disk.")
        iso_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(QUrl("https://github.com/mrtrick37/kyth/releases")))
        reinstall_btns.addWidget(iso_btn)
        home_btn = QPushButton("Open Home Folder")
        home_btn.setToolTip("Open your home folder in the file manager to back up personal files before reinstalling.")
        home_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.expanduser("~"))))
        reinstall_btns.addWidget(home_btn)
        reinstall_btns.addStretch()
        reinstall_layout.addLayout(reinstall_btns)
        self._add(reinstall_card)

        # Warning card
        warn, warn_layout = _make_card("card-accent-err")
        warn_title = QLabel("This action cannot be undone")
        warn_title.setStyleSheet("color: #f7768e; font-size: 14px; font-weight: 700;")
        warn_layout.addWidget(warn_title)
        warn_body = QLabel(
            "Running a repair will:\n"
            "  \u2022  Remove any layered packages and custom OS-level changes\n"
            "  \u2022  Reset system configuration to KythOS defaults\n"
            "  \u2022  Leave everything in /home untouched\n"
            "  \u2022  Reboot automatically after staging\n\n"
            "If you only need to undo a bad update, use Roll Back in the Update page first."
        )
        warn_body.setObjectName("card-copy")
        warn_body.setWordWrap(True)
        warn_layout.addWidget(warn_body)
        self._add(warn)

        # Confirm
        confirm_row = QHBoxLayout()
        confirm_row.setSpacing(12)
        confirm_lbl = QLabel("Type  RESET  to unlock:")
        confirm_lbl.setStyleSheet("color: #6c7086;")
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

        self._log_toggle = QPushButton("Show details")
        self._log_toggle.setCheckable(True)
        self._log_toggle.clicked.connect(lambda checked: _set_log_panel(self._log_toggle, self._log, checked))
        self._log_toggle.hide()
        self._add(self._log_toggle)

        self._log = QTextEdit()
        self._log.document().setMaximumBlockCount(5000)
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)
        self._log.hide()
        self._add(self._log)

        # ── Sleep diagnostics ─────────────────────────────────────────────────
        sleep_card, sleep_layout = _make_card()
        sleep_title = QLabel("Sleep / Wake Reliability")
        sleep_title.setObjectName("card-title")
        sleep_layout.addWidget(sleep_title)

        mem_sleep = _read_sys_text("/sys/power/mem_sleep")
        sleep_state = _read_sys_text("/sys/power/state")
        current_mode = "unknown"
        if "[deep]" in mem_sleep:
            current_mode = "S3 deep (good)"
        elif "[s2idle]" in mem_sleep:
            current_mode = "s2idle (modern standby — may wake early)"
        elif mem_sleep:
            current_mode = mem_sleep.strip()

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

        self._stretch()

    def _force_deep_sleep(self):
        try:
            result = subprocess.run(
                ["sudo", "-A", "bash", "-c", "echo deep > /sys/power/mem_sleep"],
                timeout=8, capture_output=True,
            )
            if result.returncode == 0:
                self._sleep_fix_status.setText(
                    "Deep sleep (S3) forced for this session. Put the system to sleep and wake it — "
                    "if it works correctly, the fix is working. Add mem_sleep_default=deep to your "
                    "kernel arguments to make this permanent."
                )
                self._sleep_fix_status.setObjectName("status-ok")
            else:
                err = result.stderr.decode("utf-8", errors="replace").strip()
                self._sleep_fix_status.setText(
                    f"Could not set sleep mode (may not be supported on this platform): {err}"
                )
                self._sleep_fix_status.setObjectName("status-err")
        except Exception as exc:
            self._sleep_fix_status.setText(f"Error: {exc}")
            self._sleep_fix_status.setObjectName("status-err")
        _restyle(self._sleep_fix_status)

    def _show_wakeup_sources(self):
        result = _command_stdout(
            ["bash", "-c", "grep -r . /sys/bus/*/devices/*/power/wakeup 2>/dev/null | grep ':enabled' | sed 's|/sys/bus/||;s|/devices/||;s|/power/wakeup:enabled||' | sort"],
            timeout=5,
        )
        if result.strip():
            self._sleep_fix_status.setText(f"Wake-enabled devices:\n{result.strip()}")
        else:
            self._sleep_fix_status.setText("No wake sources found (or /sys/bus path unavailable).")
        self._sleep_fix_status.setObjectName("card-copy")
        _restyle(self._sleep_fix_status)

    def _on_file_history(self):
        if _is_flatpak_installed("org.gnome.World.PikaBackup"):
            try:
                subprocess.Popen(["flatpak", "run", "org.gnome.World.PikaBackup"])
            except OSError:
                pass
            return
        def _launch_after_install(code: int):
            if code == 0:
                self._backup_btn.setText("Open Pika Backup")
                self._backup_btn.setEnabled(True)
        _install_flatpak_inline(
            self, self._backup_btn, "org.gnome.World.PikaBackup", "Pika Backup",
            done_cb=_launch_after_install,
        )

    def _refresh_rustdesk_btn(self):
        installed = _is_flatpak_installed("com.rustdesk.RustDesk")
        self._rustdesk_btn.setText("Open RustDesk — Get Help" if installed else "Install RustDesk — Get Help")

    def _open_or_install_rustdesk(self):
        app_id = "com.rustdesk.RustDesk"
        if _is_flatpak_installed(app_id):
            try:
                subprocess.Popen(["flatpak", "run", app_id])
                self._assist_status.setText(
                    "Share only the temporary ID and one-time password with someone you trust. "
                    "Close RustDesk when the support session is finished."
                )
            except OSError as exc:
                self._assist_status.setText(f"Could not open RustDesk: {exc}")
            return

        def _installed(code: int):
            if code == 0:
                self._rustdesk_btn.setEnabled(True)
                self._refresh_rustdesk_btn()
                self._assist_status.setText("RustDesk installed. Open it when your helper is ready.")

        _install_flatpak_inline(
            self, self._rustdesk_btn, app_id, "RustDesk", done_cb=_installed,
        )

    def _open_krdc(self):
        if shutil.which("krdc"):
            try:
                subprocess.Popen(["krdc"])
                self._assist_status.setText("KRDC opened — enter an rdp:// or vnc:// address to help another PC.")
            except OSError as exc:
                self._assist_status.setText(f"Could not open KRDC: {exc}")
        else:
            self._assist_status.setText(
                "KRDC will be available after applying the latest KythOS update and restarting."
            )

    def _create_assist_snapshot(self):
        if self._assist_worker is not None and self._assist_worker.isRunning():
            return
        self._assist_status.setText("Creating a support snapshot…")
        worker = Worker(["/usr/bin/kyth-session-snapshot"])
        worker.line.connect(lambda line: self._assist_status.setText(line.strip() or "Snapshot created."))
        worker.done.connect(self._on_assist_snapshot_done)
        self._assist_worker = worker
        worker.start()

    def _on_assist_snapshot_done(self, code: int):
        _finish_worker(self, attr="_assist_worker")
        if code != 0:
            self._assist_status.setText(f"Support snapshot failed (exit {code}).")

    @staticmethod
    def _setup_transfer_helper() -> str:
        installed = "/usr/bin/kyth-setup-transfer"
        if os.path.exists(installed):
            return installed
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "kyth-setup-transfer"))

    def _set_setup_busy(self, busy: bool):
        self._setup_export_btn.setEnabled(not busy)
        self._setup_restore_btn.setEnabled(not busy)

    def _export_setup(self):
        if self._setup_worker is not None and self._setup_worker.isRunning():
            return
        destination = QFileDialog.getExistingDirectory(
            self, "Choose where to save your KythOS setup", os.path.expanduser("~/Documents")
        )
        if not destination:
            return
        helper = self._setup_transfer_helper()
        if not os.path.exists(helper):
            self._setup_status.setText("Setup transfer is available after the next KythOS update and restart.")
            return
        self._setup_operation = "export"
        self._set_setup_busy(True)
        self._setup_status.setText("Collecting apps and preferences…")
        worker = Worker([helper, "export", destination])
        worker.line.connect(lambda line: self._setup_status.setText(line.strip() or "Exporting setup…"))
        worker.done.connect(self._on_setup_transfer_done)
        self._setup_worker = worker
        worker.start()

    def _restore_setup(self):
        if self._setup_worker is not None and self._setup_worker.isRunning():
            return
        archive, _ = QFileDialog.getOpenFileName(
            self, "Choose a KythOS setup archive", os.path.expanduser("~"),
            "KythOS setup archives (kyth-setup-*.tar.gz);;Tar archives (*.tar.gz)",
        )
        if not archive:
            return
        helper = self._setup_transfer_helper()
        if not os.path.exists(helper):
            self._setup_status.setText("Setup transfer is available after the next KythOS update and restart.")
            return
        try:
            result = subprocess.run(
                [helper, "summary", archive], capture_output=True, text=True, timeout=15,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Could not inspect archive", str(exc))
            return
        if result.returncode != 0:
            QMessageBox.warning(
                self, "Invalid setup archive", (result.stderr or result.stdout).strip()
            )
            return
        answer = QMessageBox.question(
            self, "Restore this PC setup?",
            result.stdout.strip()
            + "\n\nExisting preferences with the same names will be replaced. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._setup_operation = "restore"
        self._set_setup_busy(True)
        self._setup_status.setText("Restoring preferences and applications…")
        worker = Worker([helper, "restore", archive])
        worker.line.connect(lambda line: self._setup_status.setText(line.strip() or "Restoring setup…"))
        worker.done.connect(self._on_setup_transfer_done)
        self._setup_worker = worker
        worker.start()

    def _on_setup_transfer_done(self, code: int):
        operation = self._setup_operation
        _finish_worker(self, attr="_setup_worker")
        self._set_setup_busy(False)
        if code == 0 and operation == "restore":
            self._setup_status.setText(
                "Setup restored. Reconnect cloud accounts, re-enter network-share passwords, "
                "then sign out and back in to apply desktop shortcuts and preferences."
            )
        elif code != 0:
            self._setup_status.setText(f"Setup {operation or 'transfer'} failed (exit {code}).")

    def _run_session_snapshot(self):
        if self._snapshot_worker and self._snapshot_worker.isRunning():
            return
        self._snapshot_btn.setEnabled(False)
        self._snapshot_status.setText("Creating snapshot…")
        self._snapshot_worker = Worker(["/usr/bin/kyth-session-snapshot"])
        self._snapshot_worker.line.connect(lambda ln: self._snapshot_status.setText(ln.strip() or "Snapshot created."))
        self._snapshot_worker.done.connect(self._on_snapshot_done)
        self._snapshot_worker.start()

    def _on_snapshot_done(self, code: int):
        _finish_worker(self, attr="_snapshot_worker")
        self._snapshot_btn.setEnabled(True)
        if code != 0:
            self._snapshot_status.setText(f"Snapshot failed (exit {code}).")

    def _open_task_manager(self):
        if _is_flatpak_installed("io.missioncenter.MissionCenter"):
            try:
                subprocess.Popen(["flatpak", "run", "io.missioncenter.MissionCenter"])
                return
            except OSError:
                pass
        for cmd in (["plasma-systemmonitor"], ["ksysguard"], ["konsole", "-e", "btop"], ["konsole", "-e", "top"]):
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd)
                return
        QMessageBox.warning(self, "Task Manager not found", "Could not find System Monitor or a terminal task viewer.")

    def _open_printer_setup(self):
        subprocess.Popen(
            ["sudo", "systemctl", "enable", "--now", "cups"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for cmd in (["kcmshell6", "kcm_printer_manager"], ["systemsettings"]):
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd)
                return
        QDesktopServices.openUrl(QUrl("http://localhost:631"))

    def _open_volume_mixer(self):
        for cmd in (["pavucontrol-qt"], ["pavucontrol"], ["plasma-pa"]):
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd)
                return
        # Fall back to the KDE audio KCM
        if shutil.which("kcmshell6"):
            subprocess.Popen(["kcmshell6", "kcm_pulseaudio"])
            return
        QMessageBox.information(
            self, "Volume Mixer",
            "Right-click the speaker icon in the system tray and choose Audio Volume Settings,\n"
            "or look for 'Audio Volume' in System Settings."
        )

    def _fix_exe_association(self):
        mimes = ["application/x-ms-dos-executable", "application/x-msdos-program", "application/x-msi"]
        bottles_desktop = "com.usebottles.bottles.desktop"
        try:
            for mime in mimes:
                subprocess.run(["xdg-mime", "default", bottles_desktop, mime], timeout=5, check=False)
            QMessageBox.information(
                self, "Fix .exe Files",
                "Done. Double-clicking .exe and .msi files will now open Bottles.\n"
                "If Bottles is not installed, install it from the App Store first."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Fix .exe Files", f"Could not update file associations: {exc}")

    def _enable_clipboard_history(self):
        try:
            subprocess.run(
                ["kwriteconfig6", "--file", "klipperrc",
                 "--group", "General", "--key", "KeepClipboardContents", "true"],
                timeout=5, check=False,
            )
            subprocess.run(
                ["kwriteconfig6", "--file", "klipperrc",
                 "--group", "General", "--key", "MaxClipItems", "25"],
                timeout=5, check=False,
            )
            subprocess.run(["systemctl", "--user", "restart", "plasma-klipper.service"],
                           timeout=5, check=False)
            QMessageBox.information(
                self, "Clipboard History",
                "Clipboard history enabled (25 items).\n"
                "Press Meta+V (Meta+V) to open the clipboard history popup."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Clipboard History", f"Could not enable clipboard history: {exc}")

    def _open_night_light(self):
        if shutil.which("kcmshell6"):
            subprocess.Popen(["kcmshell6", "kcm_nightcolor"])
        else:
            QDesktopServices.openUrl(QUrl("settings://kcm_nightcolor"))

    def _run_quick_fix(self, label: str, cmd: list[str]):
        if self._worker and self._worker.isRunning():
            return
        self._confirm_edit.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ " + " ".join(shlex.quote(part) for part in cmd) + "\n")
        self._log_toggle.show()
        _set_log_panel(self._log_toggle, self._log, False)
        self._progress.show()
        self._status_lbl.setText(f"{label}…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        _restyle(self._status_lbl)
        self._worker = Worker(cmd)
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(lambda code, name=label: self._on_quick_fix_done(code, name))
        self._worker.start()

    def _on_quick_fix_done(self, code: int, label: str):
        self._progress.hide()
        _finish_worker(self)
        self._confirm_edit.setEnabled(True)
        self._on_confirm_text(self._confirm_edit.text())
        if code == 0:
            self._status_lbl.setText(f"{label} complete.")
            self._status_lbl.setObjectName("status-ok")
            self._log.append("\nDone.")
        else:
            self._status_lbl.setText(f"{label} failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
            _set_log_panel(self._log_toggle, self._log, True)
        _restyle(self._status_lbl)

    def _on_confirm_text(self, text: str):
        self._reset_btn.setEnabled(text.strip() == "RESET")

    def _run_rollback(self):
        if self._worker and self._worker.isRunning():
            return
        self._confirm_edit.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._rollback_repair_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ bootc rollback\n")
        self._log_toggle.show()
        _set_log_panel(self._log_toggle, self._log, False)
        self._progress.show()
        self._status_lbl.setText("Staging previous system image…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        _restyle(self._status_lbl)

        self._worker = Worker(_with_idle_inhibit(["sudo", "bootc", "rollback"], "KythOS is staging a rollback"))
        _set_session_inhibit(self, "KythOS is staging a rollback")
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_rollback_done)
        self._worker.start()

    def _on_rollback_done(self, code: int):
        self._progress.hide()
        _finish_worker(self)
        _set_session_inhibit(self, None)
        self._confirm_edit.setEnabled(True)
        self._on_confirm_text(self._confirm_edit.text())
        if code == 0:
            self._status_lbl.setText("Rollback staged — rebooting into the previous system image…")
            self._status_lbl.setObjectName("status-ok")
            self._log.append("\nDone. Rebooting now.")
            QTimer.singleShot(2000, lambda: subprocess.Popen(["systemctl", "reboot"]))
        else:
            self._status_lbl.setText(f"Rollback failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
            self._rollback_repair_btn.setEnabled(_has_rollback_deployment())
        _restyle(self._status_lbl)

    def _run_reset(self):
        self._confirm_edit.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ bootc reset\n")
        self._log_toggle.show()
        _set_log_panel(self._log_toggle, self._log, False)
        self._progress.show()
        self._status_lbl.setText("Resetting system…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        _restyle(self._status_lbl)

        self._worker = Worker(_with_idle_inhibit(["sudo", "bootc", "reset"], "KythOS is resetting the system"))
        _set_session_inhibit(self, "KythOS is resetting the system image")
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_line(self, text: str):
        self._log.append(text)
        self._log.ensureCursorVisible()

    def _on_done(self, code: int):
        self._progress.hide()
        _finish_worker(self)
        _set_session_inhibit(self, None)

        if code == 0:
            self._status_lbl.setText("Reset staged — rebooting…")
            self._status_lbl.setObjectName("status-ok")
            self._log.append("\nDone. Rebooting now.")
            _restyle(self._status_lbl)
            QTimer.singleShot(2000, lambda: subprocess.Popen(["systemctl", "reboot"]))
        else:
            self._status_lbl.setText(f"Reset failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
            _restyle(self._status_lbl)
            self._confirm_edit.setEnabled(True)
            self._confirm_edit.clear()
