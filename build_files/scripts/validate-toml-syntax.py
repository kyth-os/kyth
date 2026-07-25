#!/usr/bin/env python3
import subprocess
import sys
import tomllib
from pathlib import Path

def main() -> int:
    try:
        files = subprocess.check_output(["git", "ls-files", "*.toml"], text=True).splitlines()
    except subprocess.SubprocessError as exc:
        print(f"Error listing TOML files: {exc}", file=sys.stderr)
        return 1

    for name in files:
        path = Path(name)
        if not path.is_file():
            continue
        try:
            with path.open("rb") as stream:
                tomllib.load(stream)
        except Exception as exc:
            print(f"TOML parse error in {name}: {exc}", file=sys.stderr)
            return 1
            
    print(f"Checked {len(files)} TOML files")
    return 0

if __name__ == "__main__":
    sys.exit(main())
