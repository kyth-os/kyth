import shutil
import subprocess

# __KYTH_GENERATED_IMPORTS__
from .core_base import _restyle
from .services.software import Worker, _finish_worker
from .qt import (  # noqa: E501
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)
from .widgets import _make_card, _set_log_panel


def _is_distrobox_container(name: str) -> bool:
    """Return True if a distrobox container with the given name exists."""
    try:
        result = subprocess.run(
            ["distrobox", "list", "--no-color"],
            capture_output=True, text=True, timeout=10,
        )
        return name in result.stdout
    except Exception:
        return False


_INSTALL_VSCODE_CMD = [
    "bash", "-c",
    "set -euo pipefail\n"
    "kyth-vscode-wallet\n"
    "echo 'VS Code and Headroom are baked into the image. Password storage configured.'",
]

_SETUP_DEV_BOX_CMD = [
    "bash", "-c",
    r"""set -euo pipefail
box="kyth-dev"
image="${KYTH_DEV_IMAGE:-registry.fedoraproject.org/fedora-toolbox:44}"
packages=(
    git gh just jq yq skopeo podman buildah
    python3 python3-pip python3-virtualenv
    ShellCheck shfmt ripgrep fd-find
    vim-enhanced neovim
)

if ! command -v distrobox >/dev/null 2>&1; then
    echo "ERROR: distrobox is not installed on this system." >&2
    exit 1
fi

kyth-vscode-wallet

if distrobox list --no-color 2>/dev/null | grep -q "^${box}\b"; then
    echo "${box} dev box already exists."
    echo "Use 'Enter Dev Box' to open it."
    exit 0
fi

echo "Creating KythOS development box..."
echo "  Image: ${image}"
distrobox create --image "${image}" --name "${box}" --yes
distrobox enter "${box}" -- sudo dnf install -y "${packages[@]}"
echo ""
echo "Done. Use 'Enter Dev Box' to start developing."
""",
]


