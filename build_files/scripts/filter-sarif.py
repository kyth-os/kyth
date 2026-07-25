#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

def main() -> int:
    parser = argparse.ArgumentParser(description="Filter SARIF findings to changed files.")
    parser.add_argument("--root", required=True, type=Path, help="Repository root directory")
    parser.add_argument("--changed-files", required=True, type=Path, help="File containing list of changed files (one per line)")
    parser.add_argument("--sarif", required=True, type=Path, help="SARIF report file")
    parser.add_argument("--label", required=True, help="Tool name label for output messages (e.g. Codacy, CodeQL)")
    args = parser.parse_args()

    root = args.root.resolve()
    changed = set(args.changed_files.read_text(encoding="utf-8").splitlines())
    
    try:
        payload = json.loads(args.sarif.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error reading SARIF file {args.sarif}: {exc}", file=sys.stderr)
        return 1

    findings = []
    for run in payload.get("runs", []):
        for result in run.get("results", []):
            if any(item.get("kind") == "inSource" for item in result.get("suppressions", [])):
                continue
            locations = result.get("locations") or []
            if not locations:
                continue
            physical = locations[0].get("physicalLocation", {})
            uri = physical.get("artifactLocation", {}).get("uri", "")
            parsed = urlparse(uri)
            candidate = Path(unquote(parsed.path if parsed.scheme == "file" else uri))
            if candidate.is_absolute():
                try:
                    name = candidate.resolve().relative_to(root).as_posix()
                except ValueError:
                    continue
            else:
                name = candidate.as_posix()
            if name not in changed:
                continue
            region = physical.get("region", {})
            message = result.get("message", {}).get("text", f"{args.label} finding")
            findings.append((name, region.get("startLine", 1), result.get("ruleId", "unknown"), message))

    if findings:
        print(f"{args.label} found {len(findings)} issue(s) in changed files:", file=sys.stderr)
        for name, line, rule, message in findings:
            print(f"  {name}:{line}: {rule}: {message}", file=sys.stderr)
        return 1

    print(f"{args.label} passed for {len(changed)} changed file(s)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
