"""kyth-boot-verify and kyth-mok-rotate must check the cert secureboot.sh
actually installs, not a path nothing ever creates.

secureboot.sh installs the Kyth Secure Boot cert at
/usr/share/kyth/secureboot/kyth-secureboot.cer (and kyth-enroll-mok reads it
from the same place) — /etc/pki/kyth/secureboot.crt was never written by
anything in the build, which silently turned both scripts into permanent
no-ops.
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BOOT_VERIFY = ROOT / "build_files" / "kyth-boot-verify"
MOK_ROTATE = ROOT / "build_files" / "kyth-mok-rotate"
SECUREBOOT_SH = ROOT / "build_files" / "scripts" / "secureboot.sh"
REAL_CERT_PATH = "/usr/share/kyth/secureboot/kyth-secureboot.cer"
# Only match an actual shell assignment, not the explanatory comment above it
# describing the bug this test guards against.
ASSIGNS_STALE_PATH = re.compile(r'^\s*\w*CERT\w*="?/etc/pki/kyth/secureboot\.crt', re.MULTILINE)


class KythBootVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = BOOT_VERIFY.read_text(encoding="utf-8")

    def test_checks_the_cert_path_secureboot_sh_actually_installs(self) -> None:
        self.assertIn(f'CERT="{REAL_CERT_PATH}"', self.body)
        self.assertNotRegex(self.body, ASSIGNS_STALE_PATH)

    def test_secureboot_sh_agrees_on_the_install_path(self) -> None:
        """Guard against the two files drifting apart again."""
        source = SECUREBOOT_SH.read_text(encoding="utf-8")
        self.assertIn(REAL_CERT_PATH, source)

    def test_only_verifies_the_cachy_flavor_kernel_is_kyth_signed(self) -> None:
        """The Fedora flavor uses Fedora's own shim trust chain — never Kyth's."""
        self.assertIn('KERNEL_FLAVOR}" == "cachy"', self.body)

    def test_does_not_assume_a_uki_this_build_never_produces(self) -> None:
        self.assertNotIn("kyth.efi", self.body)
        self.assertNotIn("shimx64.efi", self.body)

    def test_documents_its_exit_code_contract(self) -> None:
        self.assertIn("exit 2", self.body)


class KythMokRotateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = MOK_ROTATE.read_text(encoding="utf-8")

    def test_checks_the_cert_path_secureboot_sh_actually_installs(self) -> None:
        self.assertIn(f'cert="{REAL_CERT_PATH}"', self.body)
        self.assertNotRegex(self.body, ASSIGNS_STALE_PATH)

    def test_does_not_enroll_unrelated_sbctl_keys_as_a_fake_rotation(self) -> None:
        """sbctl-generated keys share no key material with the Kyth MOK cert;
        enrolling them did nothing about the cert actually expiring."""
        self.assertNotIn("sbctl create-keys", self.body)
        self.assertNotIn("sbctl status", self.body)

    def test_warns_with_actionable_remediation_on_near_expiry(self) -> None:
        self.assertIn("ujust enroll-secureboot", self.body)


if __name__ == "__main__":
    unittest.main()
