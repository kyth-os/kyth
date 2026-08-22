#!/usr/bin/env python3
"""Decide whether CI can reuse a published Kyth base image.

Inspects an existing GHCR ``base-${tag}`` ref and compares
``org.kyth.build.*`` labels against the current build inputs. A missing
tag or an unlabeled image (every base published before this helper)
forces a rebuild.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

LABEL_UPSTREAM = "org.kyth.build.upstream-base"
LABEL_FLAVOR = "org.kyth.build.kernel-flavor"
LABEL_KERNEL = "org.kyth.build.cachyos-kernel-version"
LABEL_SRC = "org.kyth.build.base-src-hash"
REQUIRED_LABELS = (LABEL_UPSTREAM, LABEL_FLAVOR, LABEL_KERNEL, LABEL_SRC)


def source_hash(source_root: Path) -> str:
    """Stable sha256 of every regular file under ``source_root``."""
    root = source_root.resolve()
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _walk_keys(payload: Any, keys: tuple[str, ...]) -> Any:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_digest(payload: dict[str, Any]) -> str | None:
    for path in (
        ("manifest", "digest"),
        ("Descriptor", "digest"),
        ("descriptor", "digest"),
        ("digest",),
    ):
        value = _walk_keys(payload, path)
        if isinstance(value, str) and value.startswith("sha256:"):
            return value
    return None


def extract_labels(payload: dict[str, Any]) -> dict[str, str]:
    images = [payload.get("image"), payload.get("Image"), payload]
    for image in images:
        if not isinstance(image, dict):
            continue
        config = image.get("config") or image.get("Config") or {}
        if not isinstance(config, dict):
            continue
        labels = config.get("Labels") or config.get("labels") or {}
        if isinstance(labels, dict) and labels:
            return {str(key): str(value) for key, value in labels.items() if value is not None}
    return {}


def decide_reuse(
    *,
    labels: dict[str, str],
    digest: str | None,
    upstream: str,
    flavor: str,
    kernel: str,
    src_hash: str,
) -> dict[str, Any]:
    expected = {
        LABEL_UPSTREAM: upstream,
        LABEL_FLAVOR: flavor,
        LABEL_KERNEL: kernel,
        LABEL_SRC: src_hash,
    }
    missing = [key for key in REQUIRED_LABELS if key not in labels]
    if missing:
        return {"reuse": False, "digest": digest, "reason": "missing-labels"}
    mismatches = [key for key, value in expected.items() if labels.get(key) != value]
    if mismatches:
        return {"reuse": False, "digest": digest, "reason": "label-mismatch"}
    if not digest or not digest.startswith("sha256:"):
        return {"reuse": False, "digest": digest, "reason": "missing-digest"}
    return {"reuse": True, "digest": digest, "reason": "match"}


def inspect_ref(ref: str) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{ json . }}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def cmd_hash(args: argparse.Namespace) -> int:
    print(source_hash(args.source_root))
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    src_hash = source_hash(args.source_root)
    payload = inspect_ref(args.ref)
    if payload is None:
        print(json.dumps({"reuse": False, "digest": None, "reason": "inspect-failed"}))
        return 0
    decision = decide_reuse(
        labels=extract_labels(payload),
        digest=extract_digest(payload),
        upstream=args.upstream,
        flavor=args.flavor,
        kernel=args.kernel,
        src_hash=src_hash,
    )
    print(json.dumps(decision))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    hash_parser = sub.add_parser("hash", help="Print sha256 of build_base sources")
    hash_parser.add_argument("--source-root", type=Path, required=True)
    hash_parser.set_defaults(func=cmd_hash)

    decide_parser = sub.add_parser("decide", help="Inspect a published base tag")
    decide_parser.add_argument("--ref", required=True)
    decide_parser.add_argument("--upstream", required=True)
    decide_parser.add_argument("--flavor", required=True)
    decide_parser.add_argument("--kernel", required=True)
    decide_parser.add_argument("--source-root", type=Path, required=True)
    decide_parser.set_defaults(func=cmd_decide)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
