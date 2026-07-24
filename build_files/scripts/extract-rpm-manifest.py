#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Extract RPM manifest from Syft JSON SBOM.")
    parser.add_argument("--sbom", required=True, type=Path, help="Path to input SBOM JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Path to output manifest text file")
    args = parser.parse_args()

    if not args.sbom.exists():
        print(f"Error: SBOM file {args.sbom} does not exist", file=sys.stderr)
        return 1

    try:
        sbom = json.loads(args.sbom.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error: Failed to parse JSON from {args.sbom}: {e}", file=sys.stderr)
        return 1

    pkgs = []
    for a in sbom.get("artifacts", []):
        if a.get("type") != "rpm":
            continue
        m = a.get("metadata") or {}
        name = a.get("name")
        if not name:
            continue
        arch = m.get("architecture", "")
        meta_ver = m.get("version", "")
        meta_rel = m.get("release", "")
        if meta_ver and meta_rel:
            pkgs.append(f"{name}-{meta_ver}-{meta_rel}.{arch}")
        else:
            ver = a.get("version", "")
            pkgs.append(f"{name}-{ver}.{arch}" if arch else f"{name}-{ver}")

    pkgs.sort()
    
    try:
        args.output.write_text("\n".join(pkgs) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"Error: Failed to write to {args.output}: {e}", file=sys.stderr)
        return 1

    print(f"Successfully extracted {len(pkgs)} RPM packages to {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
