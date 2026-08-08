"""Pika/DejaDup backup confidence helpers — thin probe for the Repair > File History card."""
from __future__ import annotations

import os
import shutil


def _pika_backup_summary() -> tuple[str, str, str]:
    """Return (status, title, summary) for Pika Backup.

    status: ok|warn|dim — mirrors _ludusavi_backup_summary pattern so the
    Repair card can reuse the same badge logic. Probe is synchronous but
    cheap; caller wraps in DataWorker to keep GUI thread unblocked."""
    flatpak_id = "org.gnome.World.PikaBackup"
    try:
        from .flatpak import is_installed
        pika_flatpak = is_installed(flatpak_id)
    except Exception:
        pika_flatpak = False
    pika_bin = shutil.which("pika-backup") is not None or shutil.which("pika_backup") is not None
    if not (pika_flatpak or pika_bin):
        return "dim", "Pika Backup", "Not installed — install Pika Backup from Flathub to get File History for your home folder."
    # Check for existing backup config (Pika stores repos in ~/.config/pika-backup or xdg)
    candidates = [
        os.path.expanduser("~/.config/pika-backup"),
        os.path.expanduser("~/.var/app/org.gnome.World.PikaBackup/config/pika-backup"),
        os.path.expanduser("~/.config/deja-dup"),
    ]
    for path in candidates:
        try:
            if os.path.isdir(path) and os.listdir(path):
                # look for newest file as proxy for last backup
                newest = max(
                    (os.path.join(path, e) for e in os.listdir(path)),
                    key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                    default=None,
                )
                if newest:
                    return "ok", "Pika Backup", f"Backups configured — last config change: {newest}"
                return "ok", "Pika Backup", "Backups configured — open Pika to see schedule and last backup."
        except OSError:
            continue
    return "warn", "Pika Backup", "Installed but no backup scheduled — open Pika Backup to pick a drive and schedule backups."
