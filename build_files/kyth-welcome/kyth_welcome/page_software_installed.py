import configparser
import glob
import os
import shlex
import shutil
import subprocess

# __KYTH_GENERATED_IMPORTS__
from .core_base import _restyle
from .services.software import Worker, _finish_worker
from .qt import (  # noqa: E501
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)
from .widgets import _set_log_panel


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

        self._uninstall_log_toggle = QPushButton("Show details")
        self._uninstall_log_toggle.setCheckable(True)
        self._uninstall_log_toggle.hide()
        layout.addWidget(self._uninstall_log_toggle)

        self._uninstall_log = QTextEdit()
        self._uninstall_log.document().setMaximumBlockCount(5000)
        self._uninstall_log.setReadOnly(True)
        self._uninstall_log.setMaximumHeight(130)
        self._uninstall_log.hide()
        layout.addWidget(self._uninstall_log)
        self._uninstall_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._uninstall_log_toggle, self._uninstall_log, checked)
        )

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
            _restyle(self._uninstall_status)
            return
        flatpak_count = sum(1 for app in apps if app["kind"] == "flatpak")
        appimage_count = sum(1 for app in apps if app["kind"] == "appimage")
        if not shutil.which("flatpak") and appimage_count == 0:
            self._uninstall_status.setText("Flatpak is not available and no AppImages were found.")
            self._uninstall_status.setObjectName("status-warn")
            _restyle(self._uninstall_status)
            return
        self._uninstall_status.setText(
            status_text or (
                f"{flatpak_count} Flatpak app{'s' if flatpak_count != 1 else ''} "
                f"and {appimage_count} AppImage{'s' if appimage_count != 1 else ''} found."
            )
        )
        self._uninstall_status.setObjectName(status_object)
        _restyle(self._uninstall_status)
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
        detail_lbl = QLabel(self._uninstall_app_detail(app))
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

    def _uninstall_app_detail(self, app: dict[str, str]) -> str:
        if app["kind"] == "appimage":
            launcher = " · launcher" if app.get("desktop_path") else ""
            return f"{app['path']} · AppImage{launcher}"
        return f"{app['app_id']} · {app['installation']} install · {app['origin']}"

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
        cmd = ["flatpak", "uninstall", "-y"]
        if app["installation"] == "user":
            cmd.append("--user")
        elif app["installation"] == "system":
            cmd.append("--system")
        cmd.append(app["app_id"])
        self._set_uninstall_controls_enabled(False)
        self._uninstall_log.clear()
        self._uninstall_log.append("→ " + " ".join(shlex.quote(part) for part in cmd) + "\n")
        self._uninstall_log_toggle.show()
        _set_log_panel(self._uninstall_log_toggle, self._uninstall_log, False)
        self._uninstall_progress.show()
        self._uninstall_status.setText(f"Uninstalling {app['name']}…")
        self._uninstall_status.setObjectName("subheading")
        _restyle(self._uninstall_status)
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
        safe_targets: list[str] = []
        for target in targets:
            real = os.path.realpath(os.path.expanduser(target))
            home = os.path.realpath(os.path.expanduser("~"))
            if real.startswith(home + os.sep):
                safe_targets.append(real)
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
            "update-desktop-database \"$HOME/.local/share/applications\" 2>/dev/null || true\n"
            "kbuildsycoca6 --noincremental 2>/dev/null || true\n",
            "kyth-remove-appimage",
            *safe_targets,
        ]
        self._set_uninstall_controls_enabled(False)
        self._uninstall_log.clear()
        self._uninstall_log.append("→ remove AppImage and launcher\n")
        for target in safe_targets:
            self._uninstall_log.append(f"  {target}")
        self._uninstall_log_toggle.show()
        _set_log_panel(self._uninstall_log_toggle, self._uninstall_log, False)
        self._uninstall_progress.show()
        self._uninstall_status.setText(f"Uninstalling {app['name']}…")
        self._uninstall_status.setObjectName("subheading")
        _restyle(self._uninstall_status)
        self._uninstall_worker = Worker(cmd)
        self._uninstall_worker.line.connect(self._on_uninstall_line)
        self._uninstall_worker.done.connect(
            lambda code, name=app["name"]: self._on_uninstall_done(code, name)
        )
        self._uninstall_worker.start()

    def _on_uninstall_line(self, ln: str):
        self._uninstall_log.append(ln)
        self._uninstall_log.ensureCursorVisible()

    def _on_uninstall_done(self, code: int, name: str):
        self._uninstall_progress.hide()
        _finish_worker(self, attr="_uninstall_worker")
        self._set_uninstall_controls_enabled(True)
        if code == 0:
            self._uninstall_log.append("\nDone.")
            self._refresh_installed_list(f"{name} uninstalled.", "status-ok")
        else:
            self._uninstall_status.setText(f"Uninstall failed (exit {code}).")
            self._uninstall_status.setObjectName("status-err")
            _set_log_panel(self._uninstall_log_toggle, self._uninstall_log, True)
            _restyle(self._uninstall_status)

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _installed_flatpak_apps(self) -> list[dict[str, str]]:
        if not shutil.which("flatpak"):
            return []
        try:
            _en_env = {**os.environ, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
            result = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application,name,origin,installation"],
                capture_output=True, text=True, timeout=12, check=False,
                env=_en_env,
            )
        except Exception:
            return []
        apps: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            app_id, name, origin, installation = (part.strip() for part in parts[:4])
            if not app_id:
                continue
            apps.append({
                "kind": "flatpak",
                "app_id": app_id,
                "name": name or app_id,
                "origin": origin or "unknown",
                "installation": installation or "default",
            })
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

    def _path_is_user_appimage(self, path: str) -> bool:
        if not path:
            return False
        try:
            real = os.path.realpath(os.path.expanduser(path))
            home = os.path.realpath(os.path.expanduser("~"))
        except OSError:
            return False
        return (
            real.startswith(home + os.sep)
            and os.path.isfile(real)
            and os.path.basename(real).lower().endswith(".appimage")
        )

    def _desktop_entry_for_appimage(self, desktop_path: str) -> dict[str, str] | None:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        try:
            parser.read(desktop_path, encoding="utf-8")
        except Exception:
            return None
        if not parser.has_section("Desktop Entry"):
            return None
        entry = parser["Desktop Entry"]
        exec_line = entry.get("Exec", "")
        try_exec = entry.get("TryExec", "")
        candidates: list[str] = []
        for line in (exec_line, try_exec):
            if not line:
                continue
            try:
                parts = shlex.split(line)
            except ValueError:
                parts = line.split()
            candidates.extend(part for part in parts if ".AppImage" in part or ".appimage" in part)
        appimage_path = next((part for part in candidates if self._path_is_user_appimage(part)), "")
        if not appimage_path:
            return None
        appimage_path = os.path.realpath(os.path.expanduser(appimage_path))
        return {
            "kind": "appimage",
            "app_id": appimage_path,
            "name": entry.get("Name", "") or os.path.basename(appimage_path),
            "origin": "AppImage",
            "installation": "user file",
            "path": appimage_path,
            "desktop_path": desktop_path,
            "icon": entry.get("Icon", ""),
        }

    def _installed_appimage_apps(self) -> list[dict[str, str]]:
        apps_by_path: dict[str, dict[str, str]] = {}
        desktop_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
        for desktop_path in glob.glob(os.path.join(desktop_dir, "*.desktop")):
            app = self._desktop_entry_for_appimage(desktop_path)
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
                if not self._path_is_user_appimage(path):
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
                    subprocess.Popen(cmd)
                    return
                except OSError:
                    pass
