"""Shared utilities for KythOS's read-only runtime diagnostic scripts."""
from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime


class DiagnosticReporter:
    """Standard reporter for tracking, printing, and notifying diagnostic check results."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.warnings = 0
        self.failures = 0
        self.results: list[tuple[str, str, str]] = []  # (level, check_name, message)

    def print_header(self) -> None:
        """Print standard KythOS generation header."""
        now = datetime.now().astimezone().isoformat()
        print(f"KythOS {self.title}")
        print(f"Generated: {now}")
        print()

    def have(self, cmd: str) -> bool:
        """Check if command exists on system."""
        return shutil.which(cmd) is not None

    def pass_check(self, check_name: str, message: str) -> None:
        """Log and print a passed check."""
        print(f"PASS  {check_name:<28} {message}")
        self.results.append(("PASS", check_name, message))

    def warn_check(self, check_name: str, message: str) -> None:
        """Log and print a warning check."""
        print(f"WARN  {check_name:<28} {message}")
        self.warnings += 1
        self.results.append(("WARN", check_name, message))

    def fail_check(self, check_name: str, message: str) -> None:
        """Log and print a failed check."""
        print(f"FAIL  {check_name:<28} {message}")
        self.failures += 1
        self.results.append(("FAIL", check_name, message))

    def notify(self, title: str, body: str) -> None:
        """Send a desktop notification using notify-send or kdialog."""
        if self.have("notify-send"):
            try:
                subprocess.run(
                    ["notify-send", "--app-name=KythOS", title, body],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        elif self.have("kdialog"):
            try:
                subprocess.run(
                    ["kdialog", "--title", title, "--passivepopup", body, "12"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def print_result(self, target_name: str, custom_warn_msg: str | None = None) -> None:
        """Print summary result and exit with matching status code."""
        print()
        if self.failures > 0:
            print(f"Result: {target_name} has failures.")
            sys.exit(2)
        if self.warnings > 0:
            msg = custom_warn_msg or f"{target_name} has warnings."
            print(f"Result: {msg}")
            sys.exit(1)
        print(f"Result: {target_name} looks good.")
        sys.exit(0)
