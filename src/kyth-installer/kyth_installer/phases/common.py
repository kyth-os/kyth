"""Shared helpers for install pipeline phases — power, transactions, mounts."""
from __future__ import annotations

import threading
import os
import contextlib
import fcntl

from ..config import TRANSACTION_FILE
from ..context import InstallerContext
from ..recovery import write_transaction_state


def _push(event: dict, context: InstallerContext) -> None:
    context.events.publish(event)


def _assert_still_on_ac(log) -> None:
    """Continuous power guard — re-checks at each phase boundary."""
    from ..assurance import _battery_check

    check = _battery_check()
    if check.status == "fail":
        msg = f"{check.detail} \u2014 Plug in AC power and keep it connected through install."
        log(f"Power guard refused: {msg}")
        raise RuntimeError(msg)


def _abort_on_power_loss(log, context, msg: str) -> None:
    log(msg)
    try:
        context._power_failed = msg  # type: ignore[attr-defined]
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        pass
    try:
        context.cancel_requested.set()
        context.events.publish({"type": "log", "text": msg})
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        pass


def _start_power_watch(log, context, stop_event: threading.Event) -> threading.Thread:
    """Background poll every 10s through IMAGE phase; fails closed on AC yank."""
    from ..assurance import _battery_check

    def _watch():
        while not stop_event.is_set():
            if stop_event.wait(10):
                break
            try:
                chk = _battery_check()
            except OSError:
                continue
            except RuntimeError as exc:
                detail = str(exc).strip() or "AC power lost"
                _abort_on_power_loss(
                    log, context, f"Power lost during install: {detail} — aborting to avoid half-write.",
                )
                break
            else:
                if chk.status == "fail":
                    _abort_on_power_loss(
                        log,
                        context,
                        f"Power lost during install: {chk.detail} — aborting to avoid half-write.",
                    )
                    break

    th = threading.Thread(target=_watch, name="kyth-power-watch", daemon=True)
    th.start()
    return th


def _stop_power_watch(thread: threading.Thread | None, stop_event: threading.Event | None) -> None:
    if stop_event is not None:
        stop_event.set()
    if thread is not None:
        thread.join(timeout=2)


def _disk_image_hold(disk: str, log):
    """Context manager: hold shared flock on disk through IMAGE phase."""
    @contextlib.contextmanager
    def _hold():
        fd = -1
        try:
            try:
                fd = os.open(disk, os.O_RDONLY)
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                log(f"Holding shared lock on {disk} through image write...")
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
                log(f"Warning: could not flock disk for IMAGE phase: {exc}")
                fd = -1
            yield
        finally:
            if fd != -1:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                    pass

    return _hold()


def _record_transaction(
    context: InstallerContext,
    status: str,
    *,
    message: str = "",
    log=None,
) -> None:
    try:
        write_transaction_state(
            TRANSACTION_FILE,
            context=context,
            status=status,
            message=message,
        )
        # write_transaction_state already fsyncs file + parent via _atomic_write_json,
        # but ensure parent dir is durable even if future impl changes.
        try:
            dfd = os.open(str(TRANSACTION_FILE.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except (OSError, ValueError):
            pass
    except (OSError, ValueError) as exc:
        if log is not None:
            log(f"Warning: could not update installer transaction report: {exc}")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path  # fallback for unexpected
        if log is not None:
            log(f"Warning: could not update installer transaction report: {exc}")
