#!/usr/bin/env python3
"""R2 retention for the kyth-releases bucket.

Every live-ISO publish uploads one immutable build set per build
(``kyth-live-<channel>-<date>-<sha8>-<run>-<attempt>.iso`` plus its
-CHECKSUM/.sig/.bundle/.intoto.jsonl/.json companions) and overwrites the
channel pointer objects (``kyth-live-<channel>.iso`` + companions).
Nothing ever removed the old build sets, so the bucket grew by one full
ISO per build (~3 TB / ~$46 per month by 2026-10).

This script keeps only the newest ``--keep`` builds per channel and
deletes the older build sets. Safety properties:

- Only keys matching the strict immutable-build pattern are ever
  deleted. Channel pointers, the secure-boot cert, legacy one-off ISOs
  and any other key shape are not parseable as builds and are kept.
- Builds are ordered by the (date, run, attempt) tuple parsed from the
  key name, never by wall clock, so runner clock skew cannot reorder
  history.
- A build set is deleted as a unit: a stem is either kept whole or
  deleted whole, companions included.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

CHANNELS = ("testing", "latest")
BUILD_KEY_RE = re.compile(
    r"^kyth-live-(?P<channel>testing|latest)-(?P<date>\d{8})-[0-9a-f]{8}-"
    r"(?P<run>\d+)-(?P<attempt>\d+)\.iso"
    r"(?P<suffix>-CHECKSUM|\.sig|\.bundle|\.intoto\.jsonl|\.json)?$"
)
DELETE_BATCH = 1000  # S3 DeleteObjects limit


def parse_build_key(key: str) -> tuple[str, tuple[int, int, int]] | None:
    """Return (channel, (date, run, attempt)) for an immutable build key.

    The stem of a build set is the key with its companion suffix removed;
    grouping by stem keeps a build's files together. Returns None for
    anything that is not an immutable build object.
    """
    match = BUILD_KEY_RE.match(key)
    if match is None:
        return None
    order = (
        int(match.group("date")),
        int(match.group("run")),
        int(match.group("attempt")),
    )
    return match.group("channel"), order


def build_stem(key: str) -> str:
    match = BUILD_KEY_RE.match(key)
    assert match is not None
    suffix = match.group("suffix") or ""
    return key[: len(key) - len(suffix)]


def plan_deletions(keys: Iterable[str], keep: int = 5) -> list[str]:
    """Keys to delete so each channel retains its newest ``keep`` builds."""
    if keep < 1:
        raise ValueError("keep must be at least 1")
    stems: dict[str, dict[tuple[int, int, int], str]] = {
        channel: {} for channel in CHANNELS
    }
    members: dict[str, list[str]] = {}
    for key in keys:
        parsed = parse_build_key(key)
        if parsed is None:
            continue
        channel, order = parsed
        stem = build_stem(key)
        stems[channel][order] = stem
        members.setdefault(stem, []).append(key)
    doomed: list[str] = []
    for channel in CHANNELS:
        ordered = sorted(stems[channel], reverse=True)
        for order in ordered[keep:]:
            doomed.extend(members[stems[channel][order]])
    return sorted(doomed)


# --- aws CLI execution layer -------------------------------------------------
# ``runner`` maps an argv list to the parsed JSON stdout of the command.
# Tests inject a fake; production uses the real aws CLI (already the
# upload action's tool, with credentials in the environment).

Runner = Callable[[list[str]], Mapping]


def aws_cli_runner(argv: list[str]) -> Mapping:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(argv[:3])} failed rc={result.returncode}: "
            f"{result.stderr.strip()[:400]}"
        )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def list_objects(runner: Runner, bucket: str, endpoint: str, prefix: str) -> list[Mapping]:
    objects: list[Mapping] = []
    token: str | None = None
    while True:
        argv = [
            "aws", "s3api", "list-objects-v2",
            "--bucket", bucket,
            "--prefix", prefix,
            "--endpoint-url", endpoint,
            "--output", "json",
        ]
        if token:
            argv += ["--continuation-token", token]
        page = runner(argv)
        objects.extend(page.get("Contents") or [])
        if not page.get("IsTruncated"):
            return objects
        token = page.get("NextContinuationToken")
        if not token:
            raise RuntimeError("truncated listing without a continuation token")


def delete_objects(runner: Runner, bucket: str, endpoint: str, keys: list[str]) -> None:
    for start in range(0, len(keys), DELETE_BATCH):
        batch = keys[start : start + DELETE_BATCH]
        payload = {"Objects": [{"Key": key} for key in batch], "Quiet": True}
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(payload, handle)
            payload_path = handle.name
        try:
            runner([
                "aws", "s3api", "delete-objects",
                "--bucket", bucket,
                "--endpoint-url", endpoint,
                "--delete", f"file://{payload_path}",
                "--output", "json",
            ])
        finally:
            Path(payload_path).unlink(missing_ok=True)


def apply_retention(
    runner: Runner,
    bucket: str,
    endpoint: str,
    prefix: str = "kyth-live-",
    keep: int = 5,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Run one retention pass. Returns (builds_seen, keys_deleted)."""
    objects = list_objects(runner, bucket, endpoint, prefix)
    sizes = {obj["Key"]: int(obj.get("Size", 0)) for obj in objects}
    doomed = plan_deletions(sizes.keys(), keep=keep)
    builds_seen = len(
        {build_stem(key) for key in sizes if parse_build_key(key) is not None}
    )
    reclaimed = sum(sizes[key] for key in doomed)
    print(
        f"retention: {builds_seen} builds in s3://{bucket}, keep={keep} per channel, "
        f"{'would delete' if dry_run else 'deleting'} {len(doomed)} objects "
        f"({reclaimed / 1e9:.2f} GB)"
    )
    if doomed and not dry_run:
        delete_objects(runner, bucket, endpoint, doomed)
    return builds_seen, (0 if dry_run else len(doomed))


def main(argv: list[str] | None = None, runner: Runner | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--endpoint-url", required=True)
    parser.add_argument("--prefix", default="kyth-live-")
    parser.add_argument("--keep", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.keep < 1:
        parser.error("--keep must be at least 1")
    try:
        apply_retention(
            runner or aws_cli_runner,
            bucket=args.bucket,
            endpoint=args.endpoint_url,
            prefix=args.prefix,
            keep=args.keep,
            dry_run=args.dry_run,
        )
    except RuntimeError as error:
        print(f"retention: error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
