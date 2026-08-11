from kyth_shared.system.gpu import lspci_gpu_lines

# __KYTH_GENERATED_IMPORTS__
from .core_base import IS_LIVE, restyle
from .services.bootc import bootc_image_digest, current_branch
from .services.runtime import release_worker_when_finished
from .services.diagnostics import command_stdout
from .services.workers import GitHubIssueWorker
from .qt import (
    QButtonGroup, QCheckBox, QDesktopServices, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QTextEdit, QUrl,
)
from .widgets import (
    Page, _make_card,
)

# ── Page: Feedback ────────────────────────────────────────────────────────────
_GITHUB_FEEDBACK_TOKEN_PATH = "/etc/kyth-github-feedback-token"
_GITHUB_REPO = "mrtrick37/kyth"


def _scrub_logs(text: str) -> str:
    """Arch #16: central scrub via kyth_shared.diagnostics_scrub."""
    from kyth_shared.diagnostics_scrub import scrub_logs as _central

    return _central(text)


def _collect_system_info() -> str:
    lines = []
    kernel = command_stdout(["uname", "-r"], timeout=5) or "unknown"
    lines.append(f"**Kernel:** {kernel}")
    branch = current_branch() or "unknown"
    lines.append(f"**Channel:** {branch}")
    digest_info = bootc_image_digest("booted")
    if digest_info:
        lines.append(f"**Image digest:** `{digest_info[1][:16]}`")
    gpu = "\n".join(lspci_gpu_lines()[:3]) or "unknown"
    lines.append(f"**GPU:**\n```\n{gpu}\n```")
    cpu = command_stdout(
        ["bash", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2"],
        timeout=5,
    ).strip() or "unknown"
    lines.append(f"**CPU:** {cpu}")
    if IS_LIVE:
        lines.append("**Session:** Live ISO")
    return "\n".join(lines)



class FeedbackPage(Page):
    def __init__(self):
        super().__init__()
        self._worker = None

        self._page_header(
            "Advanced",
            "Feedback",
            "Report a bug or request a feature. Your report goes directly to the KythOS issue tracker.",
        )

        # Type selector
        type_card, type_layout = _make_card()
        type_title = QLabel("What would you like to submit?")
        type_title.setObjectName("card-title")
        type_layout.addWidget(type_title)
        type_row = QHBoxLayout()
        type_row.setSpacing(12)
        self._bug_btn = QRadioButton("Bug Report")
        self._feature_btn = QRadioButton("Feature Request")
        self._bug_btn.setChecked(True)
        self._type_group = QButtonGroup(self)
        self._type_group.addButton(self._bug_btn)
        self._type_group.addButton(self._feature_btn)
        type_row.addWidget(self._bug_btn)
        type_row.addWidget(self._feature_btn)
        type_row.addStretch()
        type_layout.addLayout(type_row)
        self._add(type_card)

        # Form
        form_card, form_layout = _make_card()
        title_lbl = QLabel("Title")
        title_lbl.setObjectName("card-title")
        form_layout.addWidget(title_lbl)
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Short summary of the issue or request")
        form_layout.addWidget(self._title_edit)
        self._desc_lbl = QLabel("Description")
        self._desc_lbl.setObjectName("card-title")
        form_layout.addWidget(self._desc_lbl)
        self._desc_edit = QTextEdit()
        self._desc_edit.document().setMaximumBlockCount(5000)
        self._desc_edit.setPlaceholderText(
            "Steps to reproduce, what you expected, and what actually happened"
        )
        self._desc_edit.setMinimumHeight(140)
        self._desc_edit.setMaximumHeight(240)
        form_layout.addWidget(self._desc_edit)
        self._sysinfo_check = QCheckBox(
            "Include system information (kernel, GPU, channel, image digest)"
        )
        self._sysinfo_check.setChecked(True)
        form_layout.addWidget(self._sysinfo_check)
        self._add(form_card)

        # Submit area
        action_card, action_layout = _make_card()
        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        self._submit_btn = QPushButton("Submit")
        self._submit_btn.setObjectName("primary")
        self._submit_btn.clicked.connect(self._submit)
        action_row.addWidget(self._submit_btn)
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("card-copy")
        self._status_lbl.setWordWrap(True)
        action_row.addWidget(self._status_lbl, 1)
        action_layout.addLayout(action_row)
        note = QLabel(
            "Issues are filed publicly on GitHub. Do not include passwords, tokens, or other secrets."
        )
        note.setObjectName("card-copy")
        note.setWordWrap(True)
        action_layout.addWidget(note)
        self._add(action_card)

        self._stretch()
        self._type_group.buttonClicked.connect(self._update_placeholder)

    def _update_placeholder(self, _btn=None):
        if self._bug_btn.isChecked():
            self._desc_edit.setPlaceholderText(
                "Steps to reproduce, what you expected, and what actually happened"
            )
        else:
            self._desc_edit.setPlaceholderText(
                "Describe the feature you'd like and why it would be useful"
            )

    def _build_body(self) -> str:
        desc = self._desc_edit.toPlainText().strip() or "_No description provided._"
        if self._bug_btn.isChecked():
            parts = [f"## Description\n\n{desc}"]
        else:
            parts = [f"## Feature Request\n\n{desc}"]
        if self._sysinfo_check.isChecked():
            parts.append(f"## System Information\n\n{_collect_system_info()}")
        return "\n\n".join(parts)

    def _submit(self):
        title = self._title_edit.text().strip()
        if not title:
            self._set_status("Please enter a title before submitting.", error=True)
            return

        labels = ["bug"] if self._bug_btn.isChecked() else ["enhancement"]
        body = _scrub_logs(self._build_body())

        token = ""
        try:
            with open(_GITHUB_FEEDBACK_TOKEN_PATH) as _f:
                token = _f.read().strip()
        except OSError:
            pass

        if token:
            self._submit_btn.setEnabled(False)
            self._set_status("Submitting…")
            self._worker = GitHubIssueWorker(title, body, labels, token)
            self._worker.success.connect(self._on_success)
            self._worker.failed.connect(self._on_fail)
            release_worker_when_finished(self, "_worker", self._worker)
            self._worker.start()
        else:
            from urllib.parse import quote as _quote
            kind = "bug" if self._bug_btn.isChecked() else "enhancement"
            url = (
                f"https://github.com/{_GITHUB_REPO}/issues/new"
                f"?labels={kind}"
                f"&title={_quote(title)}"
                f"&body={_quote(body)}"
            )
            QDesktopServices.openUrl(QUrl(url))
            self._set_status(
                "GitHub opened in your browser — review the pre-filled issue and click Submit."
            )

    def _on_success(self, url: str):
        self._submit_btn.setEnabled(True)
        self._set_status(f"Issue filed! View it at: {url}")
        self._title_edit.clear()
        self._desc_edit.clear()

    def _on_fail(self, error: str):
        self._submit_btn.setEnabled(True)
        self._set_status(f"Submission failed: {error}", error=True)

    def _set_status(self, msg: str, *, error: bool = False):
        self._status_lbl.setText(msg)
        self._status_lbl.setObjectName("status-err" if error else "card-copy")
        restyle(self._status_lbl)
