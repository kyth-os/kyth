import os
import re
import subprocess

# __KYTH_GENERATED_IMPORTS__
from .core_base import _release_worker_when_finished, _restyle
from .services.gaming import (  # noqa: E501
    _PROTONDB_TIER_STYLE, _ProtonDbBatchWorker, _find_ntfs_drives, _find_steam_libraries,
    _load_protondb_cache, _ludusavi_backup_summary, _save_protondb_cache, _scan_steamapps_manifests,
    blocked_compat_lookup
)
from .services.software import _install_flatpak_inline
from .page_cloud_storage import SteamCopyWorker
from .page_compatibility import _COMPAT_GAMES
from .page_windows_migration import WindowsLibraryWorker
from .qt import (  # noqa: E501
    QApplication, QComboBox, QDesktopServices, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QTextEdit, QTimer, QUrl, QVBoxLayout
)
from .widgets import _make_card, _set_log_panel


class _MigrationMixin:
    """Steam library migration, save backup, and modding-migration cards — the GAMING HUB "migration" section."""

    _READY_TIERS = ("native", "platinum", "gold", "silver")

    def _build_steam_library_migration_card(self):
        # ── Steam Library Migration ────────────────────────────────────────────
        self._divider()
        migrate_head = QLabel("Steam Library — Migrate from another system")
        migrate_head.setObjectName("heading")
        migrate_head.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        self._add(migrate_head)
        migrate_sub = QLabel(
            "Dual-booting? Use this tool to copy your Steam library from a other system "
            "NTFS partition directly into Steam on KythOS. The drive is mounted "
            "read-only — your original install is never modified."
        )
        migrate_sub.setObjectName("card-copy")
        migrate_sub.setWordWrap(True)
        self._add(migrate_sub)

        hibernate_warn = QLabel(
            "⚠  Before scanning: boot the other system and do a full Shut Down (not Restart). "
            "other system Fast Startup leaves NTFS volumes in a hibernated state — Linux "
            "can read them safely read-only, but other system may report errors on resume "
            "if any other tool writes to the partition. This tool never writes to it."
        )
        hibernate_warn.setObjectName("card-copy")
        hibernate_warn.setWordWrap(True)
        hibernate_warn.setStyleSheet("color: #f0a500; padding: 6px 0;")
        self._add(hibernate_warn)

        migrate_card, migrate_layout = _make_card()

        # Drive selection
        drive_row = QHBoxLayout()
        drive_row.setSpacing(8)
        drive_lbl = QLabel("PC drive:")
        drive_lbl.setObjectName("card-copy")
        drive_row.addWidget(drive_lbl)
        self._drive_combo = QComboBox()
        self._drive_combo.setMinimumWidth(280)
        drive_row.addWidget(self._drive_combo)
        migrate_refresh_btn = QPushButton("Refresh")
        migrate_refresh_btn.clicked.connect(self._refresh_ntfs_drives)
        drive_row.addWidget(migrate_refresh_btn)
        migrate_scan_btn = QPushButton("Scan for Steam")
        migrate_scan_btn.setObjectName("primary")
        migrate_scan_btn.clicked.connect(self._scan_steam_on_drive)
        drive_row.addWidget(migrate_scan_btn)
        drive_row.addStretch()
        migrate_layout.addLayout(drive_row)

        self._migrate_found_lbl = QLabel("Select a drive above and click Scan for Steam.")
        self._migrate_found_lbl.setObjectName("card-copy")
        self._migrate_found_lbl.setWordWrap(True)
        migrate_layout.addWidget(self._migrate_found_lbl)

        self._lib_combo = QComboBox()
        self._lib_combo.setMinimumWidth(400)
        self._lib_combo.hide()
        migrate_layout.addWidget(self._lib_combo)

        # Per-game readiness for the scanned game library — answers
        # "can I play *my* games?" before any copying happens.
        check_row = QHBoxLayout()
        check_row.setSpacing(8)
        self._winlib_check_btn = QPushButton("Check My Games")
        self._winlib_check_btn.hide()
        self._winlib_check_btn.clicked.connect(self._check_windows_library_compat)
        check_row.addWidget(self._winlib_check_btn)
        check_row.addStretch()
        migrate_layout.addLayout(check_row)
        self._winlib_summary_lbl = QLabel()
        self._winlib_summary_lbl.setObjectName("card-copy")
        self._winlib_summary_lbl.setWordWrap(True)
        self._winlib_summary_lbl.hide()
        migrate_layout.addWidget(self._winlib_summary_lbl)
        self._winlib_rows = QVBoxLayout()
        self._winlib_rows.setSpacing(6)
        migrate_layout.addLayout(self._winlib_rows)
        self._winlib_games: list[dict] = []
        self._winlib_protondb_worker: _ProtonDbBatchWorker | None = None

        # Destination
        dst_row = QHBoxLayout()
        dst_row.setSpacing(8)
        dst_lbl = QLabel("Copy to:")
        dst_lbl.setObjectName("card-copy")
        dst_row.addWidget(dst_lbl)
        self._migrate_dst_edit = QLineEdit(
            os.path.expanduser("~/.local/share/Steam/steamapps")
        )
        dst_row.addWidget(self._migrate_dst_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_migrate_dst)
        dst_row.addWidget(browse_btn)
        migrate_layout.addLayout(dst_row)

        # Copy controls
        copy_btn_row = QHBoxLayout()
        copy_btn_row.setSpacing(8)
        self._copy_btn = QPushButton("Copy Library")
        self._copy_btn.setObjectName("primary")
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._start_steam_copy)
        copy_btn_row.addWidget(self._copy_btn)
        self._copy_cancel_btn = QPushButton("Cancel")
        self._copy_cancel_btn.hide()
        self._copy_cancel_btn.clicked.connect(self._cancel_steam_copy)
        copy_btn_row.addWidget(self._copy_cancel_btn)
        copy_btn_row.addStretch()
        migrate_layout.addLayout(copy_btn_row)

        self._migrate_status = QLabel()
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.hide()
        migrate_layout.addWidget(self._migrate_status)

        self._migrate_progress = QProgressBar()
        self._migrate_progress.setRange(0, 0)
        self._migrate_progress.hide()
        migrate_layout.addWidget(self._migrate_progress)

        self._migrate_log_toggle = QPushButton("Show details")
        self._migrate_log_toggle.setCheckable(True)
        self._migrate_log_toggle.hide()
        self._migrate_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._migrate_log_toggle, self._migrate_log, checked)
        )
        migrate_layout.addWidget(self._migrate_log_toggle)

        self._migrate_log = QTextEdit()
        self._migrate_log.document().setMaximumBlockCount(5000)
        self._migrate_log.setReadOnly(True)
        self._migrate_log.setMaximumHeight(140)
        self._migrate_log.hide()
        migrate_layout.addWidget(self._migrate_log)

        self._add(migrate_card)
        self._migrate_worker = None
        self._scanned_mount = None

    def _build_save_backup_card(self):
        # ── Save backup / restore ─────────────────────────────────────────────
        self._divider()
        saves_card, saves_layout = _make_card("card-accent-ok")
        saves_title = QLabel("Game Saves — Back Up Before You Switch")
        saves_title.setObjectName("card-title")
        saves_layout.addWidget(saves_title)
        saves_desc = QLabel(
            "KythOS recommends Ludusavi for game save backup and restore. Run it "
            "before a other system migration, after importing a library, and before "
            "large modding sessions."
        )
        saves_desc.setObjectName("card-copy")
        saves_desc.setWordWrap(True)
        saves_layout.addWidget(saves_desc)
        self._saves_status_lbl = QLabel("")
        self._saves_status_lbl.setObjectName("card-copy")
        self._saves_status_lbl.setWordWrap(True)
        saves_layout.addWidget(self._saves_status_lbl)
        saves_btns = QHBoxLayout()
        saves_btns.setSpacing(8)
        ludusavi_btn = QPushButton("Install Ludusavi")
        ludusavi_btn.clicked.connect(lambda _=False, b=ludusavi_btn: _install_flatpak_inline(
            self, b, "com.github.mtkennerly.ludusavi", "Ludusavi"))
        saves_btns.addWidget(ludusavi_btn)
        ludusavi_open_btn = QPushButton("Open Ludusavi")
        ludusavi_open_btn.clicked.connect(lambda _=False: subprocess.Popen(["flatpak", "run", "com.github.mtkennerly.ludusavi"]))
        saves_btns.addWidget(ludusavi_open_btn)
        saves_refresh_btn = QPushButton("Refresh Status")
        saves_refresh_btn.clicked.connect(self._refresh_gaming_dashboard)
        saves_btns.addWidget(saves_refresh_btn)
        saves_doc_btn = QPushButton("Save Migration Checklist")
        saves_doc_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/mrtrick37/kyth/blob/main/docs/game-save-migration.md")))
        saves_btns.addWidget(saves_doc_btn)
        saves_btns.addStretch()
        saves_layout.addLayout(saves_btns)
        self._add(saves_card)

    def _build_modding_migration_card(self):
        # ── Modding migration ────────────────────────────────────────────────
        mods_card, mods_layout = _make_card()
        mods_title = QLabel("Mods — Nexus, MO2, SteamTinkerLaunch")
        mods_title.setObjectName("card-title")
        mods_layout.addWidget(mods_title)
        mods_desc = QLabel(
            "Start with Steam Workshop and native mod managers when a game provides "
            "them. For Bethesda-style load orders, use SteamTinkerLaunch to install "
            "Mod Organizer 2 per game; use Bottles for standalone patchers and tools."
        )
        mods_desc.setObjectName("card-copy")
        mods_desc.setWordWrap(True)
        mods_layout.addWidget(mods_desc)
        mods_btns = QHBoxLayout()
        mods_btns.setSpacing(8)
        protonup_btn = QPushButton("Open ProtonUp-Qt")
        protonup_btn.clicked.connect(lambda _=False: self._open_protonupqt())
        mods_btns.addWidget(protonup_btn)
        bottles_btn = QPushButton("Install Bottles")
        bottles_btn.clicked.connect(lambda _=False, b=bottles_btn: _install_flatpak_inline(
            self, b, "com.usebottles.bottles", "Bottles"))
        mods_btns.addWidget(bottles_btn)
        mods_doc_btn = QPushButton("Modding Guide")
        mods_doc_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/mrtrick37/kyth/blob/main/docs/modding-on-kythos.md")))
        mods_btns.addWidget(mods_doc_btn)
        mods_btns.addStretch()
        mods_layout.addLayout(mods_btns)
        self._add(mods_card)

    def _refresh_save_status(self):
        if not hasattr(self, "_saves_status_lbl"):
            return
        self._saves_status_lbl.setText("Scanning save backup tools…")
        self._start_data_worker("saves", _ludusavi_backup_summary)

    def _render_save_status(self, data):
        if not hasattr(self, "_saves_status_lbl") or not data:
            return
        status, title, summary = data
        prefix = {
            "ok": "Ready",
            "warn": "Needs setup",
            "err": "Needs fix",
            "dim": "Optional",
        }.get(status, "Optional")
        self._saves_status_lbl.setText(f"{prefix}: {title} - {summary}")

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._dashboard_loaded and "dashboard" not in self._data_workers:
            self._refresh_gaming_dashboard()
        QTimer.singleShot(80, self._refresh_status)
        if not self._win_lib_probed:
            self._win_lib_probed = True
            worker = WindowsLibraryWorker()
            self._win_lib_worker = worker
            worker.result.connect(self._on_win_lib_result)
            _release_worker_when_finished(self, "_win_lib_worker", worker)
            worker.start()

    def _on_win_lib_result(self, partitions: list) -> None:
        if not partitions:
            return

        # Clear any previous content
        while self._win_lib_layout.count():
            item = self._win_lib_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        any_dirty = any(p["is_dirty"] or p["is_hibernated"] for p in partitions)
        any_clean = any(not p["is_dirty"] and not p["is_hibernated"] for p in partitions)

        title_lbl = QLabel("other system Drive Detected")
        title_lbl.setObjectName("card-title")
        self._win_lib_layout.addWidget(title_lbl)

        if any_dirty:
            self._win_lib_card.setObjectName("card-accent-err")
            _restyle(self._win_lib_card)
            warn = QLabel(
                "⚠  Your system partition is in a hibernated or dirty state — "
                "this means other system used Fast Startup or wasn't shut down cleanly.\n\n"
                "To safely import your games:\n"
                "  1.  Boot into other system\n"
                "  2.  Open Start → Settings → System → Power & Sleep → Additional power settings\n"
                "  3.  Click \"Choose what the power buttons do\" → \"Turn on fast startup\" — disable it\n"
                "  4.  Do a full Shut Down (not Restart)\n"
                "  5.  Come back to KythOS and use the Steam Library tool below"
            )
            warn.setObjectName("card-copy")
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #d4a843;")
            self._win_lib_layout.addWidget(warn)

        if any_clean:
            self._win_lib_card.setObjectName("card-accent-ok")
            _restyle(self._win_lib_card)
            found_any_steam = any(p["steam_paths"] for p in partitions if not p["is_dirty"])
            if found_any_steam:
                msg = QLabel(
                    "✓  Your Steam library was found on this drive.\n"
                    "Use the Steam Library tool below to copy your games to KythOS — "
                    "the drive is accessed read-only, your original install is never touched."
                )
            else:
                msg = QLabel(
                    "✓  A clean PC drive is available.\n"
                    "Use the Steam Library tool below to scan it and copy games to KythOS."
                )
            msg.setObjectName("card-copy")
            msg.setWordWrap(True)
            self._win_lib_layout.addWidget(msg)

        self._win_lib_card.show()

    def _refresh_ntfs_drives(self):
        self._drive_combo.clear()
        drives = [d for d in _find_ntfs_drives() if not d.get("is_bitlocker")]
        if not drives:
            self._drive_combo.addItem("No NTFS partitions found")
            return
        for d in drives:
            label = f"{d['dev']}  {d['size']}  {d['label'] or '(no label)'}"
            if d["mount"]:
                label += f"  [mounted at {d['mount']}]"
            self._drive_combo.addItem(label, userData=d)

    def _scan_steam_on_drive(self):
        drive = self._drive_combo.currentData()
        if not drive:
            return

        mount = drive["mount"]

        if not mount:
            self._migrate_status.setText(f"Mounting {drive['dev']}…")
            self._migrate_status.setObjectName("subheading")
            self._migrate_status.show()
            _restyle(self._migrate_status)
            QApplication.processEvents()
            try:
                # Prefer the kernel ntfs3 driver: it is dramatically faster than
                # the FUSE ntfs-3g default for the multi-hundred-GB copies this
                # page encourages. Read-only either way; fall back to the stock
                # driver when udisks or the kernel rejects ntfs3.
                r = subprocess.run(
                    ["udisksctl", "mount", "-b", drive["dev"], "-t", "ntfs3",
                     "--options", "ro", "--no-user-interaction"],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode != 0:
                    r = subprocess.run(
                        ["udisksctl", "mount", "-b", drive["dev"],
                         "--options", "ro", "--no-user-interaction"],
                        capture_output=True, text=True, timeout=15,
                    )
                if r.returncode != 0:
                    err = r.stderr.strip()
                    if "hibernate" in err.lower() or "windows" in err.lower():
                        self._migrate_status.setText(
                            "Mount blocked: The other system did not shut down cleanly (Fast Startup / hibernate). "
                            "Boot the other system and do a full shut down, then try again."
                        )
                    else:
                        self._migrate_status.setText(f"Mount failed: {err}")
                    self._migrate_status.setObjectName("status-err")
                    _restyle(self._migrate_status)
                    return
                # udisksctl prints: "Mounted /dev/sdX1 at /run/media/user/Label."
                m = re.search(r" at (.+?)\.$", r.stdout.strip())
                mount = m.group(1) if m else None
                if not mount:
                    self._migrate_status.setText("Could not determine mount point from udisksctl output.")
                    self._migrate_status.setObjectName("status-err")
                    _restyle(self._migrate_status)
                    return
            except Exception as exc:
                self._migrate_status.setText(f"Mount error: {exc}")
                self._migrate_status.setObjectName("status-err")
                _restyle(self._migrate_status)
                return

        self._scanned_mount = mount
        self._migrate_status.setText(f"Scanning {mount} for Steam libraries…")
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.show()
        _restyle(self._migrate_status)
        QApplication.processEvents()

        libs = _find_steam_libraries(mount)
        self._lib_combo.clear()
        self._clear_rows(self._winlib_rows)
        self._winlib_summary_lbl.hide()
        if not libs:
            self._migrate_found_lbl.setText(f"No Steam libraries found on {mount}.")
            self._lib_combo.hide()
            self._winlib_check_btn.hide()
            self._copy_btn.setEnabled(False)
            self._migrate_status.setText("No Steam libraries found on this drive.")
            self._migrate_status.setObjectName("status-err")
            _restyle(self._migrate_status)
            return

        for lib in libs:
            self._lib_combo.addItem(lib)
        self._lib_combo.show()
        self._winlib_check_btn.show()
        self._migrate_found_lbl.setText(f"Found {len(libs)} steamapps folder(s) — select one:")
        self._copy_btn.setEnabled(True)
        self._migrate_status.setText(
            f"Found {len(libs)} folder(s). Click Check My Games for a per-game readiness "
            "report, or Copy Library to start migrating."
        )
        self._migrate_status.setObjectName("status-ok")
        _restyle(self._migrate_status)

    def _check_windows_library_compat(self):
        steamapps = self._lib_combo.currentText().strip()
        if not steamapps:
            return
        games = _scan_steamapps_manifests(steamapps)
        self._winlib_games = games
        self._winlib_summary_lbl.show()
        if not games:
            self._clear_rows(self._winlib_rows)
            self._winlib_summary_lbl.setText("No game manifests found in this folder.")
            return
        cache = _load_protondb_cache()
        self._render_winlib_compat(games, cache)
        uncached = [g["appid"] for g in games if g["appid"] and g["appid"] not in cache]
        if uncached and (self._winlib_protondb_worker is None or not self._winlib_protondb_worker.isRunning()):
            self._winlib_summary_lbl.setText(
                self._winlib_summary_lbl.text() + "  Fetching ProtonDB ratings…"
            )
            worker = _ProtonDbBatchWorker(uncached, cache)
            worker.finished_all.connect(self._on_winlib_protondb_done)
            self._winlib_protondb_worker = worker
            _release_worker_when_finished(self, "_winlib_protondb_worker", worker)
            worker.start()

    def _on_winlib_protondb_done(self, full_cache: dict):
        _save_protondb_cache(full_cache)
        if self._winlib_games:
            self._render_winlib_compat(self._winlib_games, full_cache)

    def _render_winlib_compat(self, games: list[dict], cache: dict[str, str]):
        self._clear_rows(self._winlib_rows)
        blocked_appids, blocked_names = blocked_compat_lookup(_COMPAT_GAMES)
        graded: list[tuple[dict, str, str]] = []  # (game, category, badge text)
        ready = blocked = 0
        for game in games:
            appid = game.get("appid", "")
            name_l = game.get("name", "").lower()
            tier = (cache.get(appid) or "").lower()
            if appid in blocked_appids or name_l in blocked_names:
                blocked += 1
                graded.append((game, "blocked", "Blocked"))
            elif tier in self._READY_TIERS:
                ready += 1
                graded.append((game, "ready", "Native" if tier == "native" else tier.capitalize()))
            elif tier in ("bronze", "borked"):
                graded.append((game, "risky", tier.capitalize()))
            else:
                graded.append((game, "unknown", "Not rated"))
        total = len(games)
        self._winlib_summary_lbl.setText(
            f"{ready} of {total} of your games look ready to play on KythOS. "
            f"{blocked} blocked by anti-cheat, {total - ready - blocked} unrated or with mixed reports. "
            "Based on KythOS compatibility data and ProtonDB community reports."
        )
        # Blocked games first so the bad news is impossible to miss.
        order = {"blocked": 0, "risky": 1, "unknown": 2, "ready": 3}
        graded.sort(key=lambda item: (order[item[1]], item[0]["name"].lower()))
        for game, category, badge_text in graded[:30]:
            self._winlib_rows.addWidget(self._make_winlib_row(game, category, badge_text))
        if len(graded) > 30:
            more = QLabel(f"{len(graded) - 30} more games scanned — the summary above covers all of them.")
            more.setObjectName("card-copy")
            self._winlib_rows.addWidget(more)

    def _make_winlib_row(self, game: dict, category: str, badge_text: str) -> QFrame:
        row = QFrame()
        row.setObjectName({"blocked": "hw-card-err", "risky": "hw-card-warn"}.get(category, "hw-card-dim"))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)
        name_lbl = QLabel(game["name"])
        name_lbl.setObjectName("card-summary")
        layout.addWidget(name_lbl, 1)
        badge = QLabel(f"  {badge_text}  ")
        if category == "blocked":
            badge.setStyleSheet(
                "background:#3a1010; color:#f48771; border:1px solid #5a1a1a; "
                "border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
            )
        else:
            # Native builds aren't a ProtonDB tier; show them platinum-green.
            tier_key = "platinum" if badge_text == "Native" else badge_text.lower()
            bg, fg = _PROTONDB_TIER_STYLE.get(tier_key, ("#252526", "#cccccc"))
            badge.setStyleSheet(
                f"background:{bg}; color:{fg}; "
                "border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
            )
        layout.addWidget(badge)
        return row

    def _browse_migrate_dst(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select destination steamapps folder", self._migrate_dst_edit.text()
        )
        if path:
            self._migrate_dst_edit.setText(path)

    def _start_steam_copy(self):
        if self._migrate_worker and self._migrate_worker.isRunning():
            return
        src = self._lib_combo.currentText().strip()
        dst = self._migrate_dst_edit.text().strip()
        if not src or not dst:
            return
        self._migrate_log.clear()
        self._migrate_log_toggle.show()
        _set_log_panel(self._migrate_log_toggle, self._migrate_log, False)
        self._migrate_progress.show()
        self._migrate_status.setText(f"Copying {src} → {dst}…")
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.show()
        _restyle(self._migrate_status)
        self._copy_btn.setEnabled(False)
        self._copy_cancel_btn.show()
        self._migrate_worker = SteamCopyWorker(src, dst)
        self._migrate_worker.line.connect(lambda ln: (
            self._migrate_log.append(ln),
            self._migrate_log.ensureCursorVisible(),
        ))
        self._migrate_worker.done.connect(self._on_steam_copy_done)
        self._migrate_worker.start()

    def _cancel_steam_copy(self):
        if self._migrate_worker and self._migrate_worker.isRunning():
            self._migrate_worker.stop()

    def _on_steam_copy_done(self, code: int):
        self._migrate_progress.hide()
        self._copy_cancel_btn.hide()
        self._copy_btn.setEnabled(True)
        if code == 0:
            self._migrate_status.setText("Steam library copied successfully.")
            self._migrate_status.setObjectName("status-ok")
            self._migrate_log.append(
                "\nDone. You may need to add this folder as a Steam library in "
                "Steam → Settings → Storage."
            )
        else:
            self._migrate_status.setText(f"Copy failed (exit {code}). See details.")
            self._migrate_status.setObjectName("status-err")
        _restyle(self._migrate_status)
        _set_log_panel(self._migrate_log_toggle, self._migrate_log, True)
