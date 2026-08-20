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
    avg_latency_ms: float | None = None
    p99_latency_ms: float | None = None

    @property
    def date_label(self) -> str:
        if not self.started_at:
            return "—"
        try:
            return datetime.fromtimestamp(self.started_at).strftime("%b %d %H:%M")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
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

    @property
    def latency_label(self) -> str:
        if self.avg_latency_ms is None:
            return "—"
        p99 = self.p99_latency_ms or self.avg_latency_ms
        return f"{self.avg_latency_ms:.1f} / {p99:.1f} ms p99"


def latency_ledger_path() -> Path:
    return Path("/var/cache/kyth/telem/latency.jsonl")


def _load_latency_map() -> dict[float, tuple[float, float]]:
    # key: started_at → (avg_ms, p99_ms) best-effort, no cloud
    m: dict[float, tuple[float, float]] = {}
    p = latency_ledger_path()
    try:
        if not p.exists():
            return m
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            import json

            obj = json.loads(line)
            sa = float(obj.get("started_at", 0))
            if sa:
                m[sa] = (float(obj.get("avg_ms", 0)), float(obj.get("p99_ms", 0)))
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return m
    return m


def recent_sessions(limit: int = 15) -> list[SessionRow]:
    db_path = telemetry_db_path()
    if not db_path.exists():
        return []
    latency_map = _load_latency_map()
    try:
        conn = sqlite3.connect(str(db_path), timeout=3)
        try:
            # Try extended schema first, fallback to legacy
            try:
                rows = conn.execute(
                    "SELECT game_name, started_at, duration_s, avg_fps, p1_low_fps, "
                    "stutter_count, scheduler, avg_latency_ms, p99_latency_ms FROM sessions "
                    "ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                has_lat = True
            except Exception:  # noqa: BLE001 -- broad: DB schema fallback must catch sqlite3.OperationalError
                rows = conn.execute(
                    "SELECT game_name, started_at, duration_s, avg_fps, p1_low_fps, "
                    "stutter_count, scheduler FROM sessions "
                    "ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                has_lat = False
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 -- broad: DB connection/query must catch sqlite3.Error
        return []

    sessions: list[SessionRow] = []
    for r in rows:
        if has_lat:
            game, started, duration, avg_fps, p1, stutters, sched, avg_lat, p99_lat = r
        else:
            game, started, duration, avg_fps, p1, stutters, sched = r
            avg_lat = p99_lat = None
            # fallback to ledger file if DB lacks columns
            if started is not None and started in latency_map:
                avg_lat, p99_lat = latency_map[started]
        sessions.append(
            SessionRow(
                game_name=game or "Unknown",
                started_at=started,
                duration_s=duration,
                avg_fps=avg_fps,
                p1_low_fps=p1,
                stutter_count=int(stutters or 0),
                scheduler=sched or "",
                avg_latency_ms=avg_lat,
                p99_latency_ms=p99_lat,
            )
        )
    return sessions
