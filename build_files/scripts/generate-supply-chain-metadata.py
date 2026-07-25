#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate supply chain metadata JSON.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-github-sha", required=True)
    parser.add_argument("--current-digest", required=True)
    parser.add_argument("--current-version", required=True)
    parser.add_argument("--previous-digest", required=True)
    parser.add_argument("--base-name", required=True)
    parser.add_argument("--base-digest", required=True)
    parser.add_argument("--upstream-base", required=True)
    parser.add_argument("--proton-cachyos-version", required=True)
    parser.add_argument("--thirdparty-hash", required=True)
    parser.add_argument("--kernel-flavor", required=True)
    parser.add_argument("--rpm-manifest", required=True, type=Path)
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--notes", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    source_sha = args.source_sha
    github_sha = args.source_github_sha if args.source_github_sha else source_sha

    metadata = {
        "image": args.image,
        "tag": args.tag,
        "source_sha": source_sha,
        "github_sha": github_sha,
        "current_digest": args.current_digest,
        "current_version": args.current_version,
        "previous_digest": args.previous_digest,
        "materials": {
            "build_base": f"{args.base_name}@{args.base_digest}",
            "upstream_base": args.upstream_base,
            "proton_cachyos_version": args.proton_cachyos_version,
            "thirdparty_versions_hash": args.thirdparty_hash,
            "kernel_flavor": args.kernel_flavor,
        },
        "rpm_manifest": args.rpm_manifest.name,
        "sbom": args.sbom.name,
        "notes": args.notes.name,
    }

    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_file = args.output_dir / "metadata.json"
        output_file.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(f"Generated supply chain metadata JSON at {output_file}")
    except Exception as e:
        print(f"Error: Failed to write metadata: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