class _DeveloperTabMixin:
    # ── Tab 5: Developer ──────────────────────────────────────────────────────

    def _build_developer_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel("Developer Workstations")
        title.setObjectName("section-title")
        layout.addWidget(title)

        dev_card, dev_layout = _make_card()
        dev_title = QLabel("Kyth Dev Box")
        dev_title.setObjectName("card-title")
        dev_layout.addWidget(dev_title)

        dev_desc = QLabel(
            "Create a Fedora Toolbox-based Distrobox for mutable language tools while keeping the base OS atomic."
        )
        dev_desc.setWordWrap(True)
        dev_layout.addWidget(dev_desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._dev_setup_btn = QPushButton("Setup")
        self._dev_setup_btn.setObjectName("primary")
        self._dev_enter_btn = QPushButton("Enter")
        self._dev_delete_btn = QPushButton("Delete")
        self._dev_delete_btn.setObjectName("danger")
        self._dev_log_toggle = QPushButton("Show Log")
        self._dev_log_toggle.setCheckable(True)
        self._dev_enter_btn.clicked.connect(self._dev_enter_dev_box)
        self._dev_setup_btn.clicked.connect(self._dev_run_setup)
        self._dev_delete_btn.clicked.connect(self._dev_confirm_delete)
        for btn in (self._dev_setup_btn, self._dev_enter_btn, self._dev_delete_btn, self._dev_log_toggle):
            btn_row.addWidget(btn)
        btn_row.addStretch(1)
        dev_layout.addLayout(btn_row)

        self._dev_status_lbl = QLabel("Ready.")
        self._dev_status_lbl.setObjectName("status-muted")
        dev_layout.addWidget(self._dev_status_lbl)

        self._dev_progress = QProgressBar()
        self._dev_progress.setRange(0, 0)
        self._dev_progress.hide()
        dev_layout.addWidget(self._dev_progress)

        self._dev_log = QTextEdit()
        self._dev_log.document().setMaximumBlockCount(5000)
        self._dev_log.setReadOnly(True)
        self._dev_log.hide()
        dev_layout.addWidget(self._dev_log)
        self._dev_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._dev_log_toggle, self._dev_log, checked)
        )
        layout.addWidget(dev_card)

        ai_card, ai_layout = _make_card()
        ai_title = QLabel("AI Dev Environment")
        ai_title.setObjectName("card-title")
        ai_layout.addWidget(ai_title)

        ai_desc = QLabel(
            "Create an opt-in local AI developer Distrobox with Ollama, llama.cpp, Python, Node, Rust, and GPU diagnostics. Models are never downloaded automatically."
        )
        ai_desc.setWordWrap(True)
        ai_layout.addWidget(ai_desc)

        ai_btn_row = QHBoxLayout()
        ai_btn_row.setSpacing(10)
        self._ai_setup_btn = QPushButton("Setup")
        self._ai_setup_btn.setObjectName("primary")
        self._ai_status_btn = QPushButton("Status")
        self._ai_enter_btn = QPushButton("Enter")
        self._ai_start_btn = QPushButton("Start")
        self._ai_stop_btn = QPushButton("Stop")
        self._ai_delete_btn = QPushButton("Delete")
        self._ai_delete_btn.setObjectName("danger")
        self._ai_log_toggle = QPushButton("Show Log")
        self._ai_log_toggle.setCheckable(True)
        self._ai_setup_btn.clicked.connect(lambda _=False: self._ai_run("setup"))
        self._ai_status_btn.clicked.connect(lambda _=False: self._ai_run("status"))
        self._ai_enter_btn.clicked.connect(self._ai_enter_box)
        self._ai_start_btn.clicked.connect(lambda _=False: self._ai_run("start"))
        self._ai_stop_btn.clicked.connect(lambda _=False: self._ai_run("stop"))
        self._ai_delete_btn.clicked.connect(lambda _=False: self._ai_run("remove"))
        for btn in (
            self._ai_setup_btn,
            self._ai_status_btn,
            self._ai_enter_btn,
            self._ai_start_btn,
            self._ai_stop_btn,
            self._ai_delete_btn,
            self._ai_log_toggle,
        ):
            ai_btn_row.addWidget(btn)
        ai_btn_row.addStretch(1)
        ai_layout.addLayout(ai_btn_row)

        self._ai_status_lbl = QLabel("Ready.")
        self._ai_status_lbl.setObjectName("status-muted")
        ai_layout.addWidget(self._ai_status_lbl)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.hide()
        ai_layout.addWidget(self._ai_progress)

        self._ai_log = QTextEdit()
        self._ai_log.document().setMaximumBlockCount(5000)
        self._ai_log.setReadOnly(True)
        self._ai_log.hide()
        ai_layout.addWidget(self._ai_log)
        self._ai_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._ai_log_toggle, self._ai_log, checked)
        )
        layout.addWidget(ai_card)
        layout.addStretch(1)
        return page

    def _dev_run_setup(self):
        if self._dev_worker and self._dev_worker.isRunning():
            return
        self._dev_setup_btn.setEnabled(False)
        self._dev_log.clear()
        self._dev_log.append("→ bash dev-setup …\n")
        self._dev_log_toggle.show()
        _set_log_panel(self._dev_log_toggle, self._dev_log, False)
        self._dev_progress.show()
        self._dev_status_lbl.setText("Setting up dev environment…")
        self._dev_status_lbl.setObjectName("subheading")
        self._dev_status_lbl.show()
        _restyle(self._dev_status_lbl)
        self._dev_worker = Worker(_SETUP_DEV_BOX_CMD)
        self._dev_worker.line.connect(self._dev_on_line)
        self._dev_worker.done.connect(self._dev_on_done)
        self._dev_worker.start()

    def _dev_on_line(self, ln: str):
        self._dev_log.append(ln)
        self._dev_log.ensureCursorVisible()

    def _dev_on_done(self, code: int):
        self._dev_progress.hide()
        _finish_worker(self, attr="_dev_worker")
        self._dev_setup_btn.setEnabled(True)
        if code == 0:
            self._dev_status_lbl.setText("Dev environment ready.")
            self._dev_status_lbl.setObjectName("status-ok")
            self._dev_log.append("\nDone. Launch VS Code from the app menu, or click 'Enter Dev Box'.")
        else:
            self._dev_status_lbl.setText(f"Setup failed (exit code {code}).")
            self._dev_status_lbl.setObjectName("status-err")
            _set_log_panel(self._dev_log_toggle, self._dev_log, True)
        _restyle(self._dev_status_lbl)

    def _dev_confirm_delete(self):
        if self._dev_worker and self._dev_worker.isRunning():
            return
        if not _is_distrobox_container("kyth-dev"):
            QMessageBox.information(
                self, "Nothing to Delete",
                "The kyth-dev container does not exist.",
            )
            return

        first = QMessageBox.warning(
            self,
            "Delete Dev Environment?",
            "This will permanently delete the kyth-dev distrobox container.\n\n"
            "Everything inside the container will be lost:\n"
            "  •  All installed packages (git, just, podman, ripgrep, etc.)\n"
            "  •  Any tools you installed manually inside the container\n"
            "  •  Container-level configuration and state\n\n"
            "Your home directory is NOT affected — source code, dotfiles,\n"
            "and projects remain untouched.\n\n"
            "You can recreate it at any time with 'Set Up Dev Environment'.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if first != QMessageBox.StandardButton.Ok:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Confirm Permanent Deletion")
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setSpacing(12)
        dlg_layout.setContentsMargins(20, 20, 20, 20)

        warn_lbl = QLabel("Are you absolutely sure?")
        warn_lbl.setStyleSheet("color: #f7768e; font-size: 14px; font-weight: 700;")
        dlg_layout.addWidget(warn_lbl)

        detail = QLabel(
            "The kyth-dev container and every package inside it will be\n"
            "permanently removed. This cannot be undone.\n\n"
            "Type  DELETE  below to confirm:"
        )
        detail.setWordWrap(True)
        dlg_layout.addWidget(detail)

        confirm_edit = QLineEdit()
        confirm_edit.setPlaceholderText("DELETE")
        dlg_layout.addWidget(confirm_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Delete Forever")
        ok_btn.setObjectName("danger")
        ok_btn.setEnabled(False)
        _restyle(ok_btn)
        confirm_edit.textChanged.connect(
            lambda t: ok_btn.setEnabled(t.strip() == "DELETE")
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        dlg_layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._dev_run_delete()

    def _dev_run_delete(self):
        self._dev_setup_btn.setEnabled(False)
        self._dev_enter_btn.setEnabled(False)
        self._dev_delete_btn.setEnabled(False)
        self._dev_log.clear()
        self._dev_log.append("→ distrobox rm --force kyth-dev\n")
        self._dev_log_toggle.show()
        _set_log_panel(self._dev_log_toggle, self._dev_log, False)
        self._dev_progress.show()
        self._dev_status_lbl.setText("Deleting dev environment…")
        self._dev_status_lbl.setObjectName("subheading")
        self._dev_status_lbl.show()
        _restyle(self._dev_status_lbl)
        self._dev_worker = Worker(["distrobox", "rm", "--force", "kyth-dev"])
        self._dev_worker.line.connect(self._dev_on_line)
        self._dev_worker.done.connect(self._dev_on_delete_done)
        self._dev_worker.start()

    def _dev_on_delete_done(self, code: int):
        self._dev_progress.hide()
        _finish_worker(self, attr="_dev_worker")
        self._dev_setup_btn.setEnabled(True)
        self._dev_enter_btn.setEnabled(True)
        self._dev_delete_btn.setEnabled(True)
        if code == 0:
            self._dev_status_lbl.setText("Dev environment deleted.")
            self._dev_status_lbl.setObjectName("status-ok")
            self._dev_log.append("\nDone. Click 'Set Up Dev Environment' to recreate it.")
        else:
            self._dev_status_lbl.setText(f"Deletion failed (exit {code}).")
            self._dev_status_lbl.setObjectName("status-err")
            _set_log_panel(self._dev_log_toggle, self._dev_log, True)
        _restyle(self._dev_status_lbl)

    def _dev_enter_dev_box(self):
        if not _is_distrobox_container("kyth-dev"):
            QMessageBox.information(
                self,
                "Dev Box Not Found",
                "Create the KythOS development box first.",
            )
            return
        terminal = None
        for cmd in (["konsole"], ["xdg-terminal-exec"], ["xterm"]):
            if shutil.which(cmd[0]):
                terminal = cmd[0]
                break
        if terminal is None:
            QMessageBox.warning(self, "Terminal not found",
                                "Could not find a terminal emulator to open.")
            return
        if terminal == "konsole":
            subprocess.Popen(["konsole", "-e", "distrobox", "enter", "kyth-dev"])
        else:
            subprocess.Popen([terminal, "--", "distrobox", "enter", "kyth-dev"])

    def _ai_buttons(self):
        return tuple(
            btn for btn in (
                getattr(self, "_ai_setup_btn", None),
                getattr(self, "_ai_status_btn", None),
                getattr(self, "_ai_enter_btn", None),
                getattr(self, "_ai_start_btn", None),
                getattr(self, "_ai_stop_btn", None),
                getattr(self, "_ai_delete_btn", None),
            ) if btn is not None
        )

    def _ai_set_running(self, running: bool):
        for btn in self._ai_buttons():
            btn.setEnabled(not running)
        if hasattr(self, "_ai_progress"):
            self._ai_progress.setVisible(running)

    def _ai_run(self, action: str):
        if getattr(self, "_ai_worker", None) and self._ai_worker.isRunning():
            return
        if action == "remove":
            answer = QMessageBox.question(
                self,
                "Remove AI Dev Environment",
                "Remove the kyth-ai-dev Distrobox? Downloaded models in your home directory will be kept.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._ai_set_running(True)
        self._ai_status_lbl.setObjectName("status-muted")
        self._ai_status_lbl.setText(f"Running {action}...")
        self._ai_log.clear()
        command = ["/usr/bin/kyth-ai-dev", action]
        self._ai_worker = Worker(command)
        self._ai_worker.line.connect(self._ai_on_line)
        self._ai_worker.done.connect(lambda code: self._ai_on_done(action, code))
        self._ai_worker.start()

    def _ai_on_line(self, line: str):
        self._ai_log.append(line)

    def _ai_on_done(self, action: str, code: int):
        self._ai_set_running(False)
        ok = code == 0
        self._ai_status_lbl.setObjectName("status-ok" if ok else "status-err")
        if ok:
            labels = {
                "setup": "AI developer environment is ready.",
                "status": "Status check finished.",
                "start": "Local model service started.",
                "stop": "Local model service stopped.",
                "remove": "AI developer environment removed; models were left in your home directory.",
            }
            self._ai_status_lbl.setText(labels.get(action, "Finished."))
        else:
            self._ai_status_lbl.setText(f"{action.capitalize()} failed (exit code {code}).")
        _restyle(self._ai_status_lbl)

    def _ai_enter_box(self):
        try:
            subprocess.Popen(["konsole", "-e", "/usr/bin/kyth-ai-dev", "enter"])
        except Exception as exc:
            QMessageBox.warning(self, "AI Dev Environment", f"Could not open the AI dev shell:\n{exc}")
