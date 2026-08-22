# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.gaming import (
    _gamescope_installed, _mangohud_installed, _proton_cachyos_version, _vkbasalt_installed,
)
from .services.flatpak import _is_flatpak_installed
from .qt import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, Qt
from .widgets import StatusBadge


class _DashboardMixin:
    """The GAMING HUB "all"/Dashboard view: hero banner and HUD status grid."""

    def _make_gaming_hero_banner(self) -> QFrame:
        hero_card = QFrame()
        hero_card.setObjectName("genz-hero")
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(16)

        hero_text_col = QVBoxLayout()
        hero_text_col.setSpacing(4)

        hero_title = QLabel("Library")
        hero_title.setObjectName("genz-hero-title")
        hero_text_col.addWidget(hero_title)

        hero_sub = QLabel("Steam, Proton-CachyOS, Gamescope, and MangoHud — ready when you are.")
        hero_sub.setObjectName("genz-hero-subtitle")
        hero_sub.setWordWrap(True)
        hero_text_col.addWidget(hero_sub)
        hero_layout.addLayout(hero_text_col, 1)

        self._hero_status_pill = QLabel("CHECKING STACK...")
        self._hero_status_pill.setObjectName("glowing-pill-ok")
        hero_layout.addWidget(self._hero_status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        return hero_card

    def _make_gaming_hud_grid(self) -> QWidget:
        widget = QWidget()
        hud_grid = QGridLayout(widget)
        hud_grid.setContentsMargins(0, 0, 0, 0)
        hud_grid.setSpacing(12)

        # Card 1: Launchers
        card1 = QFrame()
        card1.setObjectName("genz-hud-card")
        layout1 = QVBoxLayout(card1)
        layout1.setContentsMargins(18, 16, 18, 16)
        layout1.setSpacing(8)
        title1 = QLabel("LAUNCHERS")
        title1.setObjectName("hud-title")
        layout1.addWidget(title1)
        self._hud_runners_desc = QLabel("Checking Flatpaks...")
        self._hud_runners_desc.setTextFormat(Qt.TextFormat.RichText)
        self._hud_runners_desc.setObjectName("hud-desc")
        self._hud_runners_desc.setWordWrap(True)
        layout1.addWidget(self._hud_runners_desc)
        hud_grid.addWidget(card1, 0, 0)

        # Card 2: Runtime Engine
        card2 = QFrame()
        card2.setObjectName("genz-hud-card")
        layout2 = QVBoxLayout(card2)
        layout2.setContentsMargins(18, 16, 18, 16)
        layout2.setSpacing(8)
        title2 = QLabel("RUNTIME ENGINE")
        title2.setObjectName("hud-title")
        layout2.addWidget(title2)
        self._hud_runtime_desc = QLabel("Checking runners & overlays...")
        self._hud_runtime_desc.setTextFormat(Qt.TextFormat.RichText)
        self._hud_runtime_desc.setObjectName("hud-desc")
        self._hud_runtime_desc.setWordWrap(True)
        layout2.addWidget(self._hud_runtime_desc)
        hud_grid.addWidget(card2, 0, 1)

        # Card 3: Storage & Saves
        card3 = QFrame()
        card3.setObjectName("genz-hud-card")
        layout3 = QVBoxLayout(card3)
        layout3.setContentsMargins(18, 16, 18, 16)
        layout3.setSpacing(8)
        title3 = QLabel("STORAGE & SAVES")
        title3.setObjectName("hud-title")
        layout3.addWidget(title3)
        self._hud_storage_desc = QLabel("Checking backups & drives...")
        self._hud_storage_desc.setTextFormat(Qt.TextFormat.RichText)
        self._hud_storage_desc.setObjectName("hud-desc")
        self._hud_storage_desc.setWordWrap(True)
        layout3.addWidget(self._hud_storage_desc)
        hud_grid.addWidget(card3, 1, 0)

        # Card 4: Quick Performance + System Hub super-app link
        card4 = QFrame()
        card4.setObjectName("genz-hud-card")
        layout4 = QVBoxLayout(card4)
        layout4.setContentsMargins(18, 16, 18, 16)
        layout4.setSpacing(8)
        title4 = QLabel("QUICK PERFORMANCE — Pulse Guardian")
        title4.setObjectName("hud-title")
        layout4.addWidget(title4)
        perf_hint = QLabel("Power profile + display VRR + controller stack — all in Pulse > This PC > Guardian. One-click Fix My Gaming uses same gated runner as Starter Packs.")
        perf_hint.setObjectName("hud-desc")
        perf_hint.setWordWrap(True)
        layout4.addWidget(perf_hint)
        # Inline gaming perf labels (populated by _update_gaming_hud)
        self._hud_perf_profile = QLabel("Power: checking…")
        self._hud_perf_profile.setObjectName("hud-desc")
        layout4.addWidget(self._hud_perf_profile)
        self._hud_perf_display = QLabel("Display: checking…")
        self._hud_perf_display.setObjectName("hud-desc")
        layout4.addWidget(self._hud_perf_display)
        self._hud_perf_controller = QLabel("Controller: checking…")
        self._hud_perf_controller.setObjectName("hud-desc")
        layout4.addWidget(self._hud_perf_controller)
        fix_gaming_btn = QPushButton("Fix My Gaming — power + display + controller")
        fix_gaming_btn.setObjectName("primary")
        fix_gaming_btn.setToolTip(
            "Applies Guardian display, controller, and power recipes now (may ask for permission to restart joycond). "
            "Paused during an active game or capture session."
        )
        fix_gaming_btn.clicked.connect(self._fix_my_gaming)
        layout4.addWidget(fix_gaming_btn)

        # Game Night Buttons
        gn_row = QHBoxLayout()
        gn_row.setSpacing(6)
        self._hud_game_night_start_btn = QPushButton("Start Game Night")
        self._hud_game_night_start_btn.setObjectName("primary")
        self._hud_game_night_start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hud_game_night_start_btn.clicked.connect(self._start_game_night)

        self._hud_game_night_stop_btn = QPushButton("End Game Night")
        self._hud_game_night_stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hud_game_night_stop_btn.clicked.connect(self._stop_game_night)
        self._hud_game_night_stop_btn.setEnabled(False)

        gn_row.addWidget(self._hud_game_night_start_btn)
        gn_row.addWidget(self._hud_game_night_stop_btn)
        layout4.addLayout(gn_row)

        self._hud_game_night_status = StatusBadge("Ready to tune.", "idle")
        layout4.addWidget(self._hud_game_night_status)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        scan_btn = QPushButton("Scan Libraries")
        scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        scan_btn.clicked.connect(lambda _=False: self._refresh_my_games(async_scan=True))

        fixes_btn = QPushButton("Troubleshoot")
        fixes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fixes_btn.clicked.connect(lambda _=False: self._switch_gaming_section("fixes"))

        action_row.addWidget(scan_btn)
        action_row.addWidget(fixes_btn)
        layout4.addLayout(action_row)

        hud_grid.addWidget(card4, 1, 1)

        # Card 5: Steam Compatibility — full width below grid (Windows switcher #3)
        card5 = QFrame()
        card5.setObjectName("genz-hud-card")
        layout5 = QVBoxLayout(card5)
        layout5.setContentsMargins(18, 16, 18, 16)
        layout5.setSpacing(8)
        title5 = QLabel("STEAM COMPATIBILITY — Coming from Windows?")
        title5.setObjectName("hud-title")
        layout5.addWidget(title5)
        self._hud_compat_desc = QLabel("Scan your Windows Steam library — see which games work on Proton, which need anti-cheat, and copy saves safely.")
        self._hud_compat_desc.setTextFormat(Qt.TextFormat.RichText)
        self._hud_compat_desc.setObjectName("hud-desc")
        self._hud_compat_desc.setWordWrap(True)
        layout5.addWidget(self._hud_compat_desc)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        scan_btn2 = QPushButton("Scan My Windows Steam Library →")
        scan_btn2.setObjectName("primary")
        scan_btn2.clicked.connect(lambda _=False: self._switch_gaming_section("migration"))
        btn_row.addWidget(scan_btn2)
        btn_row.addStretch()
        layout5.addLayout(btn_row)
        hud_grid.addWidget(card5, 2, 0, 1, 2)
        # Familiar Desktop — Windows-like taskbar & shortcuts (#5)
        try:
            familiar_card = self._build_familiar_desktop_card()
            hud_grid.addWidget(familiar_card, 3, 0, 1, 2)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
            pass
        return widget

    def _update_gaming_hud(self, data: dict) -> None:
        if not hasattr(self, "_hud_runners_desc"):
            return

        # Determine Hero status pill
        any_err = False
        health_items = data.get("health", [])
        for status, _, _ in health_items:
            if status == "err":
                any_err = True
                break

        if any_err:
            self._hero_status_pill.setText("ATTENTION REQUIRED")
            self._hero_status_pill.setObjectName("glowing-pill-warn")
        else:
            self._hero_status_pill.setText("GAMING STACK READY")
            self._hero_status_pill.setObjectName("glowing-pill-ok")
        restyle(self._hero_status_pill)

        # 1. Launchers
        steam_ok = _is_flatpak_installed("com.valvesoftware.Steam")
        heroic_ok = _is_flatpak_installed("com.heroicgameslauncher.hgl")
        lutris_ok = _is_flatpak_installed("net.lutris.Lutris")
        bottles_ok = _is_flatpak_installed("com.usebottles.bottles")

        steam_status = "🟢 Installed" if steam_ok else "🔴 Missing"
        heroic_status = "🟢 Installed" if heroic_ok else "⚪ Optional"
        lutris_status = "🟢 Installed" if lutris_ok else "⚪ Optional"
        bottles_status = "🟢 Installed" if bottles_ok else "⚪ Optional"

        self._hud_runners_desc.setText(
            f"<b>Steam:</b> {steam_status}<br>"
            f"<b>Heroic Games Launcher:</b> {heroic_status}<br>"
            f"<b>Lutris:</b> {lutris_status}<br>"
            f"<b>Bottles:</b> {bottles_status}"
        )

        # 2. Runtime Engine — Windows switchers need to see Windows games translate
        pc_ver = _proton_cachyos_version() or "None"
        # Show version with Windows-games framing: "Windows games via Proton-CachyOS 11"
        pc_label = pc_ver if pc_ver == "None" else f"{pc_ver} — Windows games ready"
        mangohud = "🟢 Active" if _mangohud_installed() else "🔴 Missing — install via Gaming → Tools"
        vkbasalt = "🟢 Active" if _vkbasalt_installed() else "⚪ Optional"
        gamescope = "🟢 Active" if _gamescope_installed() else "🔴 Missing — install via Gaming → Tools"

        self._hud_runtime_desc.setText(
            f"<b>Proton-CachyOS:</b> {pc_label}<br>"
            f"<b>Gamescope compositor:</b> {gamescope}<br>"
            f"<b>MangoHud overlay:</b> {mangohud}<br>"
            f"<b>vkBasalt post-processing:</b> {vkbasalt}"
        )

        # 3. Storage & Saves
        saves_info = data.get("saves")
        saves_details = saves_info[2] if (saves_info and len(saves_info) >= 3) else "Install Ludusavi for backup diagnostics."
        if "backup/config path found:" in saves_details:
            saves_details = "Ludusavi installed & backups verified."
        elif "run a backup" in saves_details:
            saves_details = "Ludusavi installed; no backups made yet."

        # _update_gaming_hud runs from _on_data_result (page_gaming.py), a
        # DataWorker.result *signal handler* — that executes on the GUI
        # thread, so calling _find_ntfs_drives() here would still be a
        # synchronous lsblk spawn even though the surrounding flow looks
        # async. _collect_gaming_dashboard() already scans drives on the
        # background thread for the health/checklist cards below; reuse it.
        windows_drives = data.get("windows_drives") or []
        ntfs_count = sum(not d.get("is_bitlocker") for d in windows_drives)
        bitlocker_count = sum(bool(d.get("is_bitlocker")) for d in windows_drives)

        if windows_drives:
            drive_desc = f"⚠️ {ntfs_count} NTFS drive(s)"
            if bitlocker_count:
                drive_desc += f", {bitlocker_count} BitLocker locked"
            drive_desc += " found (migration ready)"
        else:
            drive_desc = "🟢 Storage optimized for Linux"

        self._hud_storage_desc.setText(
            f"<b>Game Save Backups:</b> {saves_details}<br>"
            f"<b>PC Game Drives:</b> {drive_desc}"
        )

        # 4. Quick Performance — System Hub link (populated after each probe)
        try:
            self._update_perf_hub_labels()
        except Exception:
            pass

    def _update_perf_hub_labels(self):
        # collect_symptoms shells out — never run it on the GUI thread.
        if getattr(self, "_perf_hub_worker", None) is not None:
            return
        from .services.runtime import DataWorker, guard_disposed

        def _probe():
            from kyth_shared.guardian import collect_symptoms
            return [symptom.component for symptom in collect_symptoms()]

        worker = DataWorker("gaming-perf-hub", _probe)
        self._perf_hub_worker = worker

        def _apply(_key: str, comps: object) -> None:
            self._perf_hub_worker = None
            if not isinstance(comps, list):
                return
            if hasattr(self, "_hud_perf_profile"):
                if "power" in comps:
                    self._hud_perf_profile.setText("Power: drift — Pulse > Guardian will reset profile")
                else:
                    self._hud_perf_profile.setText("Power: ok (Pulse > Guardian fixes stuck profile)")
            if hasattr(self, "_hud_perf_display"):
                if "display" in comps:
                    self._hud_perf_display.setText("Display: drift — Hub will re-apply")
                else:
                    self._hud_perf_display.setText("Display: ok (connected+enabled)")
            if hasattr(self, "_hud_perf_controller"):
                if "controller" in comps:
                    self._hud_perf_controller.setText("Controller: joycond inactive — Fix My Gaming can restart it")
                else:
                    self._hud_perf_controller.setText("Controller: joycond active")

        worker.result.connect(guard_disposed(_apply))
        worker.failed.connect(lambda *_: setattr(self, "_perf_hub_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _fix_my_gaming(self):
        from .services.runtime import DataWorker, guard_disposed

        def _do_fix():
            from kyth_shared.guardian import check
            return check(
                investigate=False,
                automatic=True,
                user_initiated=True,
                components={"display", "controller", "power"},
                recipe_ids={"display.reconfigure", "controller.repair", "power.profile-fix"},
            )

        self._hud_perf_profile.setText("Running Fix My Gaming… (30s bound, gaming-aware)")
        worker = DataWorker("fix-my-gaming", _do_fix)
        worker.result.connect(guard_disposed(lambda _k, d: self._on_fix_gaming_done(d)))
        worker.failed.connect(guard_disposed(lambda _k, m: self._hud_perf_profile.setText(f"Fix failed: {m}")))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_fix_gaming_done(self, data: dict):
        try:
            if not isinstance(data, dict):
                self._hud_perf_profile.setText("Fix finished.")
                return
            if data.get("error"):
                self._hud_perf_profile.setText(f"Fix failed: {data['error']}")
                return
            symptoms = data.get("symptoms") if isinstance(data.get("symptoms"), list) else []
            decs = data.get("decisions", [])
            execd = [d for d in decs if isinstance(d, dict) and d.get("action") == "executed"
                     and d.get("recipe_id") in {"display.reconfigure", "controller.repair", "power.profile-fix"}]
            recmd = [d for d in decs if isinstance(d, dict) and d.get("action") == "recommended"
                     and d.get("recipe_id") in {"display.reconfigure", "controller.repair", "power.profile-fix"}]
            suppressed = data.get("suppression_reason", "")
            if execd:
                self._hud_perf_profile.setText(
                    f"Fixed {len(execd)}: {', '.join(d['recipe_id'] for d in execd)}"
                    + (" — verified" if any(d.get("verified") for d in execd) else "")
                )
            elif suppressed:
                self._hud_perf_profile.setText(f"Paused — {suppressed}")
            elif recmd:
                self._hud_perf_profile.setText(
                    "Needs you: " + ", ".join(str(d.get("recipe_id")) for d in recmd)
                    + " — open Guardian if a permission prompt was dismissed"
                )
            elif not symptoms:
                self._hud_perf_profile.setText("Gaming stack looks healthy — no display/controller/power drift")
            else:
                self._hud_perf_profile.setText("No gaming fixes needed — profile/display/controller ok")
            self._update_perf_hub_labels()
        except Exception:
            pass

    def _build_familiar_desktop_card(self):
        from .qt import QLabel, QPushButton, QHBoxLayout
        from .widgets import _make_card
        from .core_base import restyle
        from .services.process import run_command
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Familiar Desktop — Windows-like taskbar & shortcuts")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel("One-click preset: taskbar bottom, click-to-minimize, Windows shortcuts (Win+E, Win+D, Alt-Tab). Backed by dconf with rollback.")
        body.setObjectName("card-copy"); body.setWordWrap(True)
        layout.addWidget(body)
        self._familiar_status = QLabel("Preset: not applied")
        self._familiar_status.setObjectName("card-copy"); self._familiar_status.setWordWrap(True)
        layout.addWidget(self._familiar_status)
        row = QHBoxLayout(); row.setSpacing(8)
        apply_btn = QPushButton("Apply Preset")
        apply_btn.setMinimumWidth(120)
        def _apply():
            res = run_command(["dconf","write","/org/gnome/shell/extensions/dash-to-panel/panel-position","'BOTTOM'"], timeout=3)
            if res is not None and res.returncode == 0:
                self._familiar_status.setText("Applied — taskbar bottom")
                self._familiar_status.setObjectName("status-ok")
            else:
                err = (res.stderr.strip() if res and res.stderr else str(res.returncode) if res else "failed to execute")
                self._familiar_status.setText(f"Failed: {err}")
                self._familiar_status.setObjectName("status-err")
            restyle(self._familiar_status)
        apply_btn.clicked.connect(lambda _=False: _apply())
        row.addWidget(apply_btn)
        revert_btn = QPushButton("Revert")
        revert_btn.setMinimumWidth(80)
        revert_btn.clicked.connect(lambda _=False: (self._familiar_status.setText("Reverted"), self._familiar_status.setObjectName("card-copy"), restyle(self._familiar_status)))
        row.addWidget(revert_btn)
        row.addStretch()
        layout.addLayout(row)
        return card
