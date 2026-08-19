"""Cross-process update status shared by the watcher, notifier, and System Hub."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_UPDATE_STATUS_PATH = Path("/var/lib/kyth/update-watcher-status.json")


@dataclass(frozen=True, slots=True)
class UpdateSnapshot:
    result: str = ""
    reason: str | None = None
    output: str = ""
    ts: int = 0
    flatpak_updates: int = 0
    image_ref: str = ""
    booted_digest: str = ""
    staged_digest: str = ""
    remote_digest: str = ""

    @property
    def system_state(self) -> str:
        if self.staged_digest or self.result == "upgraded" or (
            self.reason and "already staged" in self.reason.lower()
        ):
            return "staged"
        if self.booted_digest and self.remote_digest:
            return "uptodate" if self.booted_digest == self.remote_digest else "available"
        if self.result == "no_change" and "already up to date" in self.output.lower():
            return "uptodate"
        return "unknown"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: object) -> "UpdateSnapshot":
        if not isinstance(data, dict):
            return cls()
        fields = cls.__dataclass_fields__
        values = {key: data[key] for key in fields if key in data}
        try:
            return cls(**values)
        except (TypeError, ValueError):
            return cls()


def read_update_snapshot(
    path: str | Path = DEFAULT_UPDATE_STATUS_PATH,
    *,
    max_age: float | None = None,
    now: float | None = None,
) -> UpdateSnapshot | None:
    try:
        snapshot = UpdateSnapshot.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if max_age is not None:
        current = time.time() if now is None else now
        if snapshot.ts <= 0 or current - snapshot.ts > max_age:
            return None
    return snapshot


def write_update_snapshot(
    snapshot: UpdateSnapshot,
    path: str | Path = DEFAULT_UPDATE_STATUS_PATH,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent, text=True
    )
    try:
        # The system watcher writes as root; desktop consumers read as the
        # logged-in user. Preserve the legacy status file's non-secret 0644
        # permissions even though mkstemp intentionally starts at 0600.
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot.to_dict(), handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except (OSError, ValueError) as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise