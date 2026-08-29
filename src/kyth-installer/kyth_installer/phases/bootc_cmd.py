"""bootc install command construction and streaming execution."""
from __future__ import annotations


from kyth_shared import get_rx_bytes

from ..config import SKIP_FETCH_CHECK
from ..executor import ExecutorCommand, PrivilegedExecutor
from ..imagesrc import _friendly_network_error
from ..streaming import StreamingCommandRunner


def _build_bootc_install_cmd(
    subcmd: str,
    src_ref: str,
    tgt_ref: str,
    target: str,
    extra_flags: list[str] | None = None,
) -> list[str]:
    cmd: list[str] = [
        "bootc",
        "install",
        subcmd,
        "--source-imgref",
        src_ref,
        "--target-imgref",
        tgt_ref,
    ]
    if subcmd == "to-filesystem":
        cmd.append("--acknowledge-destructive")
    if extra_flags:
        cmd.extend(extra_flags)
    if SKIP_FETCH_CHECK and "--skip-fetch-check" not in cmd:
        cmd.append("--skip-fetch-check")
    cmd.append(target)
    return cmd


def _run_cmd(
    cmd: list[str],
    pct_start: int,
    pct_end: int,
    log,
    progress,
    stall_timeout: int = 600,
    absolute_timeout: int | None = 3600,
    publish=None,
    cancel_event=None,
    io_stall_timeout: int | None = None,
    net_stall_timeout: int | None = None,
) -> None:
    # Import _as_root lazily so tests that patch `install._as_root` still apply
    try:
        from ..install import _as_root
    except ImportError:
        from ..system import _as_root  # type: ignore

    def error_factory(returncode: int, recent_output: list[str], argv: list[str]) -> Exception:
        lowered = "\n".join(recent_output).lower()
        network_tokens = (
            "network is unreachable",
            "no route to host",
            "temporary failure in name resolution",
            "name or service not known",
            "could not resolve",
            "connection timed out",
            "i/o timeout",
            "tls handshake timeout",
            "connection reset",
            "connection refused",
        )
        if any(token in lowered for token in network_tokens):
            return RuntimeError(
                _friendly_network_error(
                    "The image download lost network access before it finished."
                )
            )
        detail = "\n".join(recent_output[-10:]) or "No command output was captured."
        return RuntimeError(f"Command failed (exit {returncode}):\n  {' '.join(argv)}\n\n{detail}")

    executor = PrivilegedExecutor(
        run_command=None,  # streaming does not use the scalar runner
        as_root=_as_root,
        stream_runner_factory=StreamingCommandRunner,
    )
    executor.stream(
        ExecutorCommand.from_argv(cmd, "bootc image installation", timeout=absolute_timeout),
        rx_bytes=get_rx_bytes,
        publish=publish or (lambda _event: None),
        pct_start=pct_start,
        pct_end=pct_end,
        log=log,
        progress=progress,
        stall_timeout=stall_timeout,
        absolute_timeout=absolute_timeout,
        error_factory=error_factory,
        cancel_event=cancel_event,
        io_stall_timeout=io_stall_timeout,
        net_stall_timeout=net_stall_timeout,
    )
