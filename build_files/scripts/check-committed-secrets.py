#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path

def main() -> int:
    patterns = {
        "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "age key": re.compile(r"AGE-SECRET-KEY-1[0-9A-Z]{58}"),
        "cosign private key": re.compile(r"-----BEGIN ENCRYPTED COSIGN PRIVATE KEY-----"),
        "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
        "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{80,}\b"),
        "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
        "keyword-assigned secret": re.compile(
            r"""\b(secret|token|key|password)\b\s*[:=]\s*"""
            r"""(?:"[A-Za-z0-9+/=._-]{32,}"|'[A-Za-z0-9+/=._-]{32,}'|[A-Za-z0-9+/=_-]{32,}\b)"""
        ),
        "generic high-entropy secret": re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b.*\b(?:secret|token|key)\b", re.IGNORECASE),
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
        # Don't flag the detector implementations' own pattern literals.
        # Both copies intentionally contain the high-confidence signatures
        # they enforce; neither is a credential-bearing application file.
        # diagnostics_scrub.rs contains both the scrub patterns and realistic
        # test fixtures for the H1 bare-token redaction tests.
        if name in {
            "build_files/scripts/check-committed-secrets.py",
            "src/kyth-shared-rs/src/secret_scan.rs",
            "src/kyth-shared-rs/src/diagnostics_scrub.rs",
        }:
            continue
        # Try non-UTF-8 encodings before giving up: silently skipping a file
        # is a coverage hole. Log anything still unreadable.
        text = None
        for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
            try:
                text = path.read_text(encoding=encoding)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        if text is None:
            print(f"warning: skipping unreadable file: {name}", file=sys.stderr)
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
