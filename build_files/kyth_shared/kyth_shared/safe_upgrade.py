"""Guard manual bootc upgrades with rollout and digest-quarantine policy."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Sequence

from .boot_health import (
    DEFAULT_STATE_PATH,
    image_ring,
    quarantine_reason,
    read_state,
    record_staged,
    rollout_policy_reason,
    write_state,
)
from .commands import run
from .system.bootc import image_digest_from_status, image_reference_from_status
from .system.bootc_query import fetch_status_data
from .system.registry import remote_digest_for_ref

DEFAULT_CONFIG_PATH = Path("/etc/kyth/auto-update.toml")


def load_rollout_ring(path: str | Path = DEFAULT_CONFIG_PATH) -> str:
    try:
        with Path(path).open("rb") as stream:
            data = tomllib.load(stream)
        section = data.get("auto_update", {})
        return str(section.get("rollout_ring", "follow-image"))
    except (OSError, TypeError, ValueError, tomllib.TOMLDecodeError):
        return "follow-image"


def upgrade(
    *,
    state_path: str | Path = DEFAULT_STATE_PATH,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> int:
    if os.geteuid() != 0:
        print("kyth-safe-upgrade must run as root", file=sys.stderr)
        return 77
    status = fetch_status_data()
    reference = image_reference_from_status(status)
    if not reference:
        print("Could not determine the booted image reference", file=sys.stderr)
        return 2
    ring = load_rollout_ring(config_path)
    policy_reason = rollout_policy_reason(reference, ring)
    if policy_reason:
        print(f"Update blocked by rollout policy: {policy_reason}", file=sys.stderr)
        return 3
    remote_digest = remote_digest_for_ref(reference)
    if not remote_digest:
        print("Could not resolve the remote image digest; update not staged", file=sys.stderr)
        return 4
    state = read_state(state_path)
    blocked = quarantine_reason(state, remote_digest)
    if blocked:
        print(f"Update blocked: {blocked}", file=sys.stderr)
        print(
            f"To retry deliberately: sudo kyth-boot-health clear-quarantine --digest {remote_digest}",
            file=sys.stderr,
        )
        return 5
    staged = image_digest_from_status(status, "staged")
    booted = image_digest_from_status(status, "booted")
    if remote_digest in {staged, booted}:
        print("KythOS is already running or has staged the latest allowed digest")
        return 0
    result = run(["bootc", "upgrade"], check=False)
    if result.returncode:
        return result.returncode
    write_state(
        record_staged(
            state,
            remote_digest,
            rollout_ring=image_ring(reference) or ring,
        ),
        state_path,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("kyth-safe-upgrade accepts no arguments", file=sys.stderr)
        return 64
    return upgrade()


if __name__ == "__main__":
    raise SystemExit(main())
