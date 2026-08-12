#!/usr/bin/env python3
"""Enforce focused coverage floors on Kyth's highest-risk service boundaries."""
from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLDS = {
    "build_files/kyth-installer/kyth_installer/fsresize.py": 90.0,
    "build_files/kyth-installer/kyth_installer/recovery.py": 85.0,
    "build_files/kyth-installer/kyth_installer/services/installer_service.py": 85.0,
    "build_files/kyth-installer/kyth_installer/system.py": 85.0,
    "build_files/kyth-welcome/kyth_welcome/services/privileged.py": 80.0,
    "build_files/kyth-welcome/kyth_welcome/services/updates.py": 75.0,
    "build_files/kyth_shared/kyth_shared/desktop/windows_installer.py": 80.0,
    "build_files/kyth_shared/kyth_shared/thirdparty.py": 90.0,
    "build_files/kyth_shared/kyth_shared/user_polish.py": 30.0,
    "build_files/kyth_shared/kyth_shared/vm_acceptance.py": 70.0,
}


def main() -> int:
    import argparse
    import subprocess  # nosec B404 -- only used below with a static argv, no shell

    parser = argparse.ArgumentParser(description="Check critical coverage thresholds")
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Only check thresholds for files changed vs HEAD (skips unchanged files)",
    )
    args = parser.parse_args()

    changed: set[str] | None = None
    if args.changed_only:
        try:
            # Static argv, no shell, no untrusted input — this is a dev/CI
            # tooling script invoking git by its PATH name like the rest of
            # this repo's build scripts do.
            out = subprocess.check_output(  # nosec B603 B607
                ["git", "diff", "--name-only", "HEAD"], text=True, stderr=subprocess.DEVNULL
            )
            changed = {line.strip() for line in out.splitlines() if line.strip()}
            # also include staged changes
            out2 = subprocess.check_output(  # nosec B603 B607
                ["git", "diff", "--name-only", "--cached"], text=True, stderr=subprocess.DEVNULL
            )
            changed.update(line.strip() for line in out2.splitlines() if line.strip())
        except Exception:
            changed = None
        if changed is not None and not changed:
            print("changed-only: no changed files vs HEAD, skipping")
            return 0

    report = json.loads(Path("coverage.json").read_text(encoding="utf-8"))
    failures = []
    skipped = 0
    for filename, minimum in THRESHOLDS.items():
        if changed is not None and filename not in changed:
            skipped += 1
            continue
        summary = report["files"].get(filename, {}).get("summary")
        if summary is None:
            failures.append(f"{filename}: absent from coverage report")
            continue
        actual = float(summary["percent_covered"])
        print(f"{filename}: {actual:.1f}% (minimum {minimum:.1f}%)")
        if actual < minimum:
            failures.append(f"{filename}: {actual:.1f}% is below {minimum:.1f}%")
    if skipped:
        print(f"changed-only: skipped {skipped} unchanged files")
    if failures:
        print("Critical coverage gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
