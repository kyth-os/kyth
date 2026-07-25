#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path

def main() -> int:
    patterns = {
        "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
        "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{80,}\b"),
        "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    }
    binary_suffixes = {".cer", ".png", ".jpg", ".jpeg", ".webp", ".ico"}
    
    try:
        files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    except subprocess.SubprocessError as exc:
        print(f"Error listing git files: {exc}", file=sys.stderr)
        return 1

    findings = []
    for name in files:
        path = Path(name)
        if not path.is_file():
            continue
        if path.suffix.lower() in binary_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in patterns.items():
            if pattern.search(text):
                findings.append(f"{name}: matched {label}")
                
    if findings:
        print("Potential committed secrets found:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
        
    print(f"Checked {len(files)} tracked files for high-confidence secret patterns")
    return 0

if __name__ == "__main__":
    sys.exit(main())
