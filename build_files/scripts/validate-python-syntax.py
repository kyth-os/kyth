#!/usr/bin/env python3
import ast
import subprocess
import sys
from pathlib import Path

def main() -> int:
    try:
        tracked = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    except subprocess.SubprocessError as exc:
        print(f"Error listing git files: {exc}", file=sys.stderr)
        return 1

    files = []
    for name in filter(None, tracked):
        path = Path(name)
        if not path.is_file():
            continue
        if path.suffix == ".py":
            files.append(path)
            continue
        try:
            with path.open(encoding="utf-8") as stream:
                first_line = stream.readline()
        except (OSError, UnicodeDecodeError):
            continue
        if first_line.startswith("#!") and "python" in first_line.lower():
            files.append(path)

    for path in files:
        name = path.as_posix()
        try:
            ast.parse(Path(name).read_text(encoding="utf-8"), filename=name)
        except Exception as exc:
            print(f"Python syntax error in {name}: {exc}", file=sys.stderr)
            return 1

    print(f"Checked {len(files)} Python files")
    return 0

if __name__ == "__main__":
    sys.exit(main())
