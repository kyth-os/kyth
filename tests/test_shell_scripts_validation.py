"""Unit test verification for shell script syntax, shellcheck, and formatting."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _git_shell_files() -> list[pathlib.Path]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "*.sh"],
            cwd=ROOT,
            text=True,
        )
        files = [ROOT / line.strip() for line in out.splitlines() if line.strip()]
        return [f for f in files if f.is_file()]
    except (subprocess.SubprocessError, OSError):
        return sorted(ROOT.rglob("*.sh"))


class ShellScriptsValidationTests(unittest.TestCase):
    def test_shell_scripts_bash_syntax(self):
        shell_files = _git_shell_files()
        self.assertGreater(len(shell_files), 0, "No shell scripts found to validate")
        failed: list[str] = []
        for script in shell_files:
            rel = script.relative_to(ROOT).as_posix()
            res = subprocess.run(
                ["bash", "-n", str(script)],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                failed.append(f"{rel}:\n{res.stderr}")

        self.assertEqual(len(failed), 0, f"Bash syntax check failed for:\n" + "\n".join(failed))

    def test_shell_scripts_shellcheck(self):
        if not shutil.which("shellcheck"):
            self.skipTest("shellcheck not found in PATH")

        shell_files = _git_shell_files()
        self.assertGreater(len(shell_files), 0, "No shell scripts found to validate")
        res = subprocess.run(
            ["shellcheck", "--severity=error"] + [str(f) for f in shell_files],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"shellcheck reported errors:\n{res.stdout}\n{res.stderr}",
        )

    def test_shell_scripts_valid_header(self):
        shell_files = _git_shell_files()
        invalid_header: list[str] = []
        for script in shell_files:
            rel = script.relative_to(ROOT).as_posix()
            try:
                first_line = script.read_text(encoding="utf-8").splitlines()[0].strip()
                if not (first_line.startswith("#!") or first_line.startswith("#")):
                    invalid_header.append(rel)
            except (IndexError, UnicodeDecodeError, OSError):
                invalid_header.append(rel)

        self.assertEqual(
            len(invalid_header),
            0,
            f"Shell scripts missing comment or shebang header:\n" + "\n".join(invalid_header),
        )


if __name__ == "__main__":
    unittest.main()
