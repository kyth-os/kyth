"""Shared business logic and Qt UI dialog for kyth-exe-handler."""
from __future__ import annotations

import configparser
import logging
import os
import re
import shlex
import shutil
import subprocess

_logger = logging.getLogger(__name__)

from ..apps import suggest_app

from ..commands import run as run_command
from ..qt import (
    QApplication,
    QCheckBox,
    QDesktopServices,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QUrl,
    QVBoxLayout,
    Signal,
    single_shot,
)
from .qt_threads import TrackedThread, shutdown_threads
from .windows_installer import (
    Compatibility,
    InstallerRequest,
    WindowsInstallerWorkflow,
    WorkflowFailure,
    assess_compatibility,
    inspect_installer,
)

_BOTTLES_ID = "com.usebottles.bottles"
_CONF_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "kyth",
    "exe-handler.conf",
)

_QSS = """
* { font-family: "Noto Sans", "Segoe UI", sans-serif; font-size: 13px; color: #cccccc; }
QDialog { background: #1e1e1e; }
QWidget { background: transparent; }
QLabel  { background: transparent; }
QFrame#sep { color: #3e3e42; }
QPushButton {
    background: #2d2d30; color: #cccccc;
    border: 1px solid #3e3e42; border-radius: 4px;
    padding: 6px 16px; min-height: 28px;
}
QPushButton:hover  { background: #3e3e42; color: #ffffff; }
QPushButton#primary {
    background: #0e639c; color: #ffffff; border-color: #1177bb;
}
QPushButton#primary:hover { background: #1177bb; }
QCheckBox { color: #aaaaaa; spacing: 8px; }
QCheckBox:hover { color: #cccccc; }
"""


def normalise_filename(filename: str) -> str:
    """Strip common wrapper/release tokens from installer filename to form a clean stem."""
    stem = os.path.splitext(os.path.basename(filename))[0].lower()
    stem = re.sub(r"[\s.]+", "-", stem)
    wrapper = r"(setup|install|installer|update|updater|launcher)"
    token = r"(x64|x86|x86_64|amd64|win64|win32|windows|pc|arm64|online|offline|stable|v?\d[\d.]*)"
    for _ in range(4):
        old = stem
        stem = re.sub(rf"^({wrapper})[-_]+", "", stem)
        stem = re.sub(rf"[-_]+({wrapper})$", "", stem)
        stem = re.sub(rf"[-_]+({token})$", "", stem)
        if stem == old:
            break
    return stem


def lookup_app_suggestion(filepath: str) -> tuple[str | None, str | None, str | None]:
    """Look up file stem suggestion using local fallback or system database."""
    stem = normalise_filename(filepath)
    local_json = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "exe-handler-apps.json",
    )
    if os.path.exists(local_json):
        return suggest_app(stem, path=local_json)
    return suggest_app(stem)


def is_rpm_installer(filepath: str) -> bool:
    """Return True if target file is an RPM package."""
    return filepath.lower().endswith(".rpm")


def load_auto_bottles(conf_path: str = _CONF_PATH) -> bool:
    """Load auto_bottles setting from configuration file."""
    parser = configparser.ConfigParser()
    try:
        parser.read(conf_path)
        return parser.getboolean("exe-handler", "auto_bottles", fallback=False)
    except (configparser.Error, ValueError):
        return False


def save_auto_bottles(enabled: bool, conf_path: str = _CONF_PATH) -> None:
    """Save auto_bottles setting to configuration file."""
    parser = configparser.ConfigParser()
    try:
        parser.read(conf_path)
    except configparser.Error:
        parser = configparser.ConfigParser()
    if not parser.has_section("exe-handler"):
        parser.add_section("exe-handler")
    parser.set("exe-handler", "auto_bottles", "true" if enabled else "false")
    os.makedirs(os.path.dirname(conf_path), exist_ok=True)
    with open(conf_path, "w", encoding="utf-8") as fh:
        parser.write(fh)


