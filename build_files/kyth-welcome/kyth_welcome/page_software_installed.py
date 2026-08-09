import glob
import os
import shlex
import shutil
from .services.appimages import (
    appimage_entry_from_desktop_text, flatpak_uninstall_command,
    is_user_appimage_path, safe_home_targets, uninstall_app_detail,
)
from .services.desktop import REFRESH_DESKTOP_DATABASE_SH
from .services.launch import popen
from .core_base import restyle
from .services.runtime import DataWorker, Worker, finish_worker
from .qt import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)
from .widgets import CollapsibleLogPanel, _make_card


class _InstalledTabMixin:
    # ── Tab 3: Installed ──────────────────────────────────────────────────────

    def _build_installed_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        intro = QLabel("Installed Flatpak apps and user AppImages.")
        intro.setObjectName("card-copy")
        top_row.addWidget(intro, 1)
        self._uninstall_refresh_btn = QPushButton("Refresh")
        self._uninstall_refresh_btn.clicked.connect(self._refresh_installed_list)
        top_row.addWidget(self._uninstall_refresh_btn)
        layout.addLayout(top_row)

        self._uninstall_status = QLabel()
        self._uninstall_status.setObjectName("subheading")
        layout.addWidget(self._uninstall_status)

        self._uninstall_progress = QProgressBar()
        self._uninstall_progress.setRange(0, 0)
        self._uninstall_progress.hide()
        layout.addWidget(self._uninstall_progress)

        self._uninstall_log_panel = CollapsibleLogPanel(max_height=130)
        layout.addWidget(self._uninstall_log_panel)

        self._uninstall_list = QVBoxLayout()
        self._uninstall_list.setSpacing(8)
        layout.addLayout(self._uninstall_list)

        self._refresh_installed_list()
        layout.addWidget(self._build_flatpak_permissions_card())
        return tab

    def _build_flatpak_permissions_card(self) -> QFrame:
        """Inline Flatpak file-access overrides — answers 'where are my files?'.

        Windows switcher saves to ~/Documents and Flatpak app cannot see it.
        Expose --filesystem= overrides without requiring Flatseal. Uses
        DataWorker for show + Worker for apply (no GUI thread block)."""
        card, card_layout = _make_card()
        title = QLabel("Flatpak File Access — Fix 'Can't see my files'")
        title.setObjectName("card-title")
        card_layout.addWidget(title)
        desc = QLabel(
            "Flatpak apps are sandboxed. If a document saved to Documents/Downloads "
            "does not appear inside an app, grant that app access here. Uses "
            "`flatpak override --user --filesystem=` — no restart required."
        )
        desc.setObjectName("card-copy")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._perm_app_combo = QComboBox()
        self._perm_app_combo.setEditable(True)
        self._perm_app_combo.setMinimumWidth(280)
        self._perm_app_combo.setPlaceholderText("App ID, e.g. org.libreoffice.LibreOffice")
        row.addWidget(self._perm_app_combo, 1)
        self._perm_fs_combo = QComboBox()
        for label, val in (
            ("Documents", "xdg-documents"),
            ("Downloads", "xdg-downloads"),
            ("Pictures", "xdg-pictures"),
            ("Home", "home"),
            ("Host (all)", "host"),
        ):
            self._perm_fs_combo.addItem(label, val)
        row.addWidget(self._perm_fs_combo)
        grant_btn = QPushButton("Grant")
        grant_btn.clicked.connect(lambda _=False: self._apply_flatpak_permission(True))
        row.addWidget(grant_btn)
        revoke_btn = QPushButton("Revoke")
        revoke_btn.clicked.connect(lambda _=False: self._apply_flatpak_permission(False))
        row.addWidget(revoke_btn)
        card_layout.addLayout(row)
        self._perm_status = QLabel("Pick an installed Flatpak app and a folder to grant/revoke.")
        self._perm_status.setObjectName("card-copy")
        self._perm_status.setWordWrap(True)
        card_layout.addWidget(self._perm_status)
        # Populate combo from installed apps after first fetch
        return card

    def _apply_flatpak_permission(self, allow: bool) -> None:
        from .services.flatpak import flatpak_override_command
        app_id = self._perm_app_combo.currentText().strip()
        filesystem = self._perm_fs_combo.currentData()
        if not app_id:
            self._perm_status.setText("Enter an app ID first.")
            self._perm_status.setObjectName("status-warn")
            restyle(self._perm_status)
            return
        try:
            cmd = flatpak_override_command(app_id, filesystem, allow=allow)
        except ValueError as exc:
            self._perm_status.setText(str(exc))
            self._perm_status.setObjectName("status-err")
            restyle(self._perm_status)
            return
        verb = "Granting" if allow else "Revoking"
        self._perm_status.setText(f"{verb} {filesystem} for {app_id}…")
        self._perm_status.setObjectName("subheading")
        restyle(self._perm_status)
        w = Worker(cmd)
        w.line.connect(lambda _ln: None)
        w.done.connect(lambda code: self._on_perm_done(code, app_id, filesystem, allow))
        w.start()
        self._perm_worker = w

    def _on_perm_done(self, code: int, app_id: str, filesystem: str, allow: bool) -> None:
        finish_worker(self, attr="_perm_worker")
        if code == 0:
            verb = "Granted" if allow else "Revoked"
            self._perm_status.setText(f"{verb} {filesystem} for {app_id}. No restart needed.")
            self._perm_status.setObjectName("status-ok")
        else:
            self._perm_status.setText(f"Failed to update override for {app_id} (exit {code}).")
            self._perm_status.setObjectName("status-err")
        restyle(self._perm_status)

    def _refresh_installed_list(self, status_text: str | None = None, status_object: str = "subheading"):
        # _installed_flatpak_apps() shells out to `flatpak list`, uncached —
        # run it (and the AppImage scan) off the GUI thread so opening or
        # refreshing this tab doesn't freeze the page. Guard against both a
        # running uninstall (which will refresh the list itself when done)
        # and an already-in-flight list fetch.
        if self._uninstall_worker and self._uninstall_worker.isRunning():
            return
        if self._installed_list_worker is not None:
            return
        self._uninstall_status.setText(status_text or "Checking installed apps…")
        self._uninstall_status.setObjectName("subheading")
        restyle(self._uninstall_status)
        self._uninstall_refresh_btn.setEnabled(False)

        def fetch() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
            return self._installed_flatpak_apps(), self._installed_appimage_apps()

        worker = DataWorker("installed-apps", fetch)
        self._installed_list_worker = worker
        worker.result.connect(
            lambda _key, data, st=status_text, so=status_object: self._on_installed_list_ready(data, st, so)
        )
        worker.failed.connect(lambda _key, _message: self._on_installed_list_failed())
        worker.finished.connect(lambda: setattr(self, "_installed_list_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_installed_list_ready(
        self, data: tuple[list[dict[str, str]], list[dict[str, str]]],
        status_text: str | None, status_object: str,
    ) -> None:
        self._uninstall_refresh_btn.setEnabled(True)
        self._clear_uninstall_list()
        flatpak_apps, appimage_apps = data
        apps = flatpak_apps + appimage_apps
        if not apps:
            self._uninstall_status.setText(status_text or "No removable Flatpak apps or AppImages found.")
            self._uninstall_status.setObjectName(status_object)
            restyle(self._uninstall_status)
            return
        flatpak_count = sum(1 for app in apps if app["kind"] == "flatpak")
        appimage_count = sum(1 for app in apps if app["kind"] == "appimage")
        if not shutil.which("flatpak") and appimage_count == 0:
            self._uninstall_status.setText("Flatpak is not available and no AppImages were found.")
            self._uninstall_status.setObjectName("status-warn")
            restyle(self._uninstall_status)
            return
        self._uninstall_status.setText(
            status_text or (
                f"{flatpak_count} Flatpak app{'s' if flatpak_count != 1 else ''} "
                f"and {appimage_count} AppImage{'s' if appimage_count != 1 else ''} found."
            )
        )
        self._uninstall_status.setObjectName(status_object)
        restyle(self._uninstall_status)
        for app in apps:
            self._uninstall_list.addWidget(self._make_uninstall_app_row(app))

    def _on_installed_list_failed(self) -> None:
        self._uninstall_refresh_btn.setEnabled(True)
        self._uninstall_status.setText("Could not check installed apps.")
        self._uninstall_status.setObjectName("status-err")
        restyle(self._uninstall_status)

    def _clear_uninstall_list(self):
        while self._uninstall_list.count():
            item = self._uninstall_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._uninstall_buttons.clear()

    def _make_uninstall_app_row(self, app: dict[str, str]) -> QFrame:
        row = QFrame()
        row.setObjectName("stat-tile")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 10, 14, 10)
        row_layout.setSpacing(12)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(app["name"])
        name_lbl.setObjectName("card-summary")
        name_lbl.setWordWrap(True)
        text_col.addWidget(name_lbl)
        detail_lbl = QLabel(uninstall_app_detail(app))
        detail_lbl.setObjectName("card-copy")
        detail_lbl.setWordWrap(True)
        text_col.addWidget(detail_lbl)
        row_layout.addLayout(text_col, 1)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setObjectName("danger")
        uninstall_btn.clicked.connect(lambda _=False, a=app: self._uninstall_app(a))
        self._uninstall_buttons.append(uninstall_btn)
        row_layout.addWidget(uninstall_btn)
        return row

    def _set_uninstall_controls_enabled(self, enabled: bool):
        self._uninstall_refresh_btn.setEnabled(enabled)
        for btn in self._uninstall_buttons:
            btn.setEnabled(enabled)

    def _uninstall_app(self, app: dict[str, str]):
        if self._uninstall_worker and self._uninstall_worker.isRunning():
            return
        if app["kind"] == "appimage":
            self._uninstall_appimage_app(app)
        else:
            self._uninstall_flatpak_app(app)

    def _uninstall_flatpak_app(self, app: dict[str, str]):
        reply = QMessageBox.question(
            self,
            f"Uninstall {app['name']}",
            f"Remove {app['name']}?\n\n{app['app_id']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cmd = flatpak_uninstall_command(app["app_id"], app["installation"])
        self._set_uninstall_controls_enabled(False)
        self._uninstall_log_panel.reset("→ " + " ".join(shlex.quote(part) for part in cmd) + "\n")
        self._uninstall_progress.show()
        self._uninstall_status.setText(f"Uninstalling {app['name']}…")
        self._uninstall_status.setObjectName("subheading")
        restyle(self._uninstall_status)
        self._uninstall_worker = Worker(cmd)
        self._uninstall_worker.line.connect(self._on_uninstall_line)
        self._uninstall_worker.done.connect(
            lambda code, name=app["name"]: self._on_uninstall_done(code, name)
        )
        self._uninstall_worker.start()

    def _uninstall_appimage_app(self, app: dict[str, str]):
        extra = "\nIts user application-menu launcher will also be removed." if app.get("desktop_path") else ""
        reply = QMessageBox.question(
            self,
            f"Uninstall {app['name']}",
            f"Delete this AppImage from your home folder?\n\n{app['path']}{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        targets = [app["path"]]
        if app.get("desktop_path"):
            targets.append(app["desktop_path"])
        safe_targets = safe_home_targets(targets)
        if not safe_targets:
            QMessageBox.warning(
                self,
                "Cannot uninstall AppImage",
                "This AppImage does not look like a user-owned file in your home folder.",
            )
            return
        cmd = [
            "bash", "-c",
            "set -euo pipefail\n"
            "for target in \"$@\"; do\n"
            "    if [[ -e \"$target\" || -L \"$target\" ]]; then\n"
            "        rm -f -- \"$target\"\n"
            "        echo \"Removed $target\"\n"
            "    fi\n"
            "done\n"
            f"{REFRESH_DESKTOP_DATABASE_SH}\n",
            "kyth-remove-appimage",
            *safe_targets,
        ]
        self._set_uninstall_controls_enabled(False)
        self._uninstall_log_panel.reset("→ remove AppImage and launcher\n")
        for target in safe_targets:
            self._uninstall_log_panel.append(f"  {target}")
        self._uninstall_progress.show()
        self._uninstall_status.setText(f"Uninstalling {app['name']}…")
        self._uninstall_status.setObjectName("subheading")
        restyle(self._uninstall_status)
        self._uninstall_worker = Worker(cmd)
        self._uninstall_worker.line.connect(self._on_uninstall_line)
        self._uninstall_worker.done.connect(
            lambda code, name=app["name"]: self._on_uninstall_done(code, name)
        )
        self._uninstall_worker.start()

    def _on_uninstall_line(self, ln: str):
        self._uninstall_log_panel.append(ln)

    def _on_uninstall_done(self, code: int, name: str):
        self._uninstall_progress.hide()
        finish_worker(self, attr="_uninstall_worker")
        self._set_uninstall_controls_enabled(True)
        if code == 0:
            self._uninstall_log_panel.append("\nDone.")
            self._refresh_installed_list(f"{name} uninstalled.", "status-ok")
        else:
            self._uninstall_status.setText(f"Uninstall failed (exit {code}).")
            self._uninstall_status.setObjectName("status-err")
            self._uninstall_log_panel.set_expanded(True)
            restyle(self._uninstall_status)

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _installed_flatpak_apps(self) -> list[dict[str, str]]:
        from .services.flatpak import list_installed_flatpak_apps
        apps = list_installed_flatpak_apps()
        return sorted(apps, key=lambda app: app["name"].casefold())

    def _appimage_search_dirs(self) -> list[str]:
        home = os.path.expanduser("~")
        return [
            os.path.join(home, "Applications"),
            os.path.join(home, ".local", "bin"),
            os.path.join(home, "bin"),
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
        ]

    def _installed_appimage_apps(self) -> list[dict[str, str]]:
        apps_by_path: dict[str, dict[str, str]] = {}
        desktop_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
        for desktop_path in glob.glob(os.path.join(desktop_dir, "*.desktop")):
            try:
                desktop_text = open(desktop_path, encoding="utf-8").read()
            except OSError:
                continue
            app = appimage_entry_from_desktop_text(desktop_text, desktop_path)
            if app:
                apps_by_path[app["path"]] = app
        for directory in self._appimage_search_dirs():
            if not os.path.isdir(directory):
                continue
            try:
                entries = os.listdir(directory)
            except OSError:
                continue
            for name in entries:
                path = os.path.join(directory, name)
                if not is_user_appimage_path(path):
                    continue
                real = os.path.realpath(path)
                apps_by_path.setdefault(real, {
                    "kind": "appimage",
                    "app_id": real,
                    "name": os.path.basename(real),
                    "origin": "AppImage",
                    "installation": "user file",
                    "path": real,
                    "desktop_path": "",
                    "icon": "",
                })
        return sorted(apps_by_path.values(), key=lambda app: app["name"].casefold())

    def _open_terminal(self):
        for cmd in (["xdg-terminal-exec"], ["konsole"], ["xterm"]):
            if shutil.which(cmd[0]):
                try:
                    popen(cmd)
                    return
                except OSError:
                    pass
