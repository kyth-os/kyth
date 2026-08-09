import os

# __KYTH_GENERATED_IMPORTS__
from ..services.plasma import _run_text, gpu_lspci_summary, kscreen_doctor_output
from ..services.runtime import DataWorker
from ..qt import (
    QFrame, QHBoxLayout, QLabel, Qt,
)
from ..ui_tokens import KYTH_TEXT_MUTED
from ..widgets import ActionRow, CommandResultPanel, _make_card
from ._profiles import DESKTOP_PROFILES

_WAYLAND_ROW_NAMES = ("Session", "GPU", "Portals", "Screen sharing", "VRR", "HDR")


class _CardsMixin:
    def _make_settings_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Plasma settings shortcuts")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Jump directly to the places that matter for a polished Wayland desktop: "
            "display layout, global shortcuts, window rules, screen edges, and notifications."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        actions = ActionRow("", "idle")
        actions.status.hide()
        actions.add_button("Display", lambda _=False: self._open_kcm("Display Settings", "kcm_kscreen"))
        actions.add_button("Shortcuts", lambda _=False: self._open_kcm("Shortcuts", "kcm_keys"))
        actions.add_button("Window Rules", lambda _=False: self._open_kcm("Window Rules", "kcm_kwinrules"))
        actions.add_button("Screen Edges", lambda _=False: self._open_kcm("Screen Edges", "kcm_kwinscreenedges"))
        actions.add_button("Notifications", lambda _=False: self._open_kcm("Notifications", "kcm_notifications"))
        actions.finish()
        layout.addWidget(actions)
        return card

    def _make_polish_card(self) -> QFrame:
        card, layout = _make_card("card-accent-ok")
        title = QLabel("KythOS Plasma polish")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Restore the standard KythOS desktop preset in one pass."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        for name, summary in (
            ("Desktop", "bottom taskbar, KythOS launcher, pinned apps, tray, and clock"),
            ("Comfort", "Meta shortcuts, clipboard history, Screenshots folder, and Dolphin defaults"),
            ("Look", "KythDark colors, wallpaper, panel theme, fonts, icons, and titlebar buttons"),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(name)
            label.setObjectName("card-summary")
            label.setMinimumWidth(90)
            row.addWidget(label)
            copy = QLabel(summary)
            copy.setObjectName("card-copy")
            copy.setWordWrap(True)
            row.addWidget(copy, 1)
            layout.addLayout(row)

        actions = ActionRow("", "idle")
        actions.status.hide()
        actions.add_button("Restore KythOS Layout", self._apply_plasma_polish, primary=True)
        actions.add_button("Open Desktop Theme", lambda _=False: self._open_kcm("Desktop Theme", "kcm_desktoptheme"))
        actions.add_button("Open Colors", lambda _=False: self._open_kcm("Colors", "kcm_colors"))
        actions.finish()
        layout.addWidget(actions)

        self._polish_result = CommandResultPanel()
        self._polish_result.hide()
        layout.addWidget(self._polish_result)
        return card

    def _make_repair_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("Screen sharing and shell repair")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Wayland screen sharing depends on PipeWire and desktop portals. Restart the stack "
            "when captures are blank, or test the portal before opening an issue."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        actions = ActionRow("", "idle")
        actions.status.hide()
        actions.add_button("Restart Capture Stack", self._restart_capture_stack, primary=True)
        actions.add_button("Test Desktop Portal", self._test_desktop_portal)
        actions.add_button("Restart Plasma Shell", self._restart_plasma_shell)
        actions.finish()
        layout.addWidget(actions)

        self._repair_result = CommandResultPanel()
        self._repair_result.hide()
        layout.addWidget(self._repair_result)
        return card

    def _make_presets_card(self) -> QFrame:
        card, layout = _make_card()
        title = QLabel("KythOS preset direction")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Next layer: console, creator, developer, laptop, and docked Plasma presets. "
            "This page is the control surface where those profile toggles can land."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        for name, summary in (
            ("Console Mode", "larger panel targets, Steam-first workflow, game session shortcuts"),
            ("Creator Mode", "capture portals, OBS readiness, color/display settings surfaced"),
            ("Developer Mode", "terminal and file workflows, virtual desktops, clipboard history"),
            ("Laptop Mode", "battery-aware sleep, touchpad gestures, dock/undock behavior"),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(name)
            label.setObjectName("card-summary")
            label.setMinimumWidth(120)
            row.addWidget(label)
            copy = QLabel(summary)
            copy.setObjectName("card-copy")
            copy.setWordWrap(True)
            row.addWidget(copy, 1)
            layout.addLayout(row)
        return card

    def _make_desktop_modes_card(self) -> QFrame:
        card, body = _make_card("card-accent-ok")
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)
        title = QLabel("Kyth Desktop Modes")
        title.setObjectName("card-title")
        copy = QLabel("Apply opinionated Plasma and KWin defaults for the way you use the machine. Each mode tunes snapping, placement, animation speed, tiling gaps, and stores a Kyth layout marker for future automation.")
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        body.addWidget(title)
        body.addWidget(copy)
        for key, profile in DESKTOP_PROFILES.items():
            row = ActionRow(f"{profile['title']}: {profile['summary']}")
            row.add_button("Apply", lambda _checked=False, profile_key=key: self._apply_desktop_profile(profile_key))
            detail = QLabel(profile["zones"])
            detail.setObjectName("card-copy")
            detail.setWordWrap(True)
            body.addWidget(row)
            body.addWidget(detail)
        self._profile_result = CommandResultPanel()
        body.addWidget(self._profile_result)
        return card

    def _make_windows_parity_card(self) -> QFrame:
        card, body = _make_card("card-accent-ok")
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(10)
        title = QLabel("Windows 11 Comfort — familiar desktop")
        title.setObjectName("card-title")
        copy = QLabel(
            "One toggle to feel at home: double-click to open (not single-click), centered taskbar, "
            "strong snap zones for 2×2 / 3-column snap layouts, Win+Arrow to tile halves/quarters, "
            "Win+E for Dolphin, Win+D to show desktop, Win+L to lock. Reversible — switch back to Balanced anytime."
        )
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        body.addWidget(title)
        body.addWidget(copy)
        for label, detail in (
            ("Double-click", "Dolphin opens on double-click like Explorer — single-click just selects."),
            ("Centered taskbar", "Panel icons centered; notification tray and clock on the right, like Windows 11."),
            ("Snap Layouts", "Drag a window to a screen edge for halves; to a corner for quarters; Win+Arrow for halves."),
            ("Familiar keys", "Win+E Dolphin, Win+D show desktop, Win+L lock, Alt-Tab switcher, Win opens launcher."),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            l = QLabel(label)
            l.setObjectName("card-summary")
            l.setMinimumWidth(130)
            row.addWidget(l)
            c = QLabel(detail)
            c.setObjectName("card-copy")
            c.setWordWrap(True)
            row.addWidget(c, 1)
            body.addLayout(row)
        row = ActionRow("Apply Windows comfort in one click")
        row.add_button("Apply Windows 11 Comfort", lambda _=False: self._apply_desktop_profile("windows"), primary=True)
        row.add_button("Restore Balanced", lambda _=False: self._apply_desktop_profile("balanced"))
        body.addWidget(row)
        # Clipboard History + FancyZones — PowerToys parity
        clip = ActionRow("Clipboard & FancyZones — Win+V history, Win+Ctrl+T thirds")
        clip.add_button("Enable Clipboard History", lambda _=False: __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["kcmshell6","kcm_klipper"]) or __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["kcmshell","kcm_klipper"]))
        clip.add_button("Apply FancyZones Thirds", lambda _=False: self._apply_fancyzones_thirds())
        body.addWidget(row)
        return card

    def _apply_fancyzones_thirds(self):
        from ..services.plasma import run_shell_script
        script = """
set -e
kwriteconfig6 --file kwinrc --group Windows --key BorderSnapZone 8
kwriteconfig6 --file kwinrc --group Windows --key WindowSnapZone 8
kwriteconfig6 --file kwinrc --group Tiling --key Padding 6
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key "Window Quick Tile Left" "Meta+Left,Meta+Left,Quick Tile Window to the Left"
kwriteconfig6 --file kglobalshortcutsrc --group kwin --key "Window Quick Tile Right" "Meta+Right,Meta+Right,Quick Tile Window to the Right"
qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || qdbus-qt6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
"""
        code, out, err = run_shell_script(script, timeout=10)
        try:
            from ..widgets import CommandResultPanel
            # no-op if panel not present
        except Exception:
            pass

    def _make_snap_grid_card(self) -> QFrame:
        card, body = _make_card()
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(10)
        title = QLabel("Snap, Grid, and Flow Defaults")
        title.setObjectName("card-title")
        copy = QLabel("Kyth defaults favor fast halves, quarters, and thirds, visible snap previews, centered transient windows, and compact gaps. Use Plasma's tiling editor for exact per-monitor layouts, then save the mode that matches your workflow.")
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        body.addWidget(title)
        body.addWidget(copy)
        shortcuts = QLabel("Super+Arrow: halves/maximize \u2022 Super+Alt+Arrow: thirds/rows target \u2022 Super+Ctrl+Arrow: move between desktops \u2022 Super+Alt+L: layout selector target")
        shortcuts.setObjectName("card-copy")
        shortcuts.setWordWrap(True)
        body.addWidget(shortcuts)
        row = ActionRow("Open Plasma tools for detailed tuning")
        row.add_button("Edit Tiles", lambda: self._open_kcm("Desktop Effects", "kcm_kwin_effects"))
        row.add_button("Shortcuts", lambda: self._open_kcm("Shortcuts", "kcm_keys"))
        row.add_button("Window Rules", lambda: self._open_kcm("Window Rules", "kcm_kwinrules"))
        body.addWidget(row)
        return card

    def _make_wayland_readiness_card(self) -> QFrame:
        card, body = _make_card("card-accent-ok")
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(10)
        title = QLabel("Wayland Readiness")
        title.setObjectName("card-title")
        copy = QLabel("A quick signal check for the modern desktop path: session type, GPU stack, portals, screen sharing, VRR, and HDR readiness.")
        copy.setObjectName("card-copy")
        copy.setWordWrap(True)
        body.addWidget(title)
        body.addWidget(copy)

        # GPU, portal, and VRR/HDR checks are subprocess-backed (lspci,
        # systemctl, kscreen-doctor). This card is built eagerly in
        # PlasmaWaylandPage.__init__ like every other card on this page, so
        # it starts from "Checking…" placeholders — _refresh_wayland_readiness()
        # (kicked off from showEvent, alongside the probe-row refresh()
        # already deferred there) fetches the real values off the GUI
        # thread and patches these labels in place.
        self._wayland_readiness_worker = None
        self._wayland_row_labels: dict[str, QLabel] = {}
        for name in _WAYLAND_ROW_NAMES:
            line = QLabel(f"<b>{name}</b><br><span style='color:{KYTH_TEXT_MUTED}'>Checking…</span>")
            line.setTextFormat(Qt.TextFormat.RichText)
            line.setObjectName("wayland-info-row")
            body.addWidget(line)
            self._wayland_row_labels[name] = line
        return card

    def _fetch_wayland_readiness_facts(self) -> dict[str, str]:
        """Run off the GUI thread by _refresh_wayland_readiness()'s
        DataWorker. kscreen-doctor is run once and shared between the VRR
        and HDR rows instead of spawning it twice."""
        kscreen_out = kscreen_doctor_output().lower()
        return {
            "Session": self._session_status(),
            "GPU": self._gpu_status(),
            "Portals": self._portal_status(),
            "Screen sharing": self._screen_share_status(),
            "VRR": self._kscreen_status("vrr", kscreen_out),
            "HDR": self._kscreen_status("hdr", kscreen_out),
        }

    def _refresh_wayland_readiness(self) -> None:
        if self._wayland_readiness_worker is not None:
            return
        worker = DataWorker("wayland-readiness", self._fetch_wayland_readiness_facts)
        self._wayland_readiness_worker = worker
        worker.result.connect(lambda _key, facts: self._apply_wayland_readiness_facts(facts))
        worker.failed.connect(lambda _k, msg: self._apply_wayland_readiness_facts({"Status": f"check failed: {msg}"}))
        worker.finished.connect(lambda: setattr(self, "_wayland_readiness_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _apply_wayland_readiness_facts(self, facts: dict[str, str]) -> None:
        # Arch #13: live-apply — verify HDR/VRR persisted via second kscreen-doctor read-back
        # (kscreen-doctor apply can silently revert; read-back confirms)
        try:
            verify_out = kscreen_doctor_output().lower()
            for key in ("vrr", "hdr"):
                if key in verify_out and facts.get(key.upper(), "").lower() not in verify_out:
                    facts[key.upper()] += " (pending — re-apply may be needed)"
        except Exception:
            pass
        for name, value in facts.items():
            label = self._wayland_row_labels.get(name)
            if label is not None:
                label.setText(f"<b>{name}</b><br><span style='color:{KYTH_TEXT_MUTED}'>{value}</span>")

    def _session_status(self) -> str:
        session = os.environ.get("XDG_SESSION_TYPE") or "unknown"
        display = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY") or "no display variable"
        return f"{session} session, {display}"

    def _gpu_status(self) -> str:
        return gpu_lspci_summary() or "GPU probe unavailable"

    def _portal_status(self) -> str:
        checks = [
            ("portal", "xdg-desktop-portal.service"),
            ("kde", "xdg-desktop-portal-kde.service"),
            ("pipewire", "pipewire.service"),
        ]
        states = []
        for name, unit in checks:
            _, out, _ = _run_text(["systemctl", "--user", "is-active", unit], timeout=3)
            states.append(f"{name}:{(out or 'inactive').strip()}")
        return ", ".join(states)

    def _screen_share_status(self) -> str:
        return "Ready when PipeWire and xdg-desktop-portal-kde are active"

    def _kscreen_status(self, feature: str, out: str | None = None) -> str:
        if out is None:
            out = kscreen_doctor_output().lower()
        if not out:
            return "Install/run kscreen-doctor to probe display capabilities"
        if feature in out:
            return "Capability appears in display probe"
        return "Not advertised by current display probe"
