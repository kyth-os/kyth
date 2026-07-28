"""Streaming command execution with progress and network-stall tracking."""

from __future__ import annotations

import codecs
import os
import select
import subprocess  # nosec B404 # nosemgrep
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence

from kyth_shared import NetStatsTracker, parse_size_bytes
from .runner import spawn_command


LogFn = Callable[[str], None]
ProgressFn = Callable[[int], None]
EventFn = Callable[[dict], None]
CounterFn = Callable[[], int]


class StreamingCommandRunner:
    """Run a command while translating its output into progress events.

    Runtime inputs that made the old installer helper hard to test—network
    counters, time, and event publication—are explicit dependencies here.
    """

    def __init__(
        self,
        *,
        rx_bytes: CounterFn,
        publish: EventFn,
        monotonic: Callable[[], float] = time.monotonic,
        monitor_interval: float = 1.0,
    ) -> None:
        self._rx_bytes = rx_bytes
        self._publish = publish
        self._monotonic = monotonic
        self._monitor_interval = monitor_interval

    def run(
        self,
        command: Sequence[str],
        pct_start: int,
        pct_end: int,
        log: LogFn,
        progress: ProgressFn,
        *,
        stall_timeout: int = 600,
        absolute_timeout: int | None = 3600,
        error_factory: Callable[[int, list[str], Sequence[str]], Exception] | None = None,
        input: str | None = None,
    ) -> None:
        argv = list(command)
        log(f"$ {' '.join(argv)}")
        proc = spawn_command(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if input is not None else None, bufsize=0,
        )
        if proc.stdout is None:
            proc.kill()
            proc.wait()
            raise RuntimeError("Could not capture installer command output.")

        if input is not None:
            # Short, fixed-size confirmation answers only (e.g. "y\n") — small
            # enough to never block on pipe buffer capacity, so writing before
            # the read loop starts below cannot deadlock.
            proc.stdin.write(input.encode())
            proc.stdin.close()

        monitor_stop = threading.Event()
        recent_output: deque[str] = deque(maxlen=30)
        output_state = {"total": 0, "rx_start": 0}
        tracker: NetStatsTracker | None = None

        def net_monitor() -> None:
            nonlocal tracker
            while not monitor_stop.wait(self._monitor_interval):
                total = output_state["total"]
                if total <= 0:
                    tracker = None
                    continue
                if tracker is None:
                    tracker = NetStatsTracker(total, output_state["rx_start"])
                stats = tracker.tick(self._rx_bytes())
                frac = min(0.95, stats["downloaded"] / total)
                progress(int(pct_start + frac * (pct_end - pct_start)))
                self._publish({"type": "stats", **stats})

        monitor_thread = threading.Thread(target=net_monitor, daemon=True)
        monitor_thread.start()

        started = self._monotonic()
        last_activity = started
        last_rx = self._rx_bytes()
        pending = ""
        last_line: str | None = None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        def emit_line(line: str) -> None:
            nonlocal last_line
            stripped = line.strip()
            if not stripped or stripped == last_line:
                return
            last_line = stripped
            log(stripped)
            recent_output.append(stripped)
            if "layers needed:" not in stripped:
                return
            try:
                details = stripped.split("layers needed:", 1)[1]
                size_str = details.split("(", 1)[1].rstrip(")") if "(" in details else ""
                output_state["total"] = parse_size_bytes(size_str)
                output_state["rx_start"] = self._rx_bytes()
            except (IndexError, TypeError, ValueError):
                # bootc output is advisory; malformed progress must not abort
                # an otherwise healthy installation command.
                output_state["total"] = 0

        def consume_output(text: str, final: bool = False) -> None:
            nonlocal pending
            pending += text
            while True:
                indexes = [idx for idx in (pending.find("\n"), pending.find("\r")) if idx >= 0]
                if not indexes:
                    break
                split_at = min(indexes)
                emit_line(pending[:split_at])
                pending = pending[split_at + 1:]
            if final and pending:
                emit_line(pending)
                pending = ""

        try:
            fd = proc.stdout.fileno()
            while True:
                ready, _, _ = select.select([fd], [], [], 1)
                if ready:
                    chunk = os.read(fd, 64 * 1024)
                    if not chunk:
                        break
                    last_activity = self._monotonic()
                    consume_output(decoder.decode(chunk))

                now = self._monotonic()
                rx_now = self._rx_bytes()
                if rx_now > last_rx:
                    last_rx = rx_now
                    last_activity = now
                if absolute_timeout is not None and now - started > absolute_timeout:
                    raise RuntimeError(
                        f"Command exceeded absolute timeout of {absolute_timeout // 60} min"
                    )
                if now - last_activity > stall_timeout:
                    raise RuntimeError(
                        "Command timed out after "
                        f"{stall_timeout // 60} min with no output or network traffic"
                    )

            consume_output(decoder.decode(b"", final=True), final=True)
            proc.wait()
        except Exception:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            raise
        finally:
            monitor_stop.set()
            monitor_thread.join(timeout=2)
            proc.stdout.close()

        if proc.returncode != 0:
            lines = list(recent_output)
            if error_factory is not None:
                raise error_factory(proc.returncode, lines, argv)
            detail = "\n".join(lines[-10:]) or "No command output was captured."
            raise RuntimeError(
                f"Command failed (exit {proc.returncode}):\n  {' '.join(argv)}\n\n{detail}"
            )
        progress(pct_end)