def open_system_hub_page(page: str) -> None:
    """Launch Kyth Pulse focused on a given page."""
    launcher = shutil.which("kyth-welcome-launch") or "/usr/bin/kyth-welcome-launch"
    try:
        subprocess.Popen([launcher, "--page", page])  # noqa: S603 -- fixed launcher argv
    except OSError as exc:
        _logger.debug("open_system_hub_page failed: %s", exc, exc_info=True)


def is_flatpak_installed(flatpak_id: str) -> bool:
    """Check if a flatpak ID is installed on the host."""
    res = run_command(["flatpak", "info", flatpak_id], check=False)
    return res.returncode == 0



def launch_flatpak_install(flatpak_id: str) -> None:
    """Launch terminal to install a flatpak interactively/non-interactively."""
    terminal = next(
        (t for t in ("konsole", "gnome-terminal", "xterm") if shutil.which(t)),
        None,
    )
    cmd = [
        "bash",
        "-lc",
        "flatpak remote-add --if-not-exists --user flathub "
        "https://dl.flathub.org/repo/flathub.flatpakrepo && "
        "flatpak install -y --noninteractive --user flathub "
        + shlex.quote(flatpak_id),
    ]
    try:
        if terminal == "konsole":
            subprocess.Popen(["konsole", "-e"] + cmd)  # noqa: S603 -- fixed terminal argv
        elif terminal == "gnome-terminal":
            subprocess.Popen(["gnome-terminal", "--"] + cmd)  # noqa: S603
        elif terminal == "xterm":
            subprocess.Popen(["xterm", "-e"] + cmd)  # noqa: S603
        else:
            subprocess.Popen(cmd)  # noqa: S603 -- fixed bash -lc wrapper
    except OSError as exc:
        _logger.debug("launch_flatpak_install failed for %s: %s", flatpak_id, exc, exc_info=True)


class _InstallerWorker(TrackedThread):
    status = Signal(str)
    completed = Signal(object)
    failed = Signal(str, str)

    def __init__(self, request: InstallerRequest, parent=None) -> None:
        super().__init__(parent)
        self._request = request

    def run(self) -> None:
        try:
            result = WindowsInstallerWorkflow().execute(self._request, self.status.emit)
        except WorkflowFailure as exc:
            self.failed.emit(exc.kind.value, str(exc))
        except Exception as exc:  # noqa: BLE001 -- always emit failed so the dialog cannot hang
            self.failed.emit("unexpected", f"Unexpected installer error: {exc}")
        else:
            self.completed.emit(result)


class _InstallerDialog(QDialog):
    """Keep the workflow alive if the user closes the window mid-operation."""

    busy = False

    def reject(self) -> None:
        if not self.busy:
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        if self.busy:
            event.ignore()
            return
        super().closeEvent(event)


