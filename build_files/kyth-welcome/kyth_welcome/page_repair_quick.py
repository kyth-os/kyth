"""Repair page — quick fixes, sleep, desktop helpers."""
from __future__ import annotations

import shutil

from .core_base import _restyle
from .services.launch import flatpak_run, kcmshell, popen, systemsettings
from .services.repair import (
    enable_clipboard_history,
    force_deep_sleep,
    set_exe_mime_defaults,
    wakeup_sources_text,
)
from .services.software import Worker, _finish_worker, _install_flatpak_inline, _is_flatpak_installed
from .qt import QDesktopServices, QMessageBox, QUrl
from .widgets import _set_log_panel


class _QuickFixMixin:
    def _force_deep_sleep(self):
        ok, err = force_deep_sleep()
        if ok:
            self._sleep_fix_status.setText(
                "Deep sleep (S3) forced for this session. Put the system to sleep and wake it — "
                "if it works correctly, the fix is working. Add mem_sleep_default=deep to your "
                "kernel arguments to make this permanent."
            )
            self._sleep_fix_status.setObjectName("status-ok")
        else:
            self._sleep_fix_status.setText(
                f"Could not set sleep mode (may not be supported on this platform): {err}"
            )
            self._sleep_fix_status.setObjectName("status-err")
        _restyle(self._sleep_fix_status)

    def _show_wakeup_sources(self):
        result = wakeup_sources_text(timeout=5)
        if result.strip():
            self._sleep_fix_status.setText(f"Wake-enabled devices:\n{result.strip()}")
        else:
            self._sleep_fix_status.setText("No wake sources found (or /sys/bus path unavailable).")
        self._sleep_fix_status.setObjectName("card-copy")
        _restyle(self._sleep_fix_status)

    def _on_file_history(self):
        if _is_flatpak_installed("org.gnome.World.PikaBackup"):
            flatpak_run("org.gnome.World.PikaBackup")
            return
        def _launch_after_install(code: int):
            if code == 0:
                self._backup_btn.setText("Open Pika Backup")
                self._backup_btn.setEnabled(True)
        _install_flatpak_inline(
            self, self._backup_btn, "org.gnome.World.PikaBackup", "Pika Backup",
            done_cb=_launch_after_install,
        )

    def _open_task_manager(self):
        if _is_flatpak_installed("io.missioncenter.MissionCenter"):
            if flatpak_run("io.missioncenter.MissionCenter"):
                return
        for cmd in (["plasma-systemmonitor"], ["ksysguard"], ["konsole", "-e", "btop"], ["konsole", "-e", "top"]):
            if popen(cmd):
                return
        QMessageBox.warning(self, "Task Manager not found", "Could not find System Monitor or a terminal task viewer.")

    def _open_printer_setup(self):
        popen(["sudo", "systemctl", "enable", "--now", "cups"])
        if kcmshell("kcm_printer_manager") or systemsettings():
            return
        QDesktopServices.openUrl(QUrl("http://localhost:631"))

    def _open_volume_mixer(self):
        for cmd in (["pavucontrol-qt"], ["pavucontrol"], ["plasma-pa"]):
            if popen(cmd):
                return
        if kcmshell("kcm_pulseaudio"):
            return
        QMessageBox.information(
            self, "Volume Mixer",
            "Right-click the speaker icon in the system tray and choose Audio Volume Settings,\n"
            "or look for 'Audio Volume' in System Settings."
        )

    def _fix_exe_association(self):
        try:
            set_exe_mime_defaults()
            QMessageBox.information(
                self, "Fix .exe Files",
                "Done. Double-clicking .exe and .msi files will now open Bottles.\n"
                "If Bottles is not installed, install it from the App Store first."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Fix .exe Files", f"Could not update file associations: {exc}")

    def _enable_clipboard_history(self):
        try:
            enable_clipboard_history(max_items=25)
            QMessageBox.information(
                self, "Clipboard History",
                "Clipboard history enabled (25 items).\n"
                "Press Meta+V (Meta+V) to open the clipboard history popup."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Clipboard History", f"Could not enable clipboard history: {exc}")

    def _open_night_light(self):
        if not kcmshell("kcm_nightcolor"):
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


