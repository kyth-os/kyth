"""Wizard step builders — _GamingStepMixin.

Gaming-profile-only step. The launcher grid at the bottom embeds the live
GamingPage's "setup" section (wizard_mode=True) rather than being
reimplemented here — it's a tested install flow (Heroic/Lutris/ProtonPlus
workers), not the kind of full-page-as-a-step problem the Update/Hardware
steps were; everything above it is wizard-native.
"""
from __future__ import annotations

from ..core_base import IS_LIVE
from ..services.gaming import _COMPAT_GAMES
from ..qt import QDesktopServices, QFrame, QHBoxLayout, QLabel, QPushButton, QUrl, QVBoxLayout, QWidget
from ..widgets import _divider, _make_card, _make_flow_step


class _GamingStepMixin:
    def _apply_gaming_windows_drives(self, drives: list[dict]) -> None:
        """Called by _MachineStepMixin._on_machine_facts_ready() once the
        shared background NTFS scan resolves (see steps_machine.py)."""
        self._pending_gaming_drives = drives
        if getattr(self, "_gaming_drive_slot_layout", None) is None:
            return
        if self._gaming_drive_card is not None:
            self._gaming_drive_slot_layout.removeWidget(self._gaming_drive_card)
            self._gaming_drive_card.deleteLater()
            self._gaming_drive_card = None
        if IS_LIVE:
            return
        filtered = [d for d in drives if not d.get("is_bitlocker")]
        if filtered:
            card = self._make_windows_game_drive_card(filtered)
            self._gaming_drive_slot_layout.addWidget(card)
            self._gaming_drive_card = card

    def _make_windows_game_drive_card(self, drives: list[dict]) -> QFrame:
        card, layout = _make_card("wiz-card-warn")
        title = QLabel("PC game drive found")
        title.setObjectName("wiz-card-title")
        layout.addWidget(title)
        names = []
        for drive in drives[:3]:
            label = drive.get("label") or drive.get("name") or drive.get("dev") or "PC drive"
            size = drive.get("size") or ""
            names.append(f"{label} {size}".strip())
        listed = ", ".join(names)
        if len(drives) > 3:
            listed += f", and {len(drives) - 3} more"
        body = QLabel(
            f"Detected: {listed}. Do not point Steam at the NTFS library and start playing. "
            "Copy the library into Steam on a Linux-formatted disk first, then let Proton "
            "build clean prefixes there. The migration tool below mounts the other system's drive read-only."
        )
        body.setObjectName("wiz-card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        return card


    def _make_gaming_step(self) -> QWidget:
        container = QWidget()
        container.setObjectName("wiz-body")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        intro = QWidget()
        intro.setObjectName("wiz-body")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(52, 40, 52, 20)
        intro_layout.setSpacing(8)
        pill_lbl = QLabel("GAMING SETUP")
        pill_lbl.setObjectName("wiz-pill")
        intro_layout.addWidget(pill_lbl)
        title_lbl = QLabel("Install your games.")
        title_lbl.setObjectName("wiz-heading")
        subtitle_lbl = QLabel(
            "Install launchers for Steam, Epic, GOG, and Battle.net below. "
            "Then follow the Proton steps to unlock your full game library."
        )
        subtitle_lbl.setObjectName("wiz-subheading")
        subtitle_lbl.setWordWrap(True)
        intro_layout.addWidget(title_lbl)
        intro_layout.addWidget(subtitle_lbl)
        outer.addWidget(intro)

        # ── Proton setup card ─────────────────────────────────────────────────
        proton_section = QWidget()
        proton_section.setObjectName("wiz-body")
        ps_layout = QVBoxLayout(proton_section)
        ps_layout.setContentsMargins(52, 6, 52, 0)
        ps_layout.setSpacing(10)

        # Populated by _apply_gaming_windows_drives() once
        # _MachineStepMixin's background NTFS scan resolves — see
        # steps_machine.py's module docstring. Not fetched here: this step
        # is built on first visit (see WizardWindow._ensure_step), so it must
        # not run lsblk itself.
        self._gaming_drive_slot = QWidget()
        self._gaming_drive_slot.setObjectName("wiz-body")
        self._gaming_drive_slot_layout = QVBoxLayout(self._gaming_drive_slot)
        self._gaming_drive_slot_layout.setContentsMargins(0, 0, 0, 0)
        self._gaming_drive_card = None
        ps_layout.addWidget(self._gaming_drive_slot)

        proton_head = QLabel("Enable Proton — play your entire game library")
        proton_head.setObjectName("wiz-section-heading")
        ps_layout.addWidget(proton_head)

        proton_card, pc_layout = _make_card("wiz-card-ok")
        intro_copy = QLabel("Do this once after Steam finishes installing:")
        intro_copy.setObjectName("wiz-card-copy")
        pc_layout.addWidget(intro_copy)

        for index, (step_title, copy) in enumerate((
            ("Open Steam", ""),
            ("Go to Settings → Compatibility", ""),
            ("Turn on \"Enable Steam Play for all other titles\"", ""),
            ("Select Proton-CachyOS", "From the version dropdown."),
            ("Restart Steam", "Your full game library now appears."),
        ), 1):
            pc_layout.addWidget(_make_flow_step(index, step_title, copy))

        tip = QLabel(
            "Proton-CachyOS is already installed on this system and kept up to date automatically."
        )
        tip.setObjectName("wiz-card-copy-ok")
        tip.setWordWrap(True)
        pc_layout.addSpacing(6)
        pc_layout.addWidget(tip)
        ps_layout.addWidget(proton_card)
        outer.addWidget(proton_section)

        # ── Compatibility teaser ──────────────────────────────────────────────
        compat_section = QWidget()
        compat_section.setObjectName("wiz-body")
        cs_layout = QHBoxLayout(compat_section)
        cs_layout.setContentsMargins(52, 14, 52, 0)

        compat_card, cc_layout = _make_card("wiz-card")
        cc_layout.setSpacing(6)
        compat_lbl = QLabel("Check your must-play games now — before you commit an evening to one")
        compat_lbl.setObjectName("wiz-card-copy-strong")
        cc_layout.addWidget(compat_lbl)
        # Front-load the hard wall: kernel-level anti-cheat is the #1 reason
        # other system switchers give up, and no Proton setting will ever fix it.
        # Showing the blocked titles here beats discovering them the hard way.
        blocked = [game for game in _COMPAT_GAMES if game.status == "blocked"]
        if blocked:
            blocked_names = "  ·  ".join(
                f"{game.name} ({game.anticheat})" for game in blocked
            )
            blocked_lbl = QLabel(
                f"Will NOT run — blocked by kernel-level anti-cheat on every Linux system: {blocked_names}."
            )
            blocked_lbl.setObjectName("wiz-card-copy-err")
            blocked_lbl.setWordWrap(True)
            cc_layout.addWidget(blocked_lbl)
        compat_sub = QLabel(
            "The rest of the tracked list is marked native, works through Proton, or needs "
            "specific tweaks. The Compatibility page in the System Hub keeps the full list "
            "current, and ProtonDB has reports for nearly every Steam title."
        )
        compat_sub.setObjectName("wiz-card-copy")
        compat_sub.setWordWrap(True)
        compat_btn = QPushButton("Browse ProtonDB →")
        compat_btn.setObjectName("primary")
        compat_btn.setFixedWidth(200)
        compat_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.protondb.com"))
        )
        cc_layout.addWidget(compat_sub)
        cc_layout.addWidget(compat_btn)
        cs_layout.addWidget(compat_card, 1)

        outer.addWidget(compat_section)
        outer.addWidget(_divider())

        # ── Launcher grid (live GamingPage "setup" section) ───────────────────
        outer.addWidget(self._ensure_gaming_page(), 1)
        pending = getattr(self, "_pending_gaming_drives", None)
        if pending:
            self._apply_gaming_windows_drives(pending)
        return container