def run_exe_handler(argv: list[str]) -> int:
    """Main execution handler logic for CLI or Dolphin invocation."""
    force_dialog = "--dialog" in argv[1:]
    args = [a for a in argv[1:] if a != "--dialog"]
    if not args:
        return 0

    filepath = args[0]
    is_rpm = is_rpm_installer(filepath)

    request = None
    assessment = None
    if not is_rpm:
        try:
            request = inspect_installer(filepath)
            assessment = assess_compatibility(request)
        except WorkflowFailure as exc:
            app = QApplication(argv)
            QMessageBox.warning(None, "KythOS — Cannot Open Installer", str(exc))
            return 1

    if is_rpm:
        app_name = "RPM Package"
        suggestion = (
            "This is an RPM package for traditional mutable Fedora/RHEL-style systems.\n\n"
            "On KythOS, install desktop apps from App Store or Flathub. Use Distrobox "
            "for command-line tools that need dnf. Only layer system RPMs when a KythOS "
            "guide explicitly tells you to, because base-system changes require a reboot "
            "and can complicate updates."
        )
        flatpak_id = None
    else:
        app_name, suggestion, flatpak_id = lookup_app_suggestion(filepath)

    basename = os.path.basename(filepath)
    search_basis = (
        os.path.splitext(basename)[0]
        if is_rpm
        else (app_name or os.path.splitext(basename)[0])
    )
    search_term = search_basis.replace(" ", "+")

    app = QApplication(argv)
    app.setStyleSheet(_QSS)
    app.aboutToQuit.connect(shutdown_threads)

    dlg = _InstallerDialog()
    dlg.setWindowTitle(
        "KythOS — Installer Help" if is_rpm else "KythOS — Windows Application"
    )
    dlg.setMinimumWidth(500)
    dlg.setMaximumWidth(600)

    root = QVBoxLayout(dlg)
    root.setContentsMargins(24, 24, 24, 20)
    root.setSpacing(14)

    title = QLabel(f"<b>{app_name or 'Windows Application'}</b>")
    title.setStyleSheet("font-size: 16px; color: #ffffff;")
    root.addWidget(title)

    file_lbl = QLabel(f"<span style='color:#888888; font-size:12px;'>{basename}</span>")
    file_lbl.setWordWrap(True)
    root.addWidget(file_lbl)

    sep = QFrame()
    sep.setObjectName("sep")
    sep.setFrameShape(QFrame.Shape.HLine)
    root.addWidget(sep)

    body_text = suggestion or (
        "This is a Windows application installer. KythOS runs Linux software natively.\n\n"
        "Search Flathub for a Linux equivalent, or run it inside Bottles (Wine)."
    )
    body = QLabel(body_text)
    body.setWordWrap(True)
    body.setStyleSheet("color: #d4d4d4; line-height: 1.5;")
    root.addWidget(body)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)

    progress = QProgressBar()
    progress.setRange(0, 0)
    progress.setVisible(False)
    status = QLabel("")
    status.setWordWrap(True)
    status.setVisible(False)

    run_btn = None
    if request is not None and assessment is not None:
        level_labels = {
            Compatibility.LIKELY: "LIKELY COMPATIBLE",
            Compatibility.UNKNOWN: "UNKNOWN — TRY IT",
            Compatibility.UNSUPPORTED: "KNOWN LIMITATION",
        }
        level_colors = {
            Compatibility.LIKELY: "#73c991",
            Compatibility.UNKNOWN: "#d7ba7d",
            Compatibility.UNSUPPORTED: "#f48771",
        }
        compatibility = QLabel(
            f"<b>{level_labels[assessment.level]}</b> — {assessment.summary}<br>"
            f"<span style='color:#aaaaaa'>{assessment.detail}</span>"
        )
        compatibility.setWordWrap(True)
        compatibility.setStyleSheet(f"color: {level_colors[assessment.level]};")
        root.addWidget(compatibility)

        expectations = QLabel(
            "Kyth runs Windows software in an isolated compatibility environment. "
            "Applications requiring Windows drivers, kernel anti-cheat, device services, "
            "or Microsoft Store components generally will not work."
        )
        expectations.setWordWrap(True)
        expectations.setStyleSheet("color:#aaaaaa; font-size:12px;")
        root.addWidget(expectations)

        fingerprint = QLabel(f"SHA-256: {request.sha256[:16]}…")
        fingerprint.setStyleSheet("color:#777777; font-size:11px;")
        root.addWidget(fingerprint)

        root.addWidget(progress)
        root.addWidget(status)

    if is_rpm:
        app_store_btn = QPushButton("Open App Store")
        app_store_btn.setObjectName("primary")
        app_store_btn.clicked.connect(
            lambda: (open_system_hub_page("App Store"), dlg.accept())
        )
        btn_row.addWidget(app_store_btn)

    if flatpak_id:
        if is_flatpak_installed(flatpak_id):
            launch_btn = QPushButton("Launch →")
            launch_btn.setObjectName("primary")
            launch_btn.clicked.connect(
                lambda: (subprocess.Popen(["flatpak", "run", flatpak_id]), dlg.accept())
            )
            btn_row.addWidget(launch_btn)
        else:
            install_btn = QPushButton("Install Linux Version")
            install_btn.setObjectName("primary")
            install_btn.clicked.connect(
                lambda: (launch_flatpak_install(flatpak_id), dlg.accept())
            )
            btn_row.addWidget(install_btn)

    flathub_btn = QPushButton("Search Flathub")
    flathub_btn.clicked.connect(
        lambda: (
            QDesktopServices.openUrl(
                QUrl(f"https://flathub.org/apps/search?q={search_term}")
            ),
            dlg.accept(),
        )
    )
    btn_row.addWidget(flathub_btn)

    if request is not None and assessment is not None:
        run_btn = QPushButton(
            "Try Anyway" if assessment.level is Compatibility.UNSUPPORTED else "Run Windows Installer"
        )
        if assessment.level is not Compatibility.UNSUPPORTED:
            run_btn.setObjectName("primary")
        run_btn.setToolTip("Prepare an isolated Bottles environment and open this installer")
        btn_row.insertWidget(0, run_btn)

    btn_row.addStretch()

    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dlg.reject)
    btn_row.addWidget(cancel_btn)

    auto_chk = None
    if request is not None:
        auto_chk = QCheckBox("Automatically prepare and run future Windows installers")
        auto_chk.setChecked(load_auto_bottles())
        auto_chk.setToolTip(
            "Future valid .exe/.msi files start this isolated workflow immediately.\n"
            f"Saved to {_CONF_PATH}.\n"
            "To see this dialog again, run: kyth-exe-handler --dialog <file>"
        )
        dlg.finished.connect(lambda _: save_auto_bottles(auto_chk.isChecked()))
        root.addWidget(auto_chk)

    root.addLayout(btn_row)

    if request is not None and assessment is not None and run_btn is not None:
        worker_holder: dict[str, _InstallerWorker] = {}
        launch_succeeded = False

        def set_busy(busy: bool) -> None:
            dlg.busy = busy
            progress.setVisible(busy)
            status.setVisible(True)
            for index in range(btn_row.count()):
                widget = btn_row.itemAt(index).widget()
                if widget is not None:
                    widget.setEnabled(not busy)

        def workflow_failed(kind: str, message: str) -> None:
            set_busy(False)
            recovery = {
                "file-changed": "Reopen the downloaded file, then try again.",
                "bottles-install": "Check your internet connection and try again.",
                "bottle-create": "Open Bottles once, close it, then try again.",
                "file-stage": "Check available disk space and try again.",
                "launch": "Open Bottles to inspect the environment, or try again.",
            }.get(kind, "Try again, or use a native Linux alternative when available.")
            run_btn.setText("Retry")
            status.setText(f"Could not open the installer: {message}\n{recovery}")
            status.setStyleSheet("color:#f48771;")
            QMessageBox.warning(
                dlg,
                "Windows Installer Could Not Start",
                f"{message}\n\n{recovery}",
            )

        def workflow_completed(_result: object) -> None:
            nonlocal launch_succeeded
            launch_succeeded = True
            status.setText("The Windows installer is opening in its isolated environment.")
            status.setStyleSheet("color:#73c991;")

        def worker_finished() -> None:
            if launch_succeeded:
                dlg.busy = False
                dlg.accept()

        def start_workflow() -> None:
            if assessment.level is Compatibility.UNSUPPORTED:
                answer = QMessageBox.question(
                    dlg,
                    "Try Unsupported Windows Installer?",
                    assessment.detail + "\n\nYou can still try it, but it is unlikely to work.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            set_busy(True)
            status.setText("Checking Windows compatibility support…")
            status.setStyleSheet("color:#d4d4d4;")
            worker = _InstallerWorker(request, dlg)
            worker_holder["worker"] = worker
            worker.status.connect(status.setText)
            worker.failed.connect(workflow_failed)
            worker.completed.connect(workflow_completed)
            worker.finished.connect(worker_finished)
            worker.start()

        run_btn.clicked.connect(start_workflow)
        if (
            not force_dialog
            and load_auto_bottles()
            and assessment.level is not Compatibility.UNSUPPORTED
        ):
            dlg.setWindowTitle("KythOS — Preparing Windows Application")
            single_shot(dlg, 0, start_workflow)

    return dlg.exec()
