"""Wizard step builder — _MachineStepMixin ("Your Machine").

Replaces the old wizard's separate "Update Your System" and "Hardware Check"
steps, which each embedded a full live Hub page (UpdatePage / HardwarePage).
This step is wizard-native: a stat bar, an update-status card, and the
preflight warning card, all built directly from services/ — with a handoff
button to System Hub for anyone who wants the full page.
"""
from __future__ import annotations

from ..core_base import IS_LIVE
from ..services.process import command_stdout
from ..services.bootc import current_branch, has_rollback_deployment, has_staged_update
from ..qt import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from ..services.gaming import _COMPAT_GAMES, _find_ntfs_drives, _proton_cachyos_version
from ..services.hardware import _detect_nvidia
from ..widgets import _make_card


class _MachineStepMixin:
    def _blocked_game_summary(self, limit: int = 5) -> str:
        blocked = [game for game in _COMPAT_GAMES if game.status == "blocked"]
        if not blocked:
            return ""
        names = [game.name for game in blocked[:limit]]
        summary = ", ".join(names)
        if len(blocked) > limit:
            summary += f", and {len(blocked) - limit} more"
        return summary

    def _make_preflight_card(self) -> QFrame | None:
        rows: list[str] = []
        blocked_summary = self._blocked_game_summary()
        if blocked_summary:
            rows.append(
                "Known hard blockers: "
                f"{blocked_summary}. These are publisher anti-cheat decisions, not Proton settings."
            )
        if not IS_LIVE and _find_ntfs_drives():
            rows.append(
                "PC game drive detected. Copy Steam libraries to a Linux-formatted disk before using Proton."
            )
        if _detect_nvidia():
            rows.append(
                "NVIDIA GPU detected. Open Hardware to verify the proprietary module and reboot state."
            )
        if has_rollback_deployment():
            rows.append(
                "Rollback is available. If an update makes things worse, return to the previous image first."
            )
        if not rows:
            return None

        card, layout = _make_card("wiz-card-warn")
        title = QLabel("Worth knowing before you dive in")
        title.setObjectName("wiz-card-title")
        layout.addWidget(title)
        for text in rows:
            row = QLabel("· " + text)
            row.setObjectName("wiz-card-copy")
            row.setWordWrap(True)
            layout.addWidget(row)
        return card

    def _make_update_card(self) -> QFrame:
        staged = has_staged_update()
        branch = current_branch() or ""
        if branch.startswith("testing"):
            channel = "Testing"
        elif branch.startswith("latest"):
            channel = "Stable"
        else:
            channel = branch or "unknown"

        card, layout = _make_card("wiz-card-warn" if staged else "wiz-card-ok")
        title = QLabel("System update")
        title.setObjectName("wiz-card-title")
        layout.addWidget(title)
        if staged:
            copy_text = (
                f"On the {channel} channel. An update is already staged and will apply "
                "on your next restart."
            )
        else:
            copy_text = f"On the {channel} channel. Check for updates any time from System Hub."
        copy = QLabel(copy_text)
        copy.setObjectName("wiz-card-copy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        open_btn = QPushButton("Open Update Center")
        open_btn.clicked.connect(lambda: self._open_hub_at("Update"))
        btn_row.addWidget(open_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return card

    def _make_stat_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("wiz-body")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        kernel = command_stdout(["uname", "-r"]) or "unknown"
        pc_ver = _proton_cachyos_version() or "included"
        scx_sched = "Fedora"
        try:
            with open("/etc/scx/scx_loader.conf", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("SCX_SCHEDULER="):
                        scx_sched = line.split("=", 1)[1].strip().replace("scx_", "").upper()
                        break
        except OSError:
            pass

        for i, (label, value) in enumerate((
            ("Kernel", kernel),
            ("Proton-CachyOS", pc_ver),
            ("Scheduler", scx_sched),
        )):
            if i > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setObjectName("wiz-stat-sep")
                sep.setFixedWidth(1)
                row.addSpacing(24)
                row.addWidget(sep)
                row.addSpacing(24)
            tile = QFrame()
            tile.setObjectName("wiz-stat")
            col = QVBoxLayout(tile)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(4)
            lbl = QLabel(label.upper())
            lbl.setObjectName("wiz-stat-label")
            val = QLabel(value)
            val.setObjectName("wiz-stat-value")
            col.addWidget(lbl)
            col.addWidget(val)
            row.addWidget(tile)
        row.addStretch()
        return bar

    def _make_machine_step(self) -> QWidget:
        page = QWidget()
        page.setObjectName("wiz-body")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(52, 40, 52, 30)
        layout.setSpacing(16)

        pill = QLabel("YOUR MACHINE")
        pill.setObjectName("wiz-pill")
        layout.addWidget(pill)

        heading = QLabel("Here's what you're running.")
        heading.setObjectName("wiz-heading")
        layout.addWidget(heading)

        sub = QLabel(
            "A quick look at your kernel, Proton stack, and update status — plus "
            "anything worth knowing before you get going."
        )
        sub.setObjectName("wiz-subheading")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        layout.addSpacing(6)
        layout.addWidget(self._make_stat_bar())
        layout.addWidget(self._make_update_card())

        preflight = self._make_preflight_card()
        if preflight is not None:
            layout.addWidget(preflight)

        layout.addStretch()
        return page
