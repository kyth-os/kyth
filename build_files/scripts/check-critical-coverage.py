#!/usr/bin/env python3
"""Enforce focused coverage floors on Kyth's highest-risk service boundaries.

Floors live in build_files/config/coverage-floors.json, not inline here, so
they're plain data: no Python edit (and no risk of a fat-fingered float) to
raise one. Every commit that touched one of these files used to also need a
hand-edited threshold bump in this file — run with --update-floors instead:
it reads the coverage report just produced and raises (never lowers) any
floor that measured coverage now clears, so "keep the ratchet honest" is a
mechanical step instead of a manual transcription.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_FLOORS_FILE = Path("build_files/config/coverage-floors.json")


def load_floors(path: Path) -> dict[str, float]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_floors(path: Path, floors: dict[str, float]) -> None:
    path.write_text(
        json.dumps(floors, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def update_floors(floors_file: Path, report: dict) -> int:
    """Raise any floor that current coverage clears; never lower one.

    A file missing from the report (renamed/deleted, or genuinely untested
    this run) is left untouched rather than silently dropped — removing a
    file from the critical set is a deliberate decision, not a side effect
    of a partial coverage run.
    """
    floors = load_floors(floors_file)
    changed = False
    for filename, floor in sorted(floors.items()):
        summary = report["files"].get(filename, {}).get("summary")
        if summary is None:
            print(f"{filename}: absent from coverage report, floor unchanged ({floor:.1f}%)")
            continue
        actual = float(summary["percent_covered"])
        # Floor a whole point below actual, matching this file's existing
        # convention (round-number floors) — leaves headroom for the normal
        # run-to-run branch/line coverage variance instead of pinning to the
        # exact float this run happened to measure.
        candidate = float(int(actual))
        if candidate > floor:
            print(f"{filename}: {floor:.1f}% -> {candidate:.1f}% (measured {actual:.1f}%)")
            floors[filename] = candidate
            changed = True
        else:
            print(f"{filename}: {actual:.1f}% (floor {floor:.1f}% already covers it)")
    if changed:
        save_floors(floors_file, floors)
        print(f"Updated {floors_file}")
    else:
        print("No floors needed raising")
    return 0


def main() -> int:
    import argparse
    import subprocess  # nosec B404 -- only used below with a static argv, no shell

    parser = argparse.ArgumentParser(description="Check critical coverage thresholds")
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Only check thresholds for files changed vs HEAD (skips unchanged files)",
    )
    parser.add_argument(
        "--update-floors",
        action="store_true",
        help="Instead of gating, raise any floor that current coverage now clears and exit 0",
    )
    parser.add_argument(
        "--floors-file",
        type=Path,
        default=DEFAULT_FLOORS_FILE,
        help="Path to the JSON floors file (default: %(default)s)",
    )
    args = parser.parse_args()

    report = json.loads(Path("coverage.json").read_text(encoding="utf-8"))

    if args.update_floors:
        return update_floors(args.floors_file, report)

    thresholds = load_floors(args.floors_file)

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
        except (OSError, ValueError) as exc:
            import logging; logging.getLogger(__name__).debug("handled in check-critical-coverage.py", exc_info=True)
            changed = None
        if changed is not None and not changed:
            print("changed-only: no changed files vs HEAD, skipping")
            return 0

    failures = []
    skipped = 0
    for filename, minimum in thresholds.items():
        if changed is not None and filename not in changed:
            skipped += 1
            continue
        summary = report["files"].get(filename, {}).get("summary")
        # Compat: report may use src/... while floors use build_files/... or vice versa after packaging refactor
        if summary is None:
            alt = filename.replace("build_files/", "src/", 1) if filename.startswith("build_files/") else filename.replace("src/", "build_files/", 1)
            summary = report["files"].get(alt, {}).get("summary")
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