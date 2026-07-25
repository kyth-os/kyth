#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate immutable build metadata JSON.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--upstream-base", required=True)
    parser.add_argument("--build-base", required=True)
    parser.add_argument("--proton-cachyos-version", required=True)
    parser.add_argument("--thirdparty-versions-hash", required=True)
    parser.add_argument("--umu-version", required=True)
    parser.add_argument("--kernel-flavor", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    metadata = {
        "image": args.image,
        "digest": args.digest,
        "version": args.version,
        "source_sha": args.source_sha,
        # GITHUB_SHA is the triggering commit recorded in the build provenance
        # attestation. For schedule runs it equals the default branch HEAD and
        # may differ from source_sha when building a non-default branch.
        "github_sha": args.github_sha,
        "source_tag": args.source_tag,
        "workflow_run_id": args.run_id,
        "workflow_run_attempt": args.run_attempt,
        "materials": {
            "upstream_base": args.upstream_base,
            "build_base": args.build_base,
            "proton_cachyos_version": args.proton_cachyos_version,
            "thirdparty_versions_hash": args.thirdparty_versions_hash,
            "umu_version": args.umu_version,
            "kernel_flavor": args.kernel_flavor,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0

if __name__ == "__main__":
    sys.exit(main())
