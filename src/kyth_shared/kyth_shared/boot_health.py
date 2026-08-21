"""Digest-aware boot health, quarantine, and rollout-ring policy."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .system.bootc_query import fetch_status_data, image_digest_from_status

SCHEMA_VERSION = 1
DEFAULT_STATE_PATH = Path("/var/lib/kyth/boot-health.json")
DEFAULT_FAILURE_THRESHOLD = 3
VALID_ROLLOUT_RINGS = {"follow-image", "canary", "testing", "stable"}
_TAG_TO_RING = {"canary": "canary", "testing": "testing", "latest": "stable"}


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    digest: str
    failures: int
    reason: str
    first_failed_at: int
    last_failed_at: int


@dataclass(frozen=True, slots=True)
class BootHealthState:
    current_digest: str = ""
    last_healthy_digest: str = ""
    pending_digest: str = ""
    status: str = "unknown"
    failures: int = 0
    last_failure_boot_id: str = ""
    last_reason: str = ""
    last_recovered_digest: str = ""
    last_recovery_at: int = 0
    rollout_ring: str = "follow-image"
    updated_at: int = 0
    quarantined: Mapping[str, QuarantineRecord] = field(default_factory=dict)
    # Digest a rollback was already attempted for — set unconditionally
    # (success or failure) the first time a digest crosses the quarantine
    # threshold, so a rollback target that's itself unhealthy can never
    # ping-pong back and forth with the digest that triggered it.
    rollback_attempted_for: str = ""

    def invariants(self) -> list[str]:
        """S7: return list of violated invariants, [] if ok."""
        errs: list[str] = []
        if self.failures < 0:
            errs.append("failures<0")
        if self.status == "healthy" and not self.last_healthy_digest:
            errs.append("healthy but last_healthy_digest empty")
        for d, r in self.quarantined.items():
            if r.failures < DEFAULT_FAILURE_THRESHOLD:
                errs.append(f"quarantined {d} failures {r.failures} < threshold")
            if d != r.digest:
                errs.append(f"quarantined key {d} != record.digest {r.digest}")
        return errs

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["schema_version"] = SCHEMA_VERSION
        return value

    @classmethod
    def from_dict(cls, value: object) -> "BootHealthState":
        if not isinstance(value, dict) or value.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            return cls()
        quarantined: dict[str, QuarantineRecord] = {}
        raw_quarantine = value.get("quarantined", {})
        if isinstance(raw_quarantine, dict):
            for digest, record in raw_quarantine.items():
                if not isinstance(record, dict):
                    continue
                try:
                    parsed = QuarantineRecord(**record)
                except (TypeError, ValueError):
                    continue
                if parsed.digest == digest:
                    quarantined[digest] = parsed
        fields = cls.__dataclass_fields__
        values = {
            key: value[key]
            for key in fields
            if key in value and key != "quarantined"
        }
        try:
            return cls(**values, quarantined=quarantined)
        except (TypeError, ValueError):
            return cls()


@dataclass(frozen=True, slots=True)
class BootCheck:
    name: str
    passed: bool
    detail: str


def read_state(path: str | Path = DEFAULT_STATE_PATH) -> BootHealthState:
    try:
        return BootHealthState.from_dict(
            json.loads(Path(path).read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return BootHealthState()


def write_state(state: BootHealthState, path: str | Path = DEFAULT_STATE_PATH) -> None:
    from .atomic import atomic_write_json

    # W1: fail-closed — don't persist corrupt state that S16 banner would mis-render
    atomic_write_json(path, state.to_dict(), invariants=state.invariants)
    if state.quarantined:
        try:
            from kyth_shared.system.probe import invalidate_bootc
            invalidate_bootc()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
            pass


def image_ring(reference: str) -> str | None:
    without_digest = reference.partition("@")[0]
    tag = without_digest.rpartition(":")[2]
    if tag.endswith("-cachy"):
        tag = tag.removesuffix("-cachy")
    return _TAG_TO_RING.get(tag)


def rollout_policy_reason(reference: str, configured_ring: str) -> str | None:
    if configured_ring not in VALID_ROLLOUT_RINGS:
        return f"invalid rollout ring {configured_ring!r}"
    actual = image_ring(reference)
    if configured_ring == "follow-image" or actual == configured_ring:
        return None
    if actual is None:
        return f"cannot determine rollout ring from booted image {reference!r}"
    return f"booted image belongs to {actual} ring, configured for {configured_ring}"


def quarantine_reason(state: BootHealthState, digest: str) -> str | None:
    record = state.quarantined.get(digest)
    if not record:
        return None
    return (
        f"digest {digest} is quarantined after {record.failures} unhealthy boots: "
        f"{record.reason}"
    )


def is_retryable_bootc_error(exc: BaseException | None = None, reason: str | None = None) -> bool:
    """Return True for transient bootc pull failures that must not quarantine."""
    if exc is not None and isinstance(exc, TimeoutError):
        return True
    # subprocess.TimeoutExpired is a TimeoutError subclass on Python 3.11+
    try:
        import subprocess as _sp

        if exc is not None and isinstance(exc, _sp.TimeoutExpired):
            return True
    except (OSError, ValueError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        pass
    if reason is not None and "timed out" in reason.lower():
        return True
    if reason is not None and reason.lower().startswith("retryable:"):
        return True
    return False


def record_staged(
    state: BootHealthState,
    digest: str,
    *,
    rollout_ring: str,
    now: int | None = None,
) -> BootHealthState:
    return replace(
        state,
        pending_digest=digest,
        rollout_ring=rollout_ring,
        updated_at=int(time.time()) if now is None else now,
    )


def record_failure(
    state: BootHealthState,
    digest: str,
    boot_id: str,
    reason: str,
    *,
    threshold: int = DEFAULT_FAILURE_THRESHOLD,
    now: int | None = None,
) -> BootHealthState:
    timestamp = int(time.time()) if now is None else now
    same_deployment = state.current_digest == digest
    failures = state.failures if same_deployment else 0
    if not (same_deployment and state.last_failure_boot_id == boot_id):
        failures += 1
    quarantined = dict(state.quarantined)
    if failures >= threshold:
        previous = quarantined.get(digest)
        quarantined[digest] = QuarantineRecord(
            digest=digest,
            failures=failures,
            reason=reason,
            first_failed_at=previous.first_failed_at if previous else timestamp,
            last_failed_at=timestamp,
        )
    return BootHealthState(
        current_digest=digest,
        last_healthy_digest=state.last_healthy_digest,
        pending_digest="" if state.pending_digest == digest else state.pending_digest,
        status="quarantined" if digest in quarantined else "unhealthy",
        failures=failures,
        last_failure_boot_id=boot_id,
        last_reason=reason,
        last_recovered_digest=state.last_recovered_digest,
        last_recovery_at=state.last_recovery_at,
        rollout_ring=state.rollout_ring,
        updated_at=timestamp,
        quarantined=quarantined,
        # BootHealthState's own field comment: rollback_attempted_for is set
        # unconditionally the first time a digest crosses the quarantine
        # threshold so a rollback target that's itself unhealthy can never
        # ping-pong with the digest that triggered it. This is a from-scratch
        # constructor call, not replace(state, ...), so every field the
        # dataclass defines has to be carried forward explicitly here or it
        # silently reverts to its default ("") — discarding that memory on
        # the very next failure recorded for *any* digest, including ones
        # unrelated to the rollback this field is tracking.
        rollback_attempted_for=state.rollback_attempted_for,
    )


def mark_healthy(
    state: BootHealthState,
    digest: str,
    *,
    now: int | None = None,
) -> BootHealthState:
    quarantined = dict(state.quarantined)
    quarantined.pop(digest, None)
    recovered_digest = ""
    if state.current_digest != digest and state.current_digest in state.quarantined:
        recovered_digest = state.current_digest
    recovery_at = int(time.time()) if now is None else now
    return BootHealthState(
        current_digest=digest,
        last_healthy_digest=digest,
        pending_digest="" if state.pending_digest == digest else state.pending_digest,
        status="recovered" if recovered_digest else "healthy",
        last_reason=(
            f"Automatically recovered from quarantined digest {recovered_digest}"
            if recovered_digest else state.last_reason
        ),
        last_recovered_digest=recovered_digest or state.last_recovered_digest,
        last_recovery_at=recovery_at if recovered_digest else state.last_recovery_at,
        rollout_ring=state.rollout_ring,
        updated_at=recovery_at,
        quarantined=quarantined,
        rollback_attempted_for=state.rollback_attempted_for,
    )


def note_rollback_attempted(
    state: BootHealthState,
    digest: str,
    *,
    now: int | None = None,
) -> BootHealthState:
    return replace(
        state,
        rollback_attempted_for=digest,
        updated_at=int(time.time()) if now is None else now,
    )


def clear_quarantine(
    state: BootHealthState,
    digest: str,
    *,
    now: int | None = None,
) -> BootHealthState:
    quarantined = dict(state.quarantined)
    quarantined.pop(digest, None)
    return replace(
        state,
        status=(
            "unhealthy"
            if state.current_digest == digest and state.status == "quarantined"
            else state.status
        ),
        quarantined=quarantined,
        updated_at=int(time.time()) if now is None else now,
    )


def current_digest(status_data: dict | None = None) -> str:
    return image_digest_from_status(
        fetch_status_data() if status_data is None else status_data, "booted"
    ) or ""


def current_boot_id(path: str | Path = "/proc/sys/kernel/random/boot_id") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def required_checks(
    *,
    status_data: dict | None = None,
    os_release: str | None = None,
    path_exists: Callable[[str | Path], bool] = lambda path: Path(path).exists(),
    kernel_release: str | None = None,
    runtime_probe: Callable[[], Sequence[object]] | None = None,
) -> tuple[BootCheck, ...]:
    """Return the checks greenboot treats as required for this boot.

    The first group asserts the deployed tree is complete; the second, supplied
    by :func:`kyth_shared.system.boot_runtime.runtime_checks`, asserts the boot
    actually produced a usable desktop. Without the latter, every required
    check inspects a path baked into the image and rollback can never trigger.
    """
    status = fetch_status_data() if status_data is None else status_data
    digest = current_digest(status)
    if os_release is None:
        try:
            os_release = Path("/usr/lib/os-release").read_text(encoding="utf-8")
        except OSError:
            os_release = ""
    kernel_release = platform.release() if kernel_release is None else kernel_release
    os_id = next(
        (
            line.partition("=")[2].strip().strip("\"'")
            for line in os_release.splitlines()
            if line.startswith("ID=")
        ),
        "",
    )
    checks = [
        BootCheck("KythOS identity", os_id == "kythos", f"ID={os_id or 'missing'}"),
        BootCheck("bootc deployment", bool(digest), digest or "booted digest unavailable"),
        BootCheck(
            "bootc executable", path_exists("/usr/bin/bootc"),
            "/usr/bin/bootc present",
        ),
        BootCheck(
            "Plasma shell", path_exists("/usr/bin/plasmashell"),
            "/usr/bin/plasmashell present",
        ),
        BootCheck(
            "NetworkManager unit",
            path_exists("/usr/lib/systemd/system/NetworkManager.service"),
            "NetworkManager unit present",
        ),
        BootCheck(
            "kernel modules",
            path_exists(f"/usr/lib/modules/{kernel_release}"),
            f"module tree for {kernel_release}",
        ),
        BootCheck(
            "Measured boot",
            path_exists("/usr/bin/kyth-boot-verify"),
            "kyth-boot-verify present (composefs + UKI + TPM)",
        ),
    ]
    probe = runtime_probe
    if probe is None:
        # Imported lazily so boot_health stays importable (and cheap) for the
        # many Hub callers that only want read_state().
        from .system.boot_runtime import runtime_checks as probe  # noqa: PLC0415
    checks.extend(
        BootCheck(observed.name, observed.passed, observed.detail)
        for observed in probe()
    )
    return tuple(checks)


def _state_summary(state: BootHealthState) -> str:
    quarantined = len(state.quarantined)
    return (
        f"status={state.status} current={state.current_digest or 'unknown'} "
        f"last-healthy={state.last_healthy_digest or 'unknown'} "
        f"failures={state.failures} quarantined={quarantined}"
    )


def _default_rollback_runner() -> tuple[int, str]:
    from .commands import CommandRunner, CommandSpec  # local: keep this module import-light

    runner = CommandRunner()
    spec = CommandSpec(argv=("/usr/bin/bootc", "rollback"), timeout=60, name="bootc rollback")
    try:
        result = runner.run(spec, capture_output=True, text=True)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return 1, "bootc rollback could not execute"
    if result is None:
        return 1, "bootc rollback could not execute"
    return result.returncode, ((result.stderr or result.stdout) or "").strip()


def trigger_rollback_if_newly_quarantined(
    coordinator,
    before: BootHealthState,
    updated: BootHealthState,
    digest: str,
    *,
    run: Callable[[], tuple[int, str]] = _default_rollback_runner,
) -> None:
    """kyth-boot-health's own docstring promises "greenboot's retry and bootc
    rollback machinery" handle a required check failing — but that promise
    is grub2 boot_counter/grubenv specific. This image boots via
    systemd-boot + composefs/UKI loader entries with no boot-counter suffix
    and no grubenv, so nothing actually falls back to the previous
    deployment; a digest that keeps failing its required checks just
    reboots into itself forever (observed directly: 9 consecutive ~3min
    boots with no self-recovery). Implement the fallback in software instead
    of depending on bootloader-level counting this image doesn't have.

    Fires at most once per digest (recorded via rollback_attempted_for
    regardless of outcome) so a rollback target that's itself unhealthy can
    bounce back to the digest that triggered this exactly once, never loop.
    *coordinator* is a kyth_shared.update_coordinator.UpdateCoordinator,
    untyped here to avoid importing it at module scope (it imports this
    module too).
    """
    if digest not in updated.quarantined or digest in before.quarantined:
        return  # not newly quarantined this call — already handled or n/a
    if updated.rollback_attempted_for == digest:
        return
    try:
        returncode, detail = run()
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        print(f"bootc rollback errored for quarantined digest {digest}: {exc}", file=sys.stderr)
        try:
            coordinator.note_rollback_attempted(digest)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc2:  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort persistence of rollback marker
            print(f"Failed to persist rollback marker for {digest}: {exc2}", file=sys.stderr)
        return
    # Record attempt regardless of success so we never loop on a bad rollback target;
    # returncode is still logged for diagnostics.
    if returncode == 0:
        print(f"Rolled back from quarantined digest {digest} — takes effect next boot")
    else:
        print(f"bootc rollback failed for quarantined digest {digest}: {detail}", file=sys.stderr)
    try:
        coordinator.note_rollback_attempted(digest)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort persistence of rollback marker
        print(f"Failed to persist rollback marker for {digest}: {exc}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kyth-boot-health",
        description="Manage KythOS digest-aware boot health and quarantine state.",
    )
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    subparsers.add_parser("mark-healthy")
    failed = subparsers.add_parser("record-failure")
    failed.add_argument("--reason", required=True)
    failed.add_argument("--threshold", type=int, default=DEFAULT_FAILURE_THRESHOLD)
    status = subparsers.add_parser("status")
    status.add_argument("--json", action="store_true")
    clear = subparsers.add_parser("clear-quarantine")
    clear.add_argument("--digest", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Use UpdateCoordinator for all state mutations to prevent lost-update races
    # between concurrent Hub pages, safe-upgrade, and greenboot hooks.
    if args.command == "check":
        checks = required_checks()
        for check in checks:
            print(f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}")
        return 0 if all(check.passed for check in checks) else 1
    if args.command == "status":
        # Read-only — no lock needed
        state = read_state(args.state)
        print(json.dumps(state.to_dict(), indent=2, sort_keys=True) if args.json else _state_summary(state))
        return 0
    if args.command == "clear-quarantine":
        from .update_coordinator import UpdateCoordinator

        coord = UpdateCoordinator(args.state)
        before = coord.read()
        was_quarantined = args.digest in before.quarantined
        try:
            coord.clear_quarantine(args.digest)
        except ValueError as exc:
            print(f"Refusing to persist corrupt state: {exc}", file=sys.stderr)
            return 1
        print(
            f"Cleared quarantine for {args.digest}"
            if was_quarantined else f"Digest {args.digest} was not quarantined"
        )
        return 0
    digest = current_digest()
    if not digest:
        print("Could not determine booted image digest")
        return 1
    if args.command == "mark-healthy":
        from .update_coordinator import UpdateCoordinator

        try:
            UpdateCoordinator(args.state).mark_healthy(digest)
        except ValueError as exc:
            print(f"Refusing to persist corrupt state: {exc}", file=sys.stderr)
            return 1
        print(f"Marked {digest} healthy")
        return 0
    # record-failure — atomic via coordinator (dedupes on boot_id internally)
    from .update_coordinator import UpdateCoordinator

    coordinator = UpdateCoordinator(args.state)
    before = coordinator.read()
    try:
        updated = coordinator.record_failure(
            digest, current_boot_id(), args.reason, threshold=max(1, args.threshold)
        )
    except ValueError as exc:
        print(f"Refusing to persist corrupt state: {exc}", file=sys.stderr)
        return 1
    print(_state_summary(updated))
    trigger_rollback_if_newly_quarantined(coordinator, before, updated, digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
