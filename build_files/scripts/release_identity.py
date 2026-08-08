#!/usr/bin/env python3
"""Generate the canonical names shared by Kyth release workflows."""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_CHANNELS = frozenset({"latest", "testing"})


@dataclass(frozen=True)
class ReleaseIdentity:
    source_sha: str
    release_id: str
    iso_basename: str
    channel_basename: str
    immutable_tag: str
    artifact_name: str


def build_identity(
    source_tag: str,
    source_sha: str,
    run_number: str,
    run_attempt: str,
    *,
    build_date: str | None = None,
) -> ReleaseIdentity:
    if source_tag not in SUPPORTED_CHANNELS:
        raise ValueError(f"unsupported release channel: {source_tag}")
    if len(source_sha) < 8:
        raise ValueError("source SHA must contain at least eight characters")
    date = build_date or dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    release_id = f"{date}-{source_sha[:8]}-{run_number}-{run_attempt}"
    return ReleaseIdentity(
        source_sha=source_sha,
        release_id=release_id,
        iso_basename=f"kyth-live-{source_tag}-{release_id}.iso",
        channel_basename=f"kyth-live-{source_tag}.iso",
        immutable_tag=f"iso-{source_tag}-{release_id}",
        artifact_name=f"kyth-live-iso-{source_tag}-{release_id}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--source-sha")
    parser.add_argument("--run-number", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--build-date")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    sha = args.source_sha or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    identity = build_identity(
        args.source_tag,
        sha,
        args.run_number,
        args.run_attempt,
        build_date=args.build_date,
    )
    output = "\n".join(
        f"{field}={getattr(identity, field)}"
        for field in identity.__dataclass_fields__
    ) + "\n"
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write(output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
