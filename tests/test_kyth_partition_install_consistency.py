import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTITION_SCRIPT = ROOT / "build_files" / "kyth-partition-install.sh"
INSTALLER_ROOT = ROOT / "build_files" / "kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer.validation import HOSTNAME_PATTERN

# (hostname, expected valid) — shared by both the bash CLI installer and the
# graphical installer's regex.
HOSTNAME_CASES = [
    ("kyth", True),
    ("a", True),
    ("my-host1", True),
    ("A0-z9", True),
    ("x" * 63, True),
    ("x" * 64, False),
    ("", False),
    ("-kyth", False),
    ("kyth-", False),
    ("kyth_host", False),
    ("kyth.host", False),
    ("kyth host", False),
]


class HostnameValidationConsistencyTests(unittest.TestCase):
    """kyth-partition-install.sh (the bash dual-boot CLI installer) and
    the graphical installer each validate hostnames with
    their own regex literal — there is no shared source of truth across the
    bash/Python boundary. These tests catch the two silently drifting apart
    rather than asserting the literal strings stay byte-identical, since the
    same character class can legitimately be spelled differently in POSIX
    ERE vs Python re.
    """

    def _bash_pattern(self) -> str:
        text = PARTITION_SCRIPT.read_text()
        match = re.search(r'\[\[ ! "\$HOSTNAME" =~ \^(.+)\$ \]\]', text)
        self.assertIsNotNone(match, "could not locate hostname regex in kyth-partition-install.sh")
        return f"^{match.group(1)}$"

    def test_hostname_regexes_agree(self):
        bash_re = re.compile(self._bash_pattern())
        for hostname, expected_valid in HOSTNAME_CASES:
            with self.subTest(hostname=hostname):
                self.assertEqual(bool(bash_re.fullmatch(hostname)), expected_valid)
                self.assertEqual(bool(HOSTNAME_PATTERN.fullmatch(hostname)), expected_valid)


if __name__ == "__main__":
    unittest.main()
