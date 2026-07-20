"""Windows Migration page — page shell + WindowsMigrationPage, assembled from domain mixins."""

from __future__ import annotations

import os
from ..services.runtime import (
    DataWorker,
)
from ..services.software import (
    Worker,
)
from ..services.launch import popen
from ..services.windows_migration import (
    UserFilesCopyWorker,
    WindowsLibraryWorker,
)
from ..qt import (
    QCheckBox, QDesktopServices, QFrame, QHBoxLayout, QLabel, QPushButton, QUrl,
)
from ..widgets import (
    Page, _make_card, _make_flow_step,
)

from .shortcuts_phone import _ShortcutsPhoneMixin
from .localsend_misc import _LocalSendMiscMixin
from .files_copy import _FilesCopyMixin
from .bookmarks_extras import _BookmarksExtrasMixin
from .transfer_extras import _TransferExtrasMixin
from .drives import _DrivesMixin


# ── Page: Move Files ──────────────────────────────────────────────────
class WindowsMigrationPage(
    Page,
    _ShortcutsPhoneMixin,
    _LocalSendMiscMixin,
    _FilesCopyMixin,
    _BookmarksExtrasMixin,
    _TransferExtrasMixin,
    _DrivesMixin,
):

    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _: None)
        self._worker: WindowsLibraryWorker | None = None
        self._files_profiles: list[tuple[dict, dict]] = []
        self._files_checks: list[tuple[QCheckBox, str, str, str]] = []
        self._files_sizes_key = ""
        self._folder_sizes_cache: dict[str, dict] = {}
        self._files_sizes_workers: dict[str, DataWorker] = {}
        self._files_copy_worker: UserFilesCopyWorker | None = None
        self._bm_worker: DataWorker | None = None
        self._bm_sources: list[dict] = []
        self._bm_dest = ""
        self._hw_worker: DataWorker | None = None
        self._extras: dict = {}
        self._extras_worker: DataWorker | None = None
        self._fonts_copy_worker: DataWorker | None = None
        self._saves_copy_worker: DataWorker | None = None
        self._wsl_worker: Worker | None = None
        self._phone_worker: DataWorker | None = None
        self._phone_action_worker: DataWorker | None = None
        self._dynamic_lock_worker: DataWorker | None = None

        self._page_header(
            "Apps",
            "Move Files",
            "Bring your files, games, and familiar habits over without touching the original install.",
        )

        self._build_intro_card()
        self._build_flow_card()
        self._build_checklist_card()
        self._build_hw_card()
        self._build_clock_card()
        self._build_shortcuts_card()
        self._build_powertoys_card()
        self._build_shell_card()
        self._build_onedrive_card()
        self._build_nearby_card()
        self._build_phone_card()
        self._build_score_card()
        self._build_drives_card()
        self._build_files_card()
        self._build_bookmarks_card()
        self._build_wallpaper_card()
        self._build_fonts_card()
        self._build_saves_card()
        self._build_sticky_card()
        self._build_rdp_card()
        self._build_extras_card()
        self._build_wsl_card()

        self._stretch()

    def _build_intro_card(self):
        intro, intro_layout = _make_card("card-accent-ok")
        intro_title = QLabel("Start here if this is your first week on KythOS")
        intro_title.setObjectName("card-title")
        intro_layout.addWidget(intro_title)
        intro_body = QLabel(
            "KythOS can read PC drives, copy personal files, import Steam libraries, "
            "and point you toward the right app path for original installers. PC drives "
            "are treated carefully: migration tools read from them and copy into your home folder."
        )
        intro_body.setObjectName("card-copy")
        intro_body.setWordWrap(True)
        intro_layout.addWidget(intro_body)
        intro_btns = QHBoxLayout()
        intro_btns.setSpacing(8)
        for label, page in (
            ("Install Familiar Apps", "App Store"),
            ("Move Steam Games", "Gaming"),
            ("Back Up Saves", "Gaming"),
            ("Open File Manager", None),
        ):
            btn = QPushButton(label)
            if page:
                btn.clicked.connect(lambda _=False, key=page: self._navigate(key))
            else:
                btn.clicked.connect(lambda _=False: popen(["dolphin", os.path.expanduser("~")]) or QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.expanduser("~"))))
            intro_btns.addWidget(btn)
        intro_btns.addStretch()
        intro_layout.addLayout(intro_btns)
        self._add(intro)



    def _build_flow_card(self):
        flow_card, flow_layout = _make_card()
        flow_title = QLabel("Migration path")
        flow_title.setObjectName("card-title")
        flow_layout.addWidget(flow_title)
        for i, (title, copy) in enumerate((
            ("Scan PC drives", "Detect NTFS, BitLocker, hibernation state, user folders, Steam libraries, and safe mount points."),
            ("Choose what to copy", "Select personal folders, bookmarks, saves, or game libraries. The PC drive is the source, not the destination."),
            ("Copy into KythOS", "Files land in your home folder or Steam library on a Linux-formatted disk. Windows stays untouched."),
            ("Finish the habits", "Set up cloud sync, shortcuts, phone pairing, printer setup, and PowerToys equivalents from this page."),
        ), 1):
            flow_layout.addWidget(_make_flow_step(i, title, copy))
        self._add(flow_card)



    def _build_checklist_card(self):
        checklist, checklist_layout = _make_card()
        checklist_title = QLabel("Windows switch checklist")
        checklist_title.setObjectName("card-title")
        checklist_layout.addWidget(checklist_title)
        for status, title, text in (
            ("ok", "Apps", "Use App Store for trending Flatpaks, starter packs, AppImages, and installed apps."),
            ("ok", "Games", "Use Steam, Heroic, Lutris, or Bottles instead of running random original installers directly."),
            ("warn", "Files", "Use Copy My Files below: scan your PC drive, then copy Documents, Pictures, Music, and Videos into your home folder."),
            ("warn", "Bookmarks", "Export Chrome, Edge, or Firefox bookmarks below; passwords come across via browser sync."),
            ("warn", "Saves", "Install Ludusavi before moving large libraries or experimenting with mods."),
            ("dim", "Updates", "KythOS updates stage a new OS image. Reboot when ready; rollbacks stay available."),
        ):
            checklist_layout.addWidget(self._make_migration_row(status, title, text))
        self._add(checklist)



    def _build_shell_card(self):
        # Terminal & shell tools card
        shell_card, shell_layout = _make_card()
        shell_title = QLabel("Terminal & Shell Tools")
        shell_title.setObjectName("card-title")
        shell_layout.addWidget(shell_title)
        shell_body = QLabel(
            "KythOS ships a pre-configured terminal experience — no manual plugin installs. "
            "Every new account gets eza (better ls), bat (syntax-highlighted cat), fd (better find), "
            "ripgrep (fast search), fzf (Ctrl+R fuzzy history), zoxide (smart cd that learns your habits), "
            "git-delta (beautiful diffs), and starship (git-aware prompt). "
            "Fish and Zsh both have autosuggestions and syntax highlighting out of the box. "
            "To switch to fish: open Konsole → Settings → Edit Profiles → Command → /usr/bin/fish."
        )
        shell_body.setObjectName("card-copy")
        shell_body.setWordWrap(True)
        shell_layout.addWidget(shell_body)
        for win_tool, linux_equiv in [
            ("cmd / PowerShell", "Konsole with zsh/fish — autosuggestions + syntax highlighting"),
            ("Terminal tabs", "Konsole profiles or zellij (modern terminal multiplexer)"),
            ("Everything (search)", "fd / ripgrep — 10–100× faster, respects .gitignore"),  # noqa: RUF001 — en dash + multiplication sign, deliberate typography
            ("notepad.exe", "helix (hx) — modal editor with LSP, no config needed"),
            ("grep / findstr", "rg (ripgrep) — alias: search <pattern>"),
        ]:
            shell_layout.addWidget(self._make_migration_row("ok", win_tool, linux_equiv))
        shell_btns = QHBoxLayout()
        shell_btns.setSpacing(8)
        open_konsole_btn = QPushButton("Open Terminal")
        open_konsole_btn.clicked.connect(
            lambda _=False: popen(["konsole"])
        )
        shell_btns.addWidget(open_konsole_btn)
        shell_btns.addStretch()
        shell_layout.addLayout(shell_btns)
        self._add(shell_card)



    def _build_onedrive_card(self):
        # OneDrive / cloud sync card
        onedrive_card, onedrive_layout = _make_card()
        onedrive_title = QLabel("OneDrive & Google Drive sync")
        onedrive_title.setObjectName("card-title")
        onedrive_layout.addWidget(onedrive_title)
        onedrive_body = QLabel(
            "KythOS includes a built-in Cloud Storage wizard that connects OneDrive and Google Drive "
            "via rclone — free, open-source, and background-sync capable. Files stay in a folder "
            "in your home directory and sync automatically. No paid client needed."
        )
        onedrive_body.setObjectName("card-copy")
        onedrive_body.setWordWrap(True)
        onedrive_layout.addWidget(onedrive_body)
        onedrive_btns = QHBoxLayout()
        onedrive_btns.setSpacing(8)
        onedrive_open_btn = QPushButton("Set Up Cloud Storage")
        onedrive_open_btn.setObjectName("primary")
        onedrive_open_btn.clicked.connect(lambda _=False: self._navigate("Cloud Storage"))
        onedrive_btns.addWidget(onedrive_open_btn)
        onedrive_btns.addStretch()
        onedrive_layout.addLayout(onedrive_btns)
        self._add(onedrive_card)



    def _build_score_card(self):
        score_card, score_layout = _make_card("card-accent-ok")
        score_title = QLabel("Switch Readiness")
        score_title.setObjectName("card-title")
        score_layout.addWidget(score_title)
        self._migration_score_lbl = QLabel(
            "Scan drives to estimate migration readiness. KythOS looks at launchers, save tools, PC drives, and safe copy paths."
        )
        self._migration_score_lbl.setObjectName("card-copy")
        self._migration_score_lbl.setWordWrap(True)
        score_layout.addWidget(self._migration_score_lbl)
        score_btns = QHBoxLayout()
        for label, page in (("Install Launchers", "Gaming"), ("Back Up Saves", "Gaming"), ("Cloud Storage", "Cloud Storage")):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, key=page: self._navigate(key))
            score_btns.addWidget(btn)
        score_btns.addStretch()
        score_layout.addLayout(score_btns)
        self._add(score_card)



    def _make_migration_row(self, status: str, title: str, summary: str) -> QFrame:
        row = QFrame()
        row.setObjectName({
            "ok": "hw-card-ok",
            "warn": "hw-card-warn",
            "err": "hw-card-err",
            "dim": "hw-card-dim",
        }.get(status, "hw-card-dim"))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(10)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("card-summary")
        title_lbl.setMinimumWidth(110)
        layout.addWidget(title_lbl)
        summary_lbl = QLabel(summary)
        summary_lbl.setObjectName("card-copy")
        summary_lbl.setWordWrap(True)
        layout.addWidget(summary_lbl, 1)
        return row



    def _run_ujust(self, recipe: str, btn: QPushButton):
        btn.setEnabled(False)
        orig = btn.text()
        btn.setText("Running…")
        worker = Worker(["bash", "-c", f"ujust {recipe}"])
        def _done(code: int, b=btn, o=orig):
            b.setEnabled(True)
            b.setText("✓ Done" if code == 0 else o)
        worker.done.connect(_done)
        worker.start()
        self._worker = worker
