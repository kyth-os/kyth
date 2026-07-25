#!/usr/bin/env python3
"""resolve-versions.py — Single source of truth for build-time version lookups."""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path


def get_github_headers() -> dict[str, str]:
    """Retrieve default GitHub headers, incorporating GITHUB_TOKEN if available."""
    headers = {
        "User-Agent": "KythOS-VersionResolver/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            secret_path = Path("/run/secrets/github_token")
            if secret_path.is_file():
                token = secret_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def gh_latest_tag(repo: str) -> str:
    """Fetch the latest release tag name of a GitHub repository."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers=get_github_headers())
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("tag_name", "")
    except Exception as e:
        print(f"Error fetching tag for {repo}: {e}", file=sys.stderr)
        return ""


def cmd_proton_cachyos() -> int:
    """Print the latest Proton-CachyOS release tag."""
    tag = gh_latest_tag("CachyOS/proton-cachyos")
    if not tag or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$", tag):
        print("ERROR: could not resolve a safe immutable Proton-CachyOS release tag", file=sys.stderr)
        return 1
    print(tag)
    return 0


def cmd_thirdparty_versions() -> int:
    """Print the latest release tag for umu-launcher."""
    import threading

    repos = ["Open-Wine-Components/umu-launcher"]
    results: dict[str, str] = {}

    def fetch(repo: str) -> None:
        results[repo] = gh_latest_tag(repo)

    threads = []
    for repo in repos:
        t = threading.Thread(target=fetch, args=(repo,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    tags = []
    for repo in repos:
        tag = results.get(repo, "")
        if not tag or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$", tag):
            print(f"ERROR: could not resolve a safe immutable release tag for {repo}", file=sys.stderr)
            return 1
        print(f"  {repo}: {tag}", file=sys.stderr)
        tags.append(tag)

    print(tags[0])
    return 0


def cmd_cachyos_kernel() -> int:
    """Print the latest succeeded kernel-cachyos COPR build NVR, falling back to today's date."""
    url = (
        "https://copr.fedorainfracloud.org/api_3/package/"
        "?ownername=bieszczaders&projectname=kernel-cachyos&packagename=kernel-cachyos"
        "&with_latest_succeeded_build=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "KythOS-VersionResolver/1.0"})
    nvr = ""
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
            sp = data["builds"]["latest_succeeded"]["source_package"]
            ver = sp.get("version") or ""
            rel = sp.get("release") or ""
            nvr = f"{ver}-{rel}".strip("-")
    except Exception as e:
        print(f"COPR query failed: {e}", file=sys.stderr)

    if not nvr:
        nvr = datetime.date.today().isoformat()
    print(nvr)
    return 0


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: resolve-versions.py {proton-cachyos|thirdparty-versions|cachyos-kernel}", file=sys.stderr)
        sys.exit(2)

    subcmd = sys.argv[1]
    if subcmd == "proton-cachyos":
        sys.exit(cmd_proton_cachyos())
    elif subcmd == "thirdparty-versions":
        sys.exit(cmd_thirdparty_versions())
    elif subcmd == "cachyos-kernel":
        sys.exit(cmd_cachyos_kernel())
    else:
        print(f"unknown subcommand: {subcmd}", file=sys.stderr)
        print("usage: resolve-versions.py {proton-cachyos|thirdparty-versions|cachyos-kernel}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
