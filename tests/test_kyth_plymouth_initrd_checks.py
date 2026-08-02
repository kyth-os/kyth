"""Behavioral tests for the shared Plymouth-initramfs assertion primitives.

installer/build.sh, scripts/plymouth-initramfs.sh, and
scripts/repair-current-plymouth-initramfs.sh each verify a built initramfs
actually contains the branded KythOS Plymouth theme. They share
scripts/lib/plymouth-initrd-checks.sh for the repeated "pattern present/
absent, or exact byte match, or die with a message" primitives. This can't
exercise the real dracut/lsinitrd integration, but the primitives themselves
are plain grep/cmp wrappers and are fully testable against plain files.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest
import os

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / "build_files" / "scripts" / "lib" / "plymouth-initrd-checks.sh"
OWNER = ROOT / "build_base" / "plymouth" / "kyth-plymouth-configure"


def _run(function_call: str, *, cwd: pathlib.Path) -> subprocess.CompletedProcess:
    script = f'set -euo pipefail\nsource "{LIB}"\n{function_call}\n'
    return subprocess.run(
        ["bash", "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class PlymouthInitrdChecksTests(unittest.TestCase):
    def test_canonical_configuration_owner_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            env = {**os.environ, "KYTH_PLYMOUTH_ROOT": str(root)}
            subprocess.run([str(OWNER)], env=env, check=True)
            first = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            subprocess.run([str(OWNER)], env=env, check=True)
            second = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }

        self.assertEqual(first, second)
        daemon = subprocess.run(
            [str(OWNER), "--print-daemon-config"], capture_output=True, text=True, check=True,
        ).stdout
        self.assertEqual(first["etc/plymouth/plymouthd.conf"].decode(), daemon)
        self.assertIn(b'force_add_dracutmodules+=" kyth-plymouth "', first["etc/dracut.conf.d/99-kyth.conf"])

    def test_every_entry_point_delegates_to_canonical_owner(self):
        base = (ROOT / "build_base" / "build.sh").read_text(encoding="utf-8")
        setup = (ROOT / "build_files" / "scripts" / "plymouth-setup.sh").read_text(encoding="utf-8")
        guard = (ROOT / "build_files" / "scripts" / "plymouth-branding-guard.sh").read_text(encoding="utf-8")
        branding = (
            ROOT / "build_files" / "scripts" / "branding"
            / "28-bootc-kernel-arguments-and-boot-splash.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("/run/plymouth/kyth-plymouth-configure", base)
        self.assertIn("/usr/libexec/kyth-plymouth-configure", setup)
        self.assertIn("KYTH_PLYMOUTH_CONFIGURE", guard)
        self.assertIn("kyth-plymouth-branding-guard", branding)
        for non_owner in (base, setup, guard, branding):
            self.assertNotIn('cat >/etc/dracut.conf.d/99-kyth.conf', non_owner)

    def test_lib_parses_as_bash(self):
        subprocess.run(["bash", "-n", str(LIB)], check=True)

    def test_require_pattern_passes_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            listing = tmp / "listing"
            listing.write_text("usr/share/plymouth/themes/kyth/kyth.plymouth\n")
            result = _run(
                f'plymouth_require_pattern "{listing}" "kyth.plymouth" "should not fire"',
                cwd=tmp,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_require_pattern_fails_with_message_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            listing = tmp / "listing"
            listing.write_text("usr/share/plymouth/themes/bgrt/bgrt.plymouth\n")
            result = _run(
                f'plymouth_require_pattern "{listing}" "kyth.plymouth" "missing branded theme"',
                cwd=tmp,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR: missing branded theme", result.stderr)

    def test_require_pattern_ere_supports_extended_regex(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            listing = tmp / "listing"
            listing.write_text("usr/lib64/plymouth/script.so\n")
            result = _run(
                f'plymouth_require_pattern_ere "{listing}" '
                f'\'usr/(lib64|lib)/plymouth/script\\.so\' "missing script.so"',
                cwd=tmp,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_require_match_passes_for_identical_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            lhs = tmp / "lhs"
            rhs = tmp / "rhs"
            lhs.write_bytes(b"same-bytes")
            rhs.write_bytes(b"same-bytes")
            result = _run(
                f'plymouth_require_match "{lhs}" "{rhs}" "should not fire"',
                cwd=tmp,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_require_match_fails_for_different_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            lhs = tmp / "lhs"
            rhs = tmp / "rhs"
            lhs.write_bytes(b"kyth-logo")
            rhs.write_bytes(b"distro-logo")
            result = _run(
                f'plymouth_require_match "{lhs}" "{rhs}" "logo mismatch"',
                cwd=tmp,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR: logo mismatch", result.stderr)

    def test_forbid_fallback_theme_passes_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            listing = tmp / "listing"
            listing.write_text("usr/share/plymouth/themes/kyth/kyth.plymouth\n")
            result = _run(
                f'plymouth_forbid_fallback_theme "{listing}" "should not fire"',
                cwd=tmp,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_forbid_fallback_theme_fails_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            listing = tmp / "listing"
            listing.write_text("usr/share/plymouth/themes/bgrt-fedora/bgrt-fedora.plymouth\n")
            result = _run(
                f'plymouth_forbid_fallback_theme "{listing}" "fallback theme leaked"',
                cwd=tmp,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR: fallback theme leaked", result.stderr)


if __name__ == "__main__":
    unittest.main()
