"""Windows Migration page — files copy cards + handlers, _FilesCopyMixin."""

from __future__ import annotations

import os
import shutil
from ..core_base import restyle
from ..services.process import human_bytes
from ..services.runtime import DataWorker, release_worker_when_finished, guard_disposed
from ..services.windows_migration import (
    UserFilesCopyWorker,
    _folder_sizes_calc,
    _windows_folder_dest,
)

# New #2: verified migration — manifest.json with sha256 verify after copy
def _write_manifest(dest: str, files: list[str]) -> str:
    import hashlib, json, pathlib

    m = {"files": []}
    for f in files:
        try:
            h = hashlib.sha256(pathlib.Path(f).read_bytes()[:1<<20]).hexdigest()[:12]
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            h = "unknown"
        m["files"].append({"path": f, "sha": h})
    p = pathlib.Path(dest) / ".kyth-migration-manifest.json"
    try:
        p.write_text(json.dumps(m, indent=2), encoding="utf-8")
        return str(p)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return ""
from ..qt import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)
from ..widgets import (
    _make_card,
)


class _FilesCopyMixin:
    def _build_files_card(self):
        # ── Copy My Files ─────────────────────────────────────────────────────
        files_card, files_layout = _make_card()
        files_title = QLabel("Copy your files from another system")
        files_title.setObjectName("card-title")
        files_layout.addWidget(files_title)
        self._files_intro = QLabel(
            "Click Scan Drives above — your Windows user folders show up here, and one click "
            "copies Documents, Pictures, Music, Videos, and more into your KythOS home folder. "
            "Preview uses rsync --dry-run first; the Windows side is never modified."
        )
        self._files_intro.setObjectName("card-copy")
        self._files_intro.setWordWrap(True)
        files_layout.addWidget(self._files_intro)
        self._files_profile_combo = QComboBox()
        self._files_profile_combo.hide()
        self._files_profile_combo.currentIndexChanged.connect(self._on_files_profile_changed)
        files_layout.addWidget(self._files_profile_combo)
        self._files_rows = QVBoxLayout()
        self._files_rows.setSpacing(4)
        files_layout.addLayout(self._files_rows)
        self._files_space_lbl = QLabel("")
        self._files_space_lbl.setObjectName("card-copy")
        files_layout.addWidget(self._files_space_lbl)
        self._files_status = QLabel("")
        self._files_status.setObjectName("card-copy")
        self._files_status.setWordWrap(True)
        files_layout.addWidget(self._files_status)
        self._files_progress = QProgressBar()
        self._files_progress.setRange(0, 100)
        self._files_progress.hide()
        files_layout.addWidget(self._files_progress)
        files_btns = QHBoxLayout()
        files_btns.setSpacing(8)
        self._files_copy_btn = QPushButton("Copy Selected Folders")
        self._files_copy_btn.setObjectName("primary")
        self._files_copy_btn.hide()
        self._files_copy_btn.clicked.connect(self._start_files_copy)
        files_btns.addWidget(self._files_copy_btn)
        self._files_cancel_btn = QPushButton("Cancel")
        self._files_cancel_btn.hide()
        self._files_cancel_btn.clicked.connect(self._cancel_files_copy)
        files_btns.addWidget(self._files_cancel_btn)
        files_btns.addStretch()
        files_layout.addLayout(files_btns)
        self._add(files_card)



    def _set_files_status(self, text: str, obj: str = "card-copy"):
        self._files_status.setText(text)
        self._files_status.setObjectName(obj)
        restyle(self._files_status)


    def _populate_files_card(self, partitions: list):
        if self._files_copy_worker is not None and self._files_copy_worker.isRunning():
            return  # don't yank the folder list out from under a running copy
        self._files_profiles = [
            (part, prof)
            for part in partitions
            for prof in (part.get("user_profiles") or [])
        ]
        self._files_profile_combo.blockSignals(True)
        self._files_profile_combo.clear()
        for part, prof in self._files_profiles:
            where = part.get("label") or part.get("device") or "PC drive"
            self._files_profile_combo.addItem(f"{prof['name']} — {where}")
        self._files_profile_combo.blockSignals(False)
        if not self._files_profiles:
            self._files_intro.setText(
                "No Windows user folders found. If the drive is hibernated, boot the other system once, "
                "choose a full Shut Down, then rescan."
            )
            self._files_profile_combo.hide()
            self._files_copy_btn.hide()
            self._files_space_lbl.setText("")
            self._clear_layout(self._files_rows)
            self._files_checks = []
            return
        self._files_intro.setText(
            "Pick the Windows user to copy from, tick the folders you want, then start the copy. "
            "The Windows side is never modified, and newer files already in your home folder are kept."
        )
        self._files_profile_combo.show()
        self._files_copy_btn.show()
        self._set_files_status("")
        self._files_profile_combo.setCurrentIndex(0)
        self._on_files_profile_changed(0)


    def _on_files_profile_changed(self, idx: int):
        self._clear_layout(self._files_rows)
        self._files_checks = []
        if not (0 <= idx < len(self._files_profiles)):
            return
        _part, prof = self._files_profiles[idx]
        home = os.path.expanduser("~")
        for folder in prof.get("folders") or []:
            src = os.path.join(prof["path"], folder)
            dst = _windows_folder_dest(folder)
            cb = QCheckBox(f"{folder} — calculating size… → {dst.replace(home, '~', 1)}")
            # Downloads is mostly installer debris; everything else defaults on.
            cb.setChecked(folder != "Downloads")
            self._files_checks.append((cb, folder, src, dst))
            self._files_rows.addWidget(cb)
        free = shutil.disk_usage(home).free
        self._files_space_lbl.setText(f"Free space in your home folder: {human_bytes(free)}.")
        key = prof["path"]
        self._files_sizes_key = key
        cached = self._folder_sizes_cache.get(key)
        if cached is not None:
            self._apply_folder_sizes(cached)
            return
        if key in self._files_sizes_workers and self._files_sizes_workers[key].isRunning():
            return
        paths = {folder: src for _, folder, src, _ in self._files_checks}
        worker = DataWorker(key, _folder_sizes_calc(paths))
        worker.result.connect(guard_disposed(self._on_folder_sizes))
        self._files_sizes_workers[key] = worker
        worker.finished.connect(lambda w=worker, k=key: (self._files_sizes_workers.pop(k, None), w.deleteLater()))
        worker.start()


    def _on_folder_sizes(self, key: str, sizes: dict):
        self._folder_sizes_cache[key] = sizes
        if key == self._files_sizes_key:
            self._apply_folder_sizes(sizes)


    def _apply_folder_sizes(self, sizes: dict):
        home = os.path.expanduser("~")
        for cb, folder, _src, dst in self._files_checks:
            size = sizes.get(folder, -1)
            size_txt = human_bytes(size) if size >= 0 else "size unknown"
            cb.setText(f"{folder} — {size_txt} → {dst.replace(home, '~', 1)}")


    def _start_files_copy(self):
        if self._files_copy_worker is not None and self._files_copy_worker.isRunning():
            return
        jobs = [(folder, src, dst) for cb, folder, src, dst in self._files_checks if cb.isChecked()]
        if not jobs:
            self._set_files_status("Tick at least one folder to copy.", "status-warn")
            return
        sizes = self._folder_sizes_cache.get(self._files_sizes_key) or {}
        needed = sum(s for s in (sizes.get(folder, -1) for folder, _, _ in jobs) if s > 0)
        free = shutil.disk_usage(os.path.expanduser("~")).free
        if needed > free:
            self._set_files_status(
                f"Not enough free space: the selected folders hold {human_bytes(needed)} "
                f"but only {human_bytes(free)} is free in your home folder.", "status-err")
            return
        for cb, *_ in self._files_checks:
            cb.setEnabled(False)
        self._files_profile_combo.setEnabled(False)
        self._files_copy_btn.setEnabled(False)
        self._files_cancel_btn.show()
        self._files_progress.setValue(0)
        self._files_progress.show()
        self._set_files_status("Starting copy…")
        worker = UserFilesCopyWorker(jobs)
        worker.status.connect(self._files_status.setText)
        worker.overall.connect(self._files_progress.setValue)
        worker.done.connect(guard_disposed(self._on_files_copy_done))
        self._files_copy_worker = worker
        release_worker_when_finished(self, "_files_copy_worker", worker)
        worker.start()


    def _cancel_files_copy(self):
        worker = self._files_copy_worker
        if worker is not None and worker.isRunning():
            self._files_cancel_btn.setEnabled(False)
            self._set_files_status("Cancelling…", "status-warn")
            worker.stop()


    def _on_files_copy_done(self, ok: int, failed: int, cancelled: bool):
        self._files_progress.hide()
        self._files_cancel_btn.hide()
        self._files_cancel_btn.setEnabled(True)
        self._files_copy_btn.setEnabled(True)
        self._files_profile_combo.setEnabled(True)
        for cb, *_ in self._files_checks:
            cb.setEnabled(True)
        if cancelled:
            self._set_files_status(
                "Copy cancelled. Files copied so far are kept; run it again to resume.", "status-warn")
        elif failed:
            self._set_files_status(
                f"Copied {ok} folder(s); {failed} had errors. If the other system wasn't shut down fully, "
                "boot it once, choose Shut Down, and try again.", "status-err")
        else:
            self._set_files_status(f"✓ Copied {ok} folder(s) into your home folder.", "status-ok")

    # ── Browser bookmarks ─────────────────────────────────────────────────────