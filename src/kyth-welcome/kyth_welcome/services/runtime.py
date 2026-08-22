"""Qt worker threads shared by System Hub pages and service workers.

Domain services should not own thread base classes — import them from here.
"""
from __future__ import annotations

import atexit
import functools
import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, TypeVar
from weakref import ref

from ..qt import QThread, Signal
from kyth_shared import NetStatsTracker, get_rx_bytes
from kyth_shared.commands import (
    APPLICATION_RUNNER,
    CommandSpec,
    EnvironmentPolicy,
    command_spec,
)
from .process import invalidate_probe_caches, parse_size_bytes

_logger = logging.getLogger(__name__)

@dataclass
class _TaskRecord:
    thread: QThread
    task_id: str
    owner_ref: object | None = None
    attr: str | None = None


class TaskSupervisor:
    """Single owner for Hub background-task lifetime and shutdown policy."""

    def __init__(self) -> None:
        self._records: dict[QThread, _TaskRecord] = {}

    def register(self, thread: QThread, *, task_id: str | None = None) -> None:
        self._records[thread] = _TaskRecord(thread, task_id or type(thread).__name__)
        thread.finished.connect(lambda: self._records.pop(thread, None))

    def attach(self, thread: QThread, owner: object, attr: str, *, task_id: str | None = None) -> None:
        record = self._records.setdefault(thread, _TaskRecord(thread, task_id or attr))
        record.task_id = task_id or record.task_id
        try:
            record.owner_ref = ref(owner)
        except TypeError:
            record.owner_ref = lambda: owner
        record.attr = attr

    def running(self) -> list[QThread]:
        alive: list[QThread] = []
        for record in self._records.values():
            try:
                if record.thread.isRunning():
                    alive.append(record.thread)
            except RuntimeError:
                continue
        return alive

    def has_blocking_tasks(self) -> bool:
        for thread in self.running():
            try:
                if getattr(thread, "BLOCKS_CLOSE", False):
                    return True
            except RuntimeError:
                continue
        return False

    def finish_owner_task(self, owner: object, attr: str) -> None:
        try:
            worker = getattr(owner, attr, None)
        except RuntimeError:
            return
        if worker is None:
            return
        # Avoid blocking the GUI thread: if the worker already finished,
        # clean up synchronously; otherwise defer cleanup to the finished
        # signal (non-blocking). Called from `done` slots where the worker
        # has just emitted `done` but may still be unwinding.
        def _cleanup():
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
            try:
                if getattr(owner, attr, None) is worker:
                    setattr(owner, attr, None)
            except RuntimeError:
                pass
            self._records.pop(worker, None)

        # Connect BEFORE checking isFinished(): if the worker finishes and
        # emits `finished` in the gap between an isFinished() check and
        # connecting a handler to catch it, that emission is missed forever
        # (Qt doesn't replay signals to late subscribers) and this task's
        # record and owner reference leak permanently. Connecting first
        # closes that window — any emission from this point on is
        # guaranteed delivered to _cleanup(). The isFinished() check below
        # then only has to catch the case where the worker had ALREADY
        # finished (and its signal already delivered to nobody) before we
        # even connected; every step in _cleanup() is a no-op on a repeat
        # call, so it's safe if both the signal and this check end up
        # invoking it.
        try:
            worker.finished.connect(_cleanup)
        except RuntimeError:
            # Worker already deleted — nothing left to defer to.
            _cleanup()
            return
        try:
            finished = worker.isFinished()
        except RuntimeError:
            _cleanup()
            return
        if finished:
            _cleanup()

    def release_when_finished(self, owner: object, attr: str, worker: QThread) -> None:
        self.attach(worker, owner, attr)

        def _release() -> None:
            try:
                if getattr(owner, attr, None) is worker:
                    setattr(owner, attr, None)
            except RuntimeError:
                pass
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
            self._records.pop(worker, None)

        try:
            worker.finished.connect(_release)
        except RuntimeError:
            _release()

    def shutdown(self, timeout_ms: int = 15000) -> None:
        for thread in list(self._records):
            try:
                stop = getattr(thread, "cancel", None) or getattr(thread, "stop", None)
            except RuntimeError:
                # Wrapped C++ object already deleted (atexit after QApplication teardown)
                continue
            if callable(stop):
                try:
                    stop()
                except RuntimeError:
                    continue
                except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                    _logger.debug("TaskSupervisor.shutdown: stop() on %r failed", thread, exc_info=True)
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            try:
                running = self.running()
            except RuntimeError:
                break
            if not running:
                break
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break
            slice_ms = max(1, min(250, remaining_ms))
            for thread in running:
                try:
                    thread.wait(slice_ms)
                except RuntimeError:
                    continue
                if time.monotonic() >= deadline:
                    break


TASK_SUPERVISOR = TaskSupervisor()


class TrackedThread(QThread):
    """QThread that stays registered (and referenced) while alive.

    Every worker in the app must subclass this: the registry both prevents a
    fire-and-forget thread from being garbage-collected mid-run and lets window
    close / app quit wait for stragglers instead of letting Python destroy a
    running QThread, which aborts the whole process.

    Subclasses that run user tasks (installs, copies, updates) set BLOCKS_CLOSE
    so the main window refuses to close mid-task; probes leave it False and are
    joined at quit by shutdown_threads.
    """

    BLOCKS_CLOSE = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        TASK_SUPERVISOR.register(self)


def running_threads() -> list[TrackedThread]:
    return TASK_SUPERVISOR.running()


def has_blocking_tasks() -> bool:
    return TASK_SUPERVISOR.has_blocking_tasks()


def shutdown_threads(timeout_ms: int = 15000) -> None:
    """Cancel and join every tracked thread. Connected to aboutToQuit so the
    interpreter never tears down a still-running QThread."""
    TASK_SUPERVISOR.shutdown(timeout_ms)


# aboutToQuit only fires when an event loop exits, so also join at interpreter
# exit — atexit runs before module teardown destroys the QThread wrappers.
# Covers embedders (tests, screenshot driver) that never call app.exec().
atexit.register(shutdown_threads)


class Worker(TrackedThread):
    BLOCKS_CLOSE = True
    CANCELLED = 130

    line = Signal(str)
    done = Signal(int)

    def __init__(self, cmd: list[str] | CommandSpec, *, input_text: str | None = None):
        super().__init__()
        if isinstance(cmd, CommandSpec):
            self._spec = cmd
        else:
            argv = tuple(cmd)
            invalidates = frozenset(
                tag for tag, binary in (("flatpak", "flatpak"), ("bootc", "bootc"))
                if binary in argv[:4]
            )
            self._spec = command_spec(
                cmd,
                name=argv[0] if argv else "command",
                timeout=None,
                environment=EnvironmentPolicy.SANITIZED,
                invalidates=invalidates,
            )
        self._cmd = self._spec.command()
        self._input_text = input_text
        self._proc: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            try:
                proc.terminate()
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                return

    def run(self):
        try:
            env = os.environ.copy()
            # When running without a TTY, sudo needs a graphical askpass helper.
            # ksshaskpass (KDE) shows a GUI password dialog and writes it to stdout.
            env.setdefault("SUDO_ASKPASS", "/usr/bin/ksshaskpass")
            # Force English locale for all subprocesses so flatpak CLI output
            # (app names in remote-ls, search, list) is always en_US, not whatever
            # the process inherited.
            env["LANG"] = "en_US.UTF-8"
            env["LC_ALL"] = "en_US.UTF-8"
            proc = APPLICATION_RUNNER.spawn(
                self._spec,
                stdin=subprocess.PIPE if self._input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
                env=env,
                cwd="/tmp",  # noqa: S108 — subprocess cwd only, nothing opened here at a predictable path
                start_new_session=True,
            )
            self._proc = proc
            if self._input_text is not None and proc.stdin is not None:
                proc.stdin.write(self._input_text)
                proc.stdin.close()
                self._input_text = None
            for ln in proc.stdout:
                self.line.emit(ln.rstrip())
            proc.wait()
            if self._cancel_requested:
                self.done.emit(self.CANCELLED)
            else:
                self.done.emit(proc.returncode)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)
        finally:
            self._proc = None
            # The command may have installed apps or staged a deployment.
            invalidate_probe_caches()
            # Targeted disk-section drops for common mutation commands.
            try:
                from .probe import (
                    invalidate_after_bootc_change,
                    invalidate_after_flatpak_change,
                )
                if "flatpak" in self._spec.invalidates:
                    invalidate_after_flatpak_change()
                if "bootc" in self._spec.invalidates:
                    invalidate_after_bootc_change()
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                _logger.debug("Worker.run: targeted disk-cache invalidation failed", exc_info=True)


class StreamingProcessWorker(TrackedThread):
    """Runs one subprocess, streaming combined stdout/stderr line-by-line.

    Emits each output line via ``line`` and the process exit code via ``done``;
    any launch/stream exception is reported as an ``Error: …`` line followed by
    ``done(1)``. ``stop()`` terminates a running process.

    Subclasses supply the command via ``command()`` and may override
    ``prepare(cmd)`` for setup (e.g. creating a destination directory or
    echoing the command) — returning ``False`` aborts the launch after the
    subclass has emitted its own ``done``.
    """

    BLOCKS_CLOSE = True
    line = Signal(str)
    done = Signal(int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._proc: subprocess.Popen[str] | None = None

    def command(self) -> list[str]:
        raise NotImplementedError

    def prepare(self, cmd: list[str]) -> bool:
        """Hook run after ``command()`` and before launch. Return False to abort."""
        return True

    def stop(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            try:
                proc.terminate()
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                return
        # In bwrap/sandbox the pgid may not match pid — ensure process dies
        try:
            time.sleep(0.05)
            if proc.poll() is None:
                proc.terminate()
            time.sleep(0.05)
            if proc.poll() is None:
                proc.kill()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
            pass

    def run(self):
        try:
            cmd = self.command()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)
            return
        if not self.prepare(cmd):
            return
        try:
            self._proc = APPLICATION_RUNNER.spawn(
                command_spec(cmd, name=cmd[0], timeout=None),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            assert self._proc.stdout
            for ln in self._proc.stdout:
                self.line.emit(ln.rstrip())
            self._proc.wait()
            self.done.emit(self._proc.returncode)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)


class DownloadMonitor(TrackedThread):
    """Polls /proc/net/dev every second to track download speed and progress."""
    # downloaded, total, speed_bps, eta_sec  (object keeps Python int — avoids 32-bit overflow)
    stats = Signal(object, object, object, object)

    def __init__(self, total_bytes: int, rx_start: int):
        super().__init__()
        self._tracker = NetStatsTracker(total_bytes, rx_start)
        # threading.Event rather than a bool flag: stop() wakes the loop
        # immediately instead of leaving callers' unbounded .wait() blocking
        # the GUI thread for up to the full 1s poll interval.
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def update_total(self, total_bytes: int) -> None:
        """Raise the expected download size when a later phase reports more."""
        self._tracker._total = total_bytes

    def run(self):
        while not self._stop_event.is_set():
            if self._stop_event.wait(1):
                break
            stats = self._tracker.tick(get_rx_bytes())
            self.stats.emit(stats["downloaded"], stats["total"], stats["speed"], stats["eta_sec"])


def stop_download_monitor(monitor: DownloadMonitor | None) -> None:
    """Stop and dispose of a running DownloadMonitor thread, if any."""
    if monitor is not None:
        monitor.stop()
        monitor.wait()
        monitor.deleteLater()


def start_or_extend_dl_monitor(
    text: str, monitor: DownloadMonitor | None, total: int,
) -> tuple[DownloadMonitor | None, int, bool, bool]:
    """Parse a bootc "layers needed: ... (SIZE)" line and start a new
    DownloadMonitor, or raise an already-running one's total if a later
    phase reports a bigger download.

    Returns (monitor, total, started, progress_ready):
      - ``started`` is True only when a new monitor was created and the
        caller still needs to connect ``.stats`` and call ``.start()``.
      - ``progress_ready`` is True whenever the total changed (new or
        extended monitor) and the caller should switch its progress bar to
        determinate mode.
    """
    if "layers needed:" not in text:
        return monitor, total, False, False
    try:
        after = text.split("layers needed:")[1]
        size_str = after.split("(")[1].rstrip(")") if "(" in after else ""
        new_total = parse_size_bytes(size_str)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        _logger.debug("start_or_extend_dl_monitor: failed to parse download size from %r", text, exc_info=True)
        return monitor, total, False, False
    if new_total <= 0:
        return monitor, total, False, False
    if monitor is None:
        return DownloadMonitor(new_total, get_rx_bytes()), new_total, True, True
    if new_total > total:
        monitor.update_total(new_total)
        return monitor, new_total, False, True
    return monitor, total, False, False


class DataWorker(TrackedThread):
    result = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, key: str, fn):
        super().__init__()
        self._key = key
        self._fn = fn

    def run(self):
        try:
            self.result.emit(self._key, self._fn())
        except Exception as exc:  # noqa: BLE001 -- always emit failed so GUI spinners cannot hang
            _logger.exception("DataWorker %s failed", self._key)
            self.failed.emit(self._key, str(exc))


def finish_worker(owner: object, attr: str = "_worker") -> None:
    TASK_SUPERVISOR.finish_owner_task(owner, attr)


def release_worker_when_finished(owner: object, attr: str, worker: QThread) -> None:
    TASK_SUPERVISOR.release_when_finished(owner, attr, worker)


# S11: lifecycle standard — every DataWorker must pair
# finished->setattr(None) + finished->deleteLater OR use release_worker_when_finished.
# TelemetryWorker fixed in S5; audit grep: setAttr.*None.*deleteLater
# S11b: that only prevents the worker from leaking — its result/failed slot
# must separately be wrapped in guard_disposed() (below) if it touches a
# widget, or a signal delivered after page teardown crashes on an
# already-deleted Qt object. Audited/fixed across the app; grep for
# ".result.connect(" / ".failed.connect(" without guard_disposed to check
# any new call site follows this.

_SlotT = TypeVar("_SlotT", bound=Callable)


def guard_disposed(slot: _SlotT) -> _SlotT:
    """Wrap a Qt slot connected to a background-worker signal (result/failed/
    done) so a signal delivered after the receiving page was torn down —
    window closed while the worker was still in flight, its queued signal
    landing after close()/deleteLater() — no-ops instead of crashing on an
    already-deleted wrapped Qt widget.

    Every DataWorker/Worker result and failed handler that touches a widget
    must connect through this (or otherwise guard against RuntimeError);
    release_worker_when_finished only stops the *worker* from leaking, it
    does not protect its callback from firing after teardown.
    """

    @functools.wraps(slot)
    def _wrapped(*args, **kwargs):
        try:
            return slot(*args, **kwargs)
        except RuntimeError:
            return None

    return _wrapped  # type: ignore[return-value]


# R2: single ProbeWorker factory so callers don't hand-roll probe_cached
# lambdas and can use one tracked worker type everywhere.
def probe_worker(key: str, ttl: float, fetch):  # type: ignore[no-untyped-def]
    from kyth_shared.system.probe import probe_cached as _pc

    return DataWorker(key, lambda: _pc(key, ttl, fetch))
