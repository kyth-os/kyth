"""Telemetry database management and query utilities shared across KythOS."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def telemetry_db_path() -> Path:
    return Path.home() / ".local" / "share" / "kyth" / "telemetry.db"


@dataclass(frozen=True)
class SessionRow:
    game_name: str
    started_at: float | None
    duration_s: float | None
    avg_fps: float | None
    p1_low_fps: float | None
    stutter_count: int
    scheduler: str

    @property
    def date_label(self) -> str:
        if not self.started_at:
            return "—"
        try:
            return datetime.fromtimestamp(self.started_at).strftime("%b %d %H:%M")
        except Exception:
            return "—"

    @property
    def duration_label(self) -> str:
        if not self.duration_s:
            return "—"
        m, s = divmod(int(self.duration_s), 60)
        return f"{m}m {s:02d}s"

    @property
    def fps_label(self) -> str:
        if not self.avg_fps:
            return "—"
        p1 = self.p1_low_fps or 0.0
        return f"{self.avg_fps:.0f} / {p1:.0f} 1%"


def recent_sessions(limit: int = 15) -> list[SessionRow]:
    db_path = telemetry_db_path()
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path), timeout=3) as conn:
            rows = conn.execute(
                "SELECT game_name, started_at, duration_s, avg_fps, p1_low_fps, "
                "stutter_count, scheduler FROM sessions "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    except Exception:
        return []

    sessions: list[SessionRow] = []
    for game, started, duration, avg_fps, p1, stutters, sched in rows:
        sessions.append(
            SessionRow(
                game_name=game or "Unknown",
                started_at=started,
                duration_s=duration,
                avg_fps=avg_fps,
                p1_low_fps=p1,
                stutter_count=int(stutters or 0),
                scheduler=sched or "",
            )
        )
    return sessions
