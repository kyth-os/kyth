#!/usr/bin/env python3
"""Generate the KythOS updater manifest (unsigned) for offline signing.

Part of the updater signature-verification flow (docs/updater-signing.md).
The rclone and GE-Proton runtime updaters only install versions that a
KythOS-signed manifest approves. This script produces the manifest —
(component, version, artifact, digest) for the current upstream
releases — and prints the offline signing + publishing steps. It never
signs anything itself and needs no credentials beyond an optional
GITHUB_TOKEN for API rate limits: signing is a deliberate manual step
on the key owner's own hardware.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from release_identity import R2_PUBLIC_BASE_URL

GITHUB_API = "https://api.github.com"
RCLONE_REPO = "rclone/rclone"
GE_PROTON_REPO = "GloriousEggroll/proton-ge-custom"
MANIFEST_FILENAME = "kyth-updater-manifest.json"
KEYS_FILENAME = "kyth-updater-keys.asc"


def fetch_text(url: str, *, api: bool = False) -> str:
    request = urllib.request.Request(url)
    request.add_header("User-Agent", "KythOS-Updater-Manifest/1.0")
    if api:
        request.add_header("Accept", "application/vnd.github+json")
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if token:
            request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def fetch_json(url: str) -> dict:
    return json.loads(fetch_text(url, api=True))


def clear_signed_body(content: str) -> str:
    """Body of a PGP clear-signed document (rclone's SHA256SUMS is one).

    Mirrors the Rust verifier's handling: strip the armor, keep only
    the signed body, never anything after the signature block.
    """
    lines = content.splitlines()
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines) or lines[index].strip() != "-----BEGIN PGP SIGNED MESSAGE-----":
        return content
    index += 1
    # Armor headers run until the first blank line.
    while index < len(lines) and lines[index].strip():
        index += 1
    body = []
    while index < len(lines):
        line = lines[index]
        if line.strip() == "-----BEGIN PGP SIGNATURE-----":
            return "\n".join(body)
        body.append(line[2:] if line.startswith("- ") else line)
        index += 1
    raise ValueError("clear-signed document has no signature block (truncated)")


def parse_sums(content: str, artifact: str) -> str:
    """The single digest pinned for `artifact` in a sha*sum-format file."""
    matches = []
    for line in clear_signed_body(content).splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        digest, name = parts
        name = name.lstrip("*").removeprefix("./")
        if name == artifact:
            matches.append(digest.lower())
    if len(matches) != 1:
        raise ValueError(f"expected exactly one checksum for {artifact}, found {len(matches)}")
    return matches[0]


def rclone_entry(version: str | None) -> dict:
    if version is None:
        release = fetch_json(f"{GITHUB_API}/repos/{RCLONE_REPO}/releases/latest")
        version = release["tag_name"]
    artifact = f"rclone-{version}-linux-amd64.zip"
    sums = fetch_text(f"https://downloads.rclone.org/{version}/SHA256SUMS")
    return {
        "component": "rclone",
        "version": version,
        "artifact": artifact,
        "sha256": parse_sums(sums, artifact),
    }


def ge_proton_entry(version: str | None) -> dict:
    if version is None:
        release = fetch_json(f"{GITHUB_API}/repos/{GE_PROTON_REPO}/releases/latest")
    else:
        release = fetch_json(f"{GITHUB_API}/repos/{GE_PROTON_REPO}/releases/tags/{version}")
    version = release["tag_name"]
    assets = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
    tarball = next((name for name in assets if name.endswith("x86_64.tar.gz")), None)
    sidecar = next((name for name in assets if name.endswith("x86_64.sha512sum")), None)
    if tarball is None or sidecar is None:
        raise ValueError(f"GE-Proton release {version} lacks the x86_64 tarball or sha512 sidecar")
    return {
        "component": "ge-proton",
        "version": version,
        "artifact": tarball,
        "sha512": parse_sums(fetch_text(assets[sidecar]), tarball),
    }


def build_manifest(rclone_version: str | None, ge_proton_version: str | None) -> dict:
    return {
        "schema": 1,
        "issued": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updates": [
            rclone_entry(rclone_version),
            ge_proton_entry(ge_proton_version),
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the (unsigned) KythOS updater manifest for offline signing."
    )
    parser.add_argument("--rclone-version", help="rclone tag (default: latest upstream release)")
    parser.add_argument(
        "--ge-proton-version", help="GE-Proton tag (default: latest upstream release)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(MANIFEST_FILENAME),
        help=f"manifest path (default: ./{MANIFEST_FILENAME})",
    )
    args = parser.parse_args()

    manifest = build_manifest(args.rclone_version, args.ge_proton_version)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for entry in manifest["updates"]:
        digest = entry.get("sha256") or entry.get("sha512")
        print(f"{entry['component']}: {entry['version']} ({entry['artifact']}) -> {digest}")
    print(f"\nWrote unsigned manifest: {args.output}")
    print(
        "\nNext steps (manual, on the key owner's hardware — see docs/updater-signing.md):\n"
        f"  1. gpg --armor --detach-sign --output {MANIFEST_FILENAME}.asc {args.output.name}\n"
        f"  2. Upload {MANIFEST_FILENAME} and {MANIFEST_FILENAME}.asc to the public\n"
        f"     release bucket root ({R2_PUBLIC_BASE_URL}/), alongside a current export\n"
        f"     of the signing certificate as {KEYS_FILENAME}:\n"
        f"       gpg --armor --export <updater-key-id> > {KEYS_FILENAME}\n"
        "  Nothing installs until all three files are published and the signature verifies."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
