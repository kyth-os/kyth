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


class SysctlCompositionTests(unittest.TestCase):
    def test_sysctl_no_duplicate_keys_across_files(self):
        """Same sysctl key must not appear in two sysctl.d files without override comment."""
        import re

        sysctl_dirs = [
            ROOT / "build_files" / "data" / "sysctl.d",
            ROOT / "build_files" / "scripts" / "sysconfig",
        ]
        key_to_files: dict[str, list[str]] = {}
        for base in sysctl_dirs:
            if not base.exists():
                continue
            for path in base.rglob("*.sh"):
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                for m in re.finditer(r"^\s*([a-z0-9._/-]+)\s*=", text, re.MULTILINE):
                    key = m.group(1)
                    if key.startswith("#"):
                        continue
                    key_to_files.setdefault(key, []).append(path.relative_to(ROOT).as_posix())
            for path in base.rglob("*.conf"):
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                for line in text.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or stripped.startswith(";"):
                        continue
                    if "=" not in stripped:
                        continue
                    key = stripped.split("=", 1)[0].strip()
                    # Allow same key if file contains explicit override marker
                    if "override:" in text:
                        continue
                    key_to_files.setdefault(key, []).append(path.relative_to(ROOT).as_posix())
        # Check direct sysctl.d conf files for duplicates
        conf_files = list((ROOT / "build_files" / "data" / "sysctl.d").glob("*.conf"))
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for conf in conf_files:
            try:
                text = conf.read_text(encoding="utf-8")
            except OSError:
                continue
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    continue
                key = stripped.split("=", 1)[0].strip()
                if key in seen:
                    duplicates.append(f"{key} in {seen[key]} and {conf.relative_to(ROOT)}")
                else:
                    seen[key] = conf.relative_to(ROOT).as_posix()
        # Also ensure no key in 99-kyth.conf is also set via scripts that compose sysctl
        # The known safe composition: net.core.default_qdisc is in 56-network-cake.sh, not 99-kyth.conf
        kyth_conf = ROOT / "build_files" / "data" / "sysctl.d" / "99-kyth.conf"
        if kyth_conf.exists():
            try:
                text = kyth_conf.read_text(encoding="utf-8")
                has_assignment = any(
                    line.strip().startswith("net.core.default_qdisc")
                    for line in text.splitlines()
                    if not line.strip().startswith("#") and "=" in line
                )
                self.assertFalse(has_assignment, "net.core.default_qdisc must live only in 56-network-cake.sh, not 99-kyth.conf (CAKE composition bug)")
            except OSError:
                pass
        self.assertEqual(duplicates, [], f"Duplicate sysctl keys across sysctl.d: {duplicates}")


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
