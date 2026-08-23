"""Qt worker for submitting GitHub issues (feedback)."""
from __future__ import annotations

import json
from urllib.request import Request, urlopen

from ...qt import Signal
from ..runtime import TrackedThread

_GITHUB_REPO = "kyth-os/kyth"


class GitHubIssueWorker(TrackedThread):
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
        except (OSError, ValueError, RuntimeError) as exc:
            self.failed.emit(str(exc))