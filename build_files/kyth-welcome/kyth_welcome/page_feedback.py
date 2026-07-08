import os
import json
import subprocess
from urllib.request import Request, urlopen

# __KYTH_GENERATED_IMPORTS__
from .core_base import (
    _IS_LIVE, _release_worker_when_finished, _restyle,
)
from .services.diagnostics import _command_stdout
from .services.gaming import TrackedThread
from .services.updates import (
    _bootc_image_digest, _current_branch,
)
from .qt import (  # noqa: E501
    QButtonGroup, QCheckBox, QDesktopServices, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QTextEdit, QThread, QUrl, Signal,
)
from .widgets import (  # noqa: E501
    Page, _make_card,
)

# ── Windows NTFS library detection ───────────────────────────────────────────

def _probe_windows_partitions() -> list[dict]:
    """Scan for NTFS partitions, check dirty/hibernated state, find Steam dirs.
    Returns list of dicts safe to call from a non-main thread."""
    import json as _json
    try:
        raw = subprocess.check_output(
            ["lsblk", "--json", "-o", "NAME,FSTYPE,LABEL,MOUNTPOINTS,SIZE,PATH"],
            text=True, timeout=8,
        )
        data = _json.loads(raw)
    except Exception:
        return []

    ntfs_devs: list[dict] = []
    locked_devs: list[dict] = []

    def _walk(nodes: list) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            fstype = (node.get("fstype") or "").lower()
            if fstype == "ntfs":
                ntfs_devs.append(node)
            elif fstype == "bitlocker" and not node.get("children"):
                # Locked BitLocker partition. Once unlocked, the cleartext NTFS
                # mapper device shows up as a child and is collected above —
                # Windows 11 enables Device Encryption by default, so most
                # modern Windows drives arrive in this state.
                locked_devs.append(node)
            _walk(node.get("children") or [])

    _walk(data.get("blockdevices", []))

    results: list[dict] = []
    for dev in locked_devs:
        name = dev.get("name") or ""
        path = dev.get("path") or (f"/dev/{name}" if name else "")
        if not path:
            continue
        results.append({
            "device":        path,
            "label":         dev.get("label") or "",
            "size":          dev.get("size") or "",
            "mountpoint":    "",
            "is_bitlocker":  True,
            "is_dirty":      False,
            "is_hibernated": False,
            "steam_paths":   [],
            "user_profiles": [],
        })
    for dev in ntfs_devs:
        name = dev.get("name") or ""
        path = dev.get("path") or (f"/dev/{name}" if name else "")
        if not path:
            continue
        label = dev.get("label") or ""
        size  = dev.get("size") or ""

        # Dirty/hibernated check via ntfsfix --no-action (reads; never writes)
        is_dirty = False
        is_hibernated = False
        try:
            r = subprocess.run(
                ["ntfsfix", "--no-action", path],
                capture_output=True, text=True, timeout=8,
            )
            combined = (r.stdout + r.stderr).lower()
            if "unclean" in combined or "dirty" in combined:
                is_dirty = True
        except FileNotFoundError:
            # ntfsfix not present — fall back to mount-attempt heuristic below
            pass
        except Exception:
            pass

        # Resolve mountpoint from lsblk JSON
        raw_mounts: list = dev.get("mountpoints") or []
        mountpoint: str = next((m for m in raw_mounts if m and m != "[SWAP]"), "")

        steam_paths: list[str] = []
        user_profiles: list[dict] = []
        windows_root = False
        if mountpoint:
            windows_root = os.path.isdir(os.path.join(mountpoint, "Windows"))
            hiberfil = os.path.join(mountpoint, "hiberfil.sys")
            if os.path.exists(hiberfil):
                is_hibernated = True
                is_dirty = True
            for candidate in (
                "Program Files (x86)/Steam",
                "Program Files/Steam",
                "SteamLibrary",
            ):
                full = os.path.join(mountpoint, candidate)
                if os.path.isdir(full):
                    steam_paths.append(full)
            users_dir = os.path.join(mountpoint, "Users")
            if os.path.isdir(users_dir):
                for entry in sorted(os.listdir(users_dir)):
                    if entry.lower() in ("all users", "default", "default user", "public", "desktop.ini"):
                        continue
                    profile = os.path.join(users_dir, entry)
                    if not os.path.isdir(profile):
                        continue
                    folders = [
                        name for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", "Saved Games")
                        if os.path.isdir(os.path.join(profile, name))
                    ]
                    if folders:
                        user_profiles.append({
                            "name": entry,
                            "path": profile,
                            "folders": folders,
                        })

        results.append({
            "device":       path,
            "label":        label,
            "size":         size,
            "mountpoint":   mountpoint,
            "is_dirty":     is_dirty,
            "is_hibernated": is_hibernated,
            "windows_root": windows_root,
            "steam_paths":  steam_paths,
            "user_profiles": user_profiles,
        })

    return results


# ── Page: Feedback ────────────────────────────────────────────────────────────
_GITHUB_FEEDBACK_TOKEN_PATH = "/etc/kyth-github-feedback-token"
_GITHUB_REPO = "mrtrick37/kyth"


def _collect_system_info() -> str:
    lines = []
    kernel = _command_stdout(["uname", "-r"], timeout=5) or "unknown"
    lines.append(f"**Kernel:** {kernel}")
    branch = _current_branch() or "unknown"
    lines.append(f"**Channel:** {branch}")
    digest_info = _bootc_image_digest("booted")
    if digest_info:
        lines.append(f"**Image digest:** `{digest_info[1][:16]}`")
    gpu = _command_stdout(
        ["bash", "-c", "lspci -mm 2>/dev/null | grep -iE 'vga|3d|display' | head -3"],
        timeout=5,
    ).strip() or "unknown"
    lines.append(f"**GPU:**\n```\n{gpu}\n```")
    cpu = _command_stdout(
        ["bash", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2"],
        timeout=5,
    ).strip() or "unknown"
    lines.append(f"**CPU:** {cpu}")
    if _IS_LIVE:
        lines.append("**Session:** Live ISO")
    return "\n".join(lines)


class _GitHubIssueWorker(TrackedThread):
    success = Signal(str)
    failed = Signal(str)

    def __init__(self, title: str, body: str, labels: list, token: str):
        super().__init__()
        self._title = title
        self._body = body
        self._labels = labels
        self._token = token

    def run(self):
        payload = json.dumps({
            "title": self._title,
            "body": self._body,
            "labels": self._labels,
        }).encode("utf-8")
        req = Request(
            f"https://api.github.com/repos/{_GITHUB_REPO}/issues",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "KythOS-Feedback/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.success.emit(data.get("html_url", ""))
        except Exception as exc:
            self.failed.emit(str(exc))


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
        note.setStyleSheet("color: #888888;")
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
        body = self._build_body()

        token = ""
        try:
            with open(_GITHUB_FEEDBACK_TOKEN_PATH) as _f:
                token = _f.read().strip()
        except OSError:
            pass

        if token:
            self._submit_btn.setEnabled(False)
            self._set_status("Submitting…")
            self._worker = _GitHubIssueWorker(title, body, labels, token)
            self._worker.success.connect(self._on_success)
            self._worker.failed.connect(self._on_fail)
            _release_worker_when_finished(self, "_worker", self._worker)
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
        _restyle(self._status_lbl)
