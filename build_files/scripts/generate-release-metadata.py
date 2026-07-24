#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate release metadata JSON files.")
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--iso-basename", required=True)
    parser.add_argument("--channel-basename", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--attestation-url", required=True)
    parser.add_argument("--immutable-tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-image", required=True)
    parser.add_argument("--source-digest", required=True)
    parser.add_argument("--build-date", required=True)
    parser.add_argument("--github-repository", required=True)
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    base_url = "https://pub-9a3cc72972ea44c4ae7504ee7cda1fa6.r2.dev"
    iso_name = args.iso_basename
    channel = args.channel_basename

    metadata = {
        "iso": iso_name,
        "sha256": args.sha256,
        "signature": f"{iso_name}.sig",
        "bundle": f"{iso_name}.bundle",
        "provenance": f"{iso_name}.intoto.jsonl",
        "checksum": f"{iso_name}-CHECKSUM",
        "attestation_url": args.attestation_url,
        "source_image": args.source_image,
        "source_image_digest": args.source_digest,
        "pinned_source_image": f"{args.source_image}@{args.source_digest}",
        "source_commit": args.source_sha,
        "source_tag": args.source_tag,
        "build_date": args.build_date,
        "release_tag": args.immutable_tag,
        "download_url": f"{base_url}/{iso_name}",
        "workflow_run": f"https://github.com/{args.github_repository}/actions/runs/{args.github_run_id}",
    }

    # Write immutable metadata
    (args.output_dir / f"{iso_name}.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    # Write channel metadata
    channel_metadata = dict(metadata)
    channel_metadata.update({
        "iso": channel,
        "signature": f"{channel}.sig",
        "bundle": f"{channel}.bundle",
        "provenance": f"{channel}.intoto.jsonl",
        "checksum": f"{channel}-CHECKSUM",
        "download_url": f"{base_url}/{channel}",
        "immutable_download_url": metadata["download_url"],
    })
    (args.output_dir / f"{channel}.json").write_text(json.dumps(channel_metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Generated metadata for {iso_name} and {channel}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
