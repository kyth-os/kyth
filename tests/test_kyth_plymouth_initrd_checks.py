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

    def test_crypt_generator_uses_exit_not_return(self):
        """dracut 111's crypt-generator.sh is executed, so top-level `return` is exit 2."""
        shipped = (
            "#!/usr/bin/sh\n\ncommand -v getargbool > /dev/null || . /lib/dracut-lib.sh\n\n"
            "if ! getargbool 1 rd.luks; then\n"
            "    # crypto LUKS detection is disabled\n"
            "    return 0\n"
            "fi\n\n"
            "[ -e /etc/crypttab ] || return 0\n\n"
            'GENERATOR_DIR="$1"\n'
            '[ -n "$GENERATOR_DIR" ] || return 1\n'
            'f() {\n    return 0\n}\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            script = root / "usr/lib/dracut/modules.d/70crypt/crypt-generator.sh"
            script.parent.mkdir(parents=True)
            script.write_text(shipped, encoding="utf-8")
            env = {**os.environ, "KYTH_PLYMOUTH_ROOT": str(root)}
            subprocess.run([str(OWNER)], env=env, check=True)
            once = script.read_text(encoding="utf-8")
            subprocess.run([str(OWNER)], env=env, check=True)
            twice = script.read_text(encoding="utf-8")
            self.assertEqual(once, twice, "must be idempotent")
            self.assertIn("[ -e /etc/crypttab ] || exit 0", once)
            self.assertIn('[ -n "$GENERATOR_DIR" ] || exit 1', once)
            self.assertIn("    exit 0\nfi", once)
            # A real function body keeps its `return`.
            self.assertIn("f() {\n    return 0\n}", once)
            # The patched script must actually run clean when executed (no crypttab).
            gen = pathlib.Path(tmp) / "gen.sh"
            gen.write_text(once.replace("command -v getargbool > /dev/null || . /lib/dracut-lib.sh",
                                        "getargbool() { return 0; }"), encoding="utf-8")
            result = subprocess.run(["bash", str(gen), tempfile.gettempdir()], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

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


class PlymouthBootImageSyncTests(unittest.TestCase):
    """The verified build must reach the images the boot chain actually reads.

    Regression pin: plymouth-initramfs.sh verified only the ostree-convention
    /usr/lib/modules/<kver>/initramfs while bootc boots the initramfs.img
    lineage, so a stale stock copy (Fedora spinner watermark included)
    shipped in early boot with the gate green.
    """

    SCRIPT = ROOT / "build_files" / "scripts" / "plymouth-initramfs.sh"

    def test_verified_build_syncs_to_bootc_boot_images(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("/usr/lib/modules/${KVER}/initramfs.img", text)
        self.assertIn("/boot/initramfs-${KVER}.img", text)

    def test_synced_copies_are_byte_verified(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("cmp -s", text)
        self.assertIn("failed to sync", text)

    def test_sync_runs_after_verification_not_before(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_branded_initramfs", text)
        self.assertLess(
            text.index("verify_branded_initramfs"),
            text.index("initramfs.img"),
            "boot images must be synced from the verified build, not rebuilt separately",
        )


if __name__ == "__main__":
    unittest.main()
