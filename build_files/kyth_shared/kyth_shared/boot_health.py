"""Digest-aware boot health, quarantine, and rollout-ring policy."""
from __future__ import annotations

import argparse
import json
import os
import platform
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
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent, text=True
    )
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        # P1-1: quarantine write hides stale bootc-status-data for 90 s → invalidate
        if state.quarantined:
            try:
                from kyth_shared.system.probe import invalidate_probe_caches

                invalidate_probe_caches(["bootc-status-data", "bootc-status-text"])
            except Exception:
                pass
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


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
) -> tuple[BootCheck, ...]:
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
    return tuple(checks)


def _state_summary(state: BootHealthState) -> str:
    quarantined = len(state.quarantined)
    return (
        f"status={state.status} current={state.current_digest or 'unknown'} "
        f"last-healthy={state.last_healthy_digest or 'unknown'} "
        f"failures={state.failures} quarantined={quarantined}"
    )


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
    state = read_state(args.state)
    if args.command == "check":
        checks = required_checks()
        for check in checks:
            print(f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}")
        return 0 if all(check.passed for check in checks) else 1
    if args.command == "status":
        print(json.dumps(state.to_dict(), indent=2, sort_keys=True) if args.json else _state_summary(state))
        return 0
    if args.command == "clear-quarantine":
        was_quarantined = args.digest in state.quarantined
        write_state(clear_quarantine(state, args.digest), args.state)
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
        write_state(mark_healthy(state, digest), args.state)
        print(f"Marked {digest} healthy")
        return 0
    updated = record_failure(
        state, digest, current_boot_id(), args.reason, threshold=max(1, args.threshold)
    )
    write_state(updated, args.state)
    print(_state_summary(updated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
