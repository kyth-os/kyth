import os

# __KYTH_GENERATED_IMPORTS__
from .services.process import _run_command
from .services.gaming import (
    _streaming_health_items, command_details, discord_screenshare_fix_command, obs_pipewire_fix_command
)
from .services.software import _install_flatpak_inline
from .qt import QDesktopServices, QHBoxLayout, QLabel, QPushButton, QUrl
from .widgets import ActionRow, _copy_text, _launch_opt_label, _launch_opt_value, _make_card


class _FixesMixin:
    """First-failure playbook and Fix-my-game shortcuts — the GAMING HUB "fixes" section."""

    def _build_first_failure_playbook_card(self):
        # ── First-failure playbook ────────────────────────────────────────────
        playbook_card, playbook_layout = _make_card()
        playbook_title = QLabel("Game will not launch")
        playbook_title.setObjectName("card-title")
        playbook_layout.addWidget(playbook_title)
        playbook_desc = QLabel(
            "Start simple: try a clean Proton runner, collect a log, then disable one "
            "sync path at a time. These launch options are safe per-game tests."
        )
        playbook_desc.setObjectName("card-copy")
        playbook_desc.setWordWrap(True)
        playbook_layout.addWidget(playbook_desc)
        for label, opt in (
            ("Capture Proton log:", "PROTON_LOG=1 %command%"),
            ("Disable NTSYNC:", "PROTON_NO_NTSYNC=1 %command%"),
            ("Disable esync:", "PROTON_NO_ESYNC=1 %command%"),
            ("Disable fsync:", "PROTON_NO_FSYNC=1 %command%"),
            ("Force Vulkan HUD:", "MANGOHUD=1 %command%"),
            ("Launcher retry:", "PROTON_LOG=1 PROTON_NO_NTSYNC=1 %command%"),
        ):
            playbook_layout.addLayout(self._copy_option_row(label, opt))
        playbook_btns = QHBoxLayout()
        playbook_btns.setSpacing(8)
        protondb_btn = QPushButton("Open ProtonDB")
        protondb_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.protondb.com")))
        playbook_btns.addWidget(protondb_btn)
        anticheat_btn = QPushButton("Open Anti-Cheat Status")
        anticheat_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://areweanticheatyet.com")))
        playbook_btns.addWidget(anticheat_btn)
        playbook_btns.addStretch()
        playbook_layout.addLayout(playbook_btns)
        self._add(playbook_card)

    def _build_fix_my_game_card(self):
        # ── Fix my game ──────────────────────────────────────────────────────
        fix_card, fix_layout = _make_card()
        fix_title = QLabel("Fix My Game")
        fix_title.setObjectName("card-title")
        fix_layout.addWidget(fix_title)
        fix_desc = QLabel(
            "Fast non-destructive support actions: open the folders players need, "
            "copy safe launch tests, and generate diagnostics."
        )
        fix_desc.setObjectName("card-copy")
        fix_desc.setWordWrap(True)
        fix_layout.addWidget(fix_desc)
        fix_actions = ActionRow("", "idle")
        for label, action in (
            ("Open Steam compatdata", lambda: self._open_user_path("~/.local/share/Steam/steamapps/compatdata")),
            ("Open shadercache", lambda: self._open_user_path("~/.local/share/Steam/steamapps/shadercache")),
            ("Copy reset-prefix command", self._copy_prefix_reset_hint),
            ("Copy support snapshot", self._copy_support_snapshot_command),
        ):
            fix_actions.add_button(label, action)
        fix_actions.finish()
        self._fix_status_lbl = fix_actions.status
        self._fix_status_lbl.hide()
        fix_layout.addWidget(fix_actions)
        self._add(fix_card)

    def _copy_option_row(self, label: str, opt: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_launch_opt_label(label))
        row.addWidget(_launch_opt_value(opt))
        cp = QPushButton("Copy")
        cp.clicked.connect(lambda _=False, t=opt: _copy_text(t))
        row.addWidget(cp)
        row.addStretch()
        return row

    def _refresh_streaming_health(self):
        self._set_rows_loading(self._streaming_rows_layout, "Checking Discord, OBS, capture, audio, and camera tools…")
        self._start_data_worker("streaming", _streaming_health_items)

    def _render_streaming_health(self, items: list[tuple[str, str, str]]):
        if not hasattr(self, "_streaming_rows_layout"):
            return
        self._clear_rows(self._streaming_rows_layout)
        for status, title, summary in items:
            self._streaming_rows_layout.addWidget(self._make_health_row(status, title, summary))

    def _fix_discord_screenshare(self):
        self._discord_fix_btn.setEnabled(False)
        cmd = discord_screenshare_fix_command()
        self._discord_fix_status.hide()
        self._discord_fix_result.set_running("Applying Discord screen share repair…", command_details(cmd))
        result = _run_command(cmd, timeout=10)
        if result is not None and result.returncode == 0:
            self._discord_fix_result.set_result(
                "ok",
                "Applied. Restart Discord to take effect.",
                command_details(cmd, result),
            )
        elif result is not None:
            err = (result.stderr or result.stdout or "").strip()
            self._discord_fix_result.set_result(
                "err",
                f"Could not repair Discord screen share: {err or 'unknown error'}.",
                command_details(cmd, result),
            )
        else:
            self._discord_fix_result.set_result(
                "err",
                "Could not repair Discord screen share: command failed to start.",
                command_details(cmd),
            )
        self._discord_fix_btn.setEnabled(True)

    def _fix_obs_pipewire(self):
        self._obs_fix_btn.setEnabled(False)
        cmd = obs_pipewire_fix_command()
        self._obs_fix_status.hide()
        self._obs_fix_result.set_running("Applying OBS capture repair…", command_details(cmd))
        result = _run_command(cmd, timeout=10)
        if result is not None and result.returncode == 0:
            self._obs_fix_result.set_result(
                "ok",
                "Applied. Restart OBS to take effect.",
                command_details(cmd, result),
            )
        elif result is not None:
            err = (result.stderr or result.stdout or "").strip()
            self._obs_fix_result.set_result(
                "err",
                f"Could not repair OBS capture: {err or 'unknown error'}.",
                command_details(cmd, result),
            )
        else:
            self._obs_fix_result.set_result(
                "err",
                "Could not repair OBS capture: command failed to start.",
                command_details(cmd),
            )
        self._obs_fix_btn.setEnabled(True)

    def _open_user_path(self, path: str):
        expanded = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(expanded):
            self._set_status_badge(self._fix_status_lbl, "warn", f"Folder not found yet: {expanded}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(expanded))
        self._set_status_badge(self._fix_status_lbl, "ok", f"Opened {expanded}")

    def _copy_prefix_reset_hint(self):
        text = (
            "# Replace APPID with the Steam app id. This moves the Proton prefix aside as a backup.\n"
            "mv ~/.local/share/Steam/steamapps/compatdata/APPID "
            "~/.local/share/Steam/steamapps/compatdata/APPID.bak-$(date +%Y%m%d-%H%M%S)"
        )
        _copy_text(text)
        self._set_status_badge(
            self._fix_status_lbl,
            "ok",
            "Copied a safe Proton prefix reset command with an APPID placeholder.",
        )

    def _copy_support_snapshot_command(self):
        text = "kyth-device-info | tee ~/kyth-device-info.txt"
        _copy_text(text)
        self._set_status_badge(self._fix_status_lbl, "ok", "Copied support snapshot command.")

    def _install_obs_inline(self, btn: QPushButton):
        # ujust install-obs also enables obs-vkcapture; mirror that here.
        _install_flatpak_inline(
            self, btn, "com.obsproject.Studio", "OBS Studio",
            extra_cmd="flatpak override --user --env=OBS_VKCAPTURE=1 com.obsproject.Studio || true",
        )
