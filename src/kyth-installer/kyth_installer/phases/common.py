"""Shared helpers for install pipeline phases — power, transactions, mounts."""
from __future__ import annotations

import threading
import os
import json
import shutil

from ..config import TRANSACTION_FILE
from ..context import InstallerContext
from ..recovery import transaction_state_payload, write_transaction_state
from ..system import _as_root


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
    from ..storage_guard import DiskLease

    return DiskLease(disk, log, exclusive=False)


def _record_transaction(
    context: InstallerContext,
    status: str,
    *,
    message: str = "",
    log=None,
) -> None:
    # Rust owns the durable status ordering. The compatibility writer remains
    # only as a storage fallback when the native helper is not installed.
    try:
        from ..orchestration import decision

        native = decision(
            "transaction",
            lifecycle=context.lifecycle.value,
            phase=context.phase.value,
            status=getattr(context, "transaction_status", ""),
            next_status=status,
        )
        if native is not None and (
            native.get("accepted") is not True or native.get("status") != status
        ):
            raise RuntimeError("native installer transaction transition was not accepted")
        context.transaction_status = status
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:
        if log is not None:
            log(f"Warning: could not validate installer transaction transition: {exc}")
        return
    try:
        payload = transaction_state_payload(context=context, status=status, message=message)
        if shutil.which("kyth-installer-exec"):
            from ..runner import run_command

            run_command(
                _as_root(["kyth-installer-exec", "--operation", "transaction-write"]),
                input=json.dumps(
                    {
                        "operation": "transaction_write",
                        "path": str(TRANSACTION_FILE),
                        "state": payload,
                    },
                    separators=(",", ":"),
                ),
                text=True,
                check=True,
                timeout=30,
                stdout=os.devnull,
                stderr=os.devnull,
            )
        else:
            write_transaction_state(
                TRANSACTION_FILE,
                context=context,
                status=status,
                message=message,
            )
    except (OSError, ValueError) as exc:
        if log is not None:
            log(f"Warning: could not update installer transaction report: {exc}")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path  # fallback for unexpected
        if log is not None:
            log(f"Warning: could not update installer transaction report: {exc}")
