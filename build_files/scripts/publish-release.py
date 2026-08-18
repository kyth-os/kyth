#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"Running: {' '.join(args)}")
    return subprocess.run(args, check=check, text=True, capture_output=True)

def main() -> int:
    parser = argparse.ArgumentParser(description="Create GitHub Releases and upload artifacts.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--channel-tag", required=True)
    parser.add_argument("--immutable-tag", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-digest", required=True)
    parser.add_argument("--attestation-url", required=True)
    parser.add_argument("--iso-basename", required=True)
    parser.add_argument("--channel-basename", required=True)
    parser.add_argument("--iso-changelog", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    # Form titles and options
    if args.source_tag == "testing":
        channel_title = "Kyth Live ISO - Testing"
        immutable_title = f"Kyth Live ISO - Testing - {args.release_id}"
        prerelease = True
        latest = False
    else:
        channel_title = "Kyth Live ISO - Stable"
        immutable_title = f"Kyth Live ISO - Stable - {args.release_id}"
        prerelease = False
        latest = True

    public_base = "https://pub-9a3cc72972ea44c4ae7504ee7cda1fa6.r2.dev"
    immutable_iso_url = f"{public_base}/{args.iso_basename}"
    channel_iso_url = f"{public_base}/{args.channel_basename}"
    immutable_release_url = f"https://github.com/{args.repo}/releases/tag/{args.immutable_tag}"

    # Read changelog notes
    try:
        changelog_content = args.iso_changelog.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        import logging; logging.getLogger(__name__).debug("handled in publish-release.py", exc_info=True)
        changelog_content = ""

    # 1. Generate Immutable Release Notes
    immutable_notes_lines = [
        f"Permanent KythOS ISO build from **{args.source_tag}**.",
        "",
        changelog_content.strip(),
        "",
        "---",
        f"**[Download immutable ISO]({immutable_iso_url})** | [Checksum]({immutable_iso_url}-CHECKSUM)",
        "",
        f"- Source commit: **{args.source_sha}**",
        f"- Source image digest: **{args.source_digest}**",
        f"- Workflow run: https://github.com/{args.repo}/actions/runs/{args.run_id}",
        f"- Build provenance: {args.attestation_url}",
        "",
        "The checksum, Cosign signature and bundle, metadata, and GitHub build provenance are attached to this release."
    ]
    immutable_notes_file = Path("immutable_notes.md")
    immutable_notes_file.write_text("\n".join(immutable_notes_lines).strip() + "\n", encoding="utf-8")

    # Create Immutable Release
    create_imm_args = ["gh", "release", "create", args.immutable_tag,
                       "--target", args.source_sha,
                       "--title", immutable_title,
                       "--notes-file", str(immutable_notes_file)]
    if prerelease:
        create_imm_args.append("--prerelease")
    
    run_command(create_imm_args)

    # Upload Immutable Artifacts
    iso_path = args.source_dir / args.iso_basename
    upload_imm_files = [
        f"{iso_path}-CHECKSUM",
        f"{iso_path}.sig",
        f"{iso_path}.bundle",
        f"{iso_path}.intoto.jsonl",
        f"{iso_path}.json"
    ]
    run_command(["gh", "release", "upload", args.immutable_tag] + upload_imm_files)

    # 2. Generate Channel Release Notes
    channel_notes_lines = [
        f"This is the moving **{args.source_tag}** channel pointer.",
        "",
        changelog_content.strip(),
        "",
        "---",
        f"**[Download current ISO]({channel_iso_url})** | [Checksum]({channel_iso_url}-CHECKSUM)",
        "",
        f"Current immutable release: [{args.immutable_tag}]({immutable_release_url})",
        "",
        f"- Source commit: **{args.source_sha}**",
        f"- Source image digest: **{args.source_digest}**",
        f"- Build provenance: {args.attestation_url}"
    ]
    channel_notes_file = Path("channel_notes.md")
    channel_notes_file.write_text("\n".join(channel_notes_lines).strip() + "\n", encoding="utf-8")

    # Delete existing channel release if exists
    run_command(["gh", "release", "delete", args.channel_tag, "--yes"], check=False)

    # Create Channel Release
    create_chan_args = ["gh", "release", "create", args.channel_tag,
                        "--target", args.source_sha,
                        "--title", channel_title,
                        "--notes-file", str(channel_notes_file)]
    if prerelease:
        create_chan_args.append("--prerelease")
    if latest:
        create_chan_args.append("--latest")

    run_command(create_chan_args)

    # Upload Channel Artifacts
    channel_path = args.source_dir / args.channel_basename
    upload_chan_files = [
        f"{channel_path}-CHECKSUM",
        f"{channel_path}.sig",
        f"{channel_path}.bundle",
        f"{channel_path}.intoto.jsonl",
        f"{channel_path}.json"
    ]
    run_command(["gh", "release", "upload", args.channel_tag, "--clobber"] + upload_chan_files)

    # Clean up temp files
    try:
        immutable_notes_file.unlink()
        channel_notes_file.unlink()
    except OSError:
        pass

    return 0

if __name__ == "__main__":
    sys.exit(main())