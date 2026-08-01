"""Repository specification and management helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "repos.json"


@dataclass
class RepoSpec:
    name: str
    description: str
    baseurl: str
    enabled: bool = True
    type: str = "rpm"
    repo_gpgcheck: bool = True
    gpgcheck: bool = False
    gpgkey: str = ""

    def render_yum_repo(self) -> str:
        lines = [
            f"[{self.name}]",
            f"name={self.description}",
            f"baseurl={self.baseurl}",
            f"enabled={1 if self.enabled else 0}",
            f"type={self.type}",
            f"repo_gpgcheck={1 if self.repo_gpgcheck else 0}",
            f"gpgcheck={1 if self.gpgcheck else 0}",
        ]
        if self.gpgkey:
            lines.append(f"gpgkey={self.gpgkey}")
        return "\n".join(lines) + "\n"


GAMING_COPRS = [
    "ublue-os/bazzite",
    "ublue-os/bazzite-multilib",
    "ublue-os/staging",
    "ublue-os/packages",
    "ublue-os/obs-vkcapture",
    "lukenukem/asus-linux",
    "ycollet/audinux",
]


def load_repo_specs(config_file: Path = CONFIG_PATH) -> list[RepoSpec]:
    """Load third-party repository definitions from JSON config."""
    if not config_file.is_file():
        return []
    data = json.loads(config_file.read_text(encoding="utf-8"))
    return [RepoSpec(**item) for item in data]

