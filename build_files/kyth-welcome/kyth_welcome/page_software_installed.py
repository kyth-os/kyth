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
from .services.runtime import Worker, finish_worker
from .qt import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)
from .widgets import CollapsibleLogPanel


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
        return tab

    def _refresh_installed_list(self, status_text: str | None = None, status_object: str = "subheading"):
        if self._uninstall_worker and self._uninstall_worker.isRunning():
            return
        self._clear_uninstall_list()
        apps = self._installed_flatpak_apps() + self._installed_appimage_apps()
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
