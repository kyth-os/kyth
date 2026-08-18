import re

# __KYTH_GENERATED_IMPORTS__
from ..core_base import restyle
from ..services.runtime import DataWorker, guard_disposed, release_worker_when_finished
from ..services.process import run_command
from ..services.gaming import (
    _PROTONDB_TIER_STYLE, _ProtonDbBatchWorker, _find_ntfs_drives, _find_steam_libraries,
    _load_protondb_cache, _save_protondb_cache, _scan_steamapps_manifests, blocked_compat_lookup,
)
from ..services.cloud_sync import SteamCopyWorker
from ..services.gaming import _COMPAT_GAMES
from ..qt import (
    QFileDialog, QFrame, QHBoxLayout, QLabel,
)
from ..widgets import _set_log_panel


class _ScanMixin:
    _READY_TIERS = ("native", "platinum", "gold", "silver")

    def _refresh_ntfs_drives(self):
        # _find_ntfs_drives() is probe_cached (services/hardware/drives.py)
        # but a cold cache still means a synchronous lsblk spawn here \u2014 and
        # this now fires automatically every time the Migration tab is
        # opened (page_gaming.py's _kick_section_refresh), not just on an
        # explicit Refresh click.
        if self._ntfs_drives_worker is not None:
            return
        self._drive_combo.clear()
        self._drive_combo.addItem("Checking for NTFS partitions\u2026")
        worker = DataWorker("migration-ntfs-drives", _find_ntfs_drives)
        self._ntfs_drives_worker = worker
        worker.result.connect(guard_disposed(lambda _key, drives: self._on_ntfs_drives_ready(drives)))
        worker.failed.connect(guard_disposed(lambda _key, _message: self._on_ntfs_drives_ready([])))
        worker.finished.connect(lambda: setattr(self, "_ntfs_drives_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_ntfs_drives_ready(self, drives: object):
        self._drive_combo.clear()
        filtered = [d for d in (drives or []) if not d.get("is_bitlocker")]
        if not filtered:
            self._drive_combo.addItem("No NTFS partitions found")
            return
        for d in filtered:
            label = f"{d['dev']}  {d['size']}  {d['label'] or '(no label)'}"
            if d["mount"]:
                label += f"  [mounted at {d['mount']}]"
            self._drive_combo.addItem(label, userData=d)

    def _scan_steam_on_drive(self):
        if self._steam_scan_worker is not None:
            return
        drive = self._drive_combo.currentData()
        if not drive:
            return

        self._migrate_status.setText(f"Checking {drive['dev']}\u2026")
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.show()
        restyle(self._migrate_status)

        # Mounting (udisksctl) and scanning are both subprocess-backed and
        # used to run synchronously here, papered over with
        # QApplication.processEvents() instead of a real worker. Both steps
        # move to a background DataWorker; _on_steam_scan_ready() applies
        # whichever outcome it reports to the widgets below.
        worker = DataWorker("migration-steam-scan", lambda: self._fetch_steam_scan(drive))
        self._steam_scan_worker = worker
        worker.result.connect(guard_disposed(lambda _key, result: self._on_steam_scan_ready(result)))
        worker.failed.connect(guard_disposed(lambda _key, message: self._on_steam_scan_ready({"error_kind": "worker", "detail": message})))
        worker.finished.connect(lambda: setattr(self, "_steam_scan_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    @staticmethod
    def _fetch_steam_scan(drive: dict) -> dict:
        """Run off the GUI thread by _scan_steam_on_drive()'s DataWorker:
        mount the drive (if not already mounted) and scan it for Steam
        libraries. Returns {"mount", "libs"} on success, or
        {"error_kind", "detail"} \u2014 never touches a widget."""
        mount = drive["mount"]

        if not mount:
            try:
                r = run_command(
                    ["udisksctl", "mount", "-b", drive["dev"], "-t", "ntfs3",
                     "--options", "ro", "--no-user-interaction"],
                    timeout=15,
                )
                if r is None or r.returncode != 0:
                    r = run_command(
                        ["udisksctl", "mount", "-b", drive["dev"],
                         "--options", "ro", "--no-user-interaction"],
                        timeout=15,
                    )
                if r is None or r.returncode != 0:
                    return {"error_kind": "mount", "detail": (r.stderr if r else "").strip()}
                m = re.search(r" at (.+?)\.$", r.stdout.strip())
                mount = m.group(1) if m else None
                if not mount:
                    return {"error_kind": "mount-point", "detail": ""}
            except Exception as exc:
                return {"error_kind": "mount-exception", "detail": str(exc)}

        return {"mount": mount, "libs": _find_steam_libraries(mount)}

    def _on_steam_scan_ready(self, result: object) -> None:
        result = result if isinstance(result, dict) else {"error_kind": "worker", "detail": ""}
        error_kind = result.get("error_kind")
        if error_kind:
            detail = result.get("detail") or ""
            if error_kind == "mount":
                if "hibernate" in detail.lower() or "windows" in detail.lower():
                    self._migrate_status.setText(
                        "Mount blocked: The other system did not shut down cleanly (Fast Startup / hibernate). "
                        "Boot the other system and do a full shut down, then try again."
                    )
                else:
                    self._migrate_status.setText(f"Mount failed: {detail}")
            elif error_kind == "mount-point":
                self._migrate_status.setText("Could not determine mount point from udisksctl output.")
            elif error_kind == "mount-exception":
                self._migrate_status.setText(f"Mount error: {detail}")
            else:
                self._migrate_status.setText(f"Scan error: {detail or 'unknown error'}")
            self._migrate_status.setObjectName("status-err")
            restyle(self._migrate_status)
            return

        mount = result["mount"]
        libs = result["libs"]
        self._scanned_mount = mount

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
            restyle(self._migrate_status)
            return

        for lib in libs:
            self._lib_combo.addItem(lib)
        self._lib_combo.show()
        self._winlib_check_btn.show()
        self._migrate_found_lbl.setText(f"Found {len(libs)} steamapps folder(s) \u2014 select one:")
        self._copy_btn.setEnabled(True)
        self._migrate_status.setText(
            f"Found {len(libs)} folder(s). Click Check My Games for a per-game readiness "
            "report, or Copy Library to start migrating."
        )
        self._migrate_status.setObjectName("status-ok")
        restyle(self._migrate_status)

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
                self._winlib_summary_lbl.text() + "  Fetching ProtonDB ratings\u2026"
            )
            worker = _ProtonDbBatchWorker(uncached, cache)
            worker.finished_all.connect(self._on_winlib_protondb_done)
            self._winlib_protondb_worker = worker
            release_worker_when_finished(self, "_winlib_protondb_worker", worker)
            worker.start()

    def _on_winlib_protondb_done(self, full_cache: dict):
        _save_protondb_cache(full_cache)
        if self._winlib_games:
            self._render_winlib_compat(self._winlib_games, full_cache)

    def _render_winlib_compat(self, games: list[dict], cache: dict[str, str]):
        self._clear_rows(self._winlib_rows)
        blocked_appids, blocked_names = blocked_compat_lookup(_COMPAT_GAMES)
        graded: list[tuple[dict, str, str]] = []
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
        order = {"blocked": 0, "risky": 1, "unknown": 2, "ready": 3}
        graded.sort(key=lambda item: (order[item[1]], item[0]["name"].lower()))
        for game, category, badge_text in graded[:30]:
            self._winlib_rows.addWidget(self._make_winlib_row(game, category, badge_text))
        if len(graded) > 30:
            more = QLabel(f"{len(graded) - 30} more games scanned \u2014 the summary above covers all of them.")
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
        badge = QLabel(badge_text)
        if category == "blocked":
            badge.setObjectName("status-err")
        else:
            tier_key = "platinum" if badge_text == "Native" else badge_text.lower()
            badge.setObjectName(_PROTONDB_TIER_STYLE.get(tier_key, "status-dim"))
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
        self._migrate_status.setText(f"Copying {src} \u2192 {dst}\u2026")
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.show()
        restyle(self._migrate_status)
        self._copy_btn.setEnabled(False)
        self._copy_cancel_btn.show()
        self._migrate_worker = SteamCopyWorker(src, dst)
        self._migrate_worker.finished.connect(lambda: setattr(self, "_migrate_worker", None))
        self._migrate_worker.finished.connect(self._migrate_worker.deleteLater)
        self._migrate_worker.line.connect(guard_disposed(lambda ln: (
            self._migrate_log.append(ln),
            self._migrate_log.ensureCursorVisible(),
        )))
        self._migrate_worker.done.connect(guard_disposed(self._on_steam_copy_done))
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
                "Steam \u2192 Settings \u2192 Storage."
            )
        else:
            self._migrate_status.setText(f"Copy failed (exit {code}). See details.")
            self._migrate_status.setObjectName("status-err")
        restyle(self._migrate_status)
        _set_log_panel(self._migrate_log_toggle, self._migrate_log, True)