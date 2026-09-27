import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer import validation
from kyth_installer.validation import InstallRequestError
from kyth_installer import server as server_mod


class ValidationGapTests2(unittest.TestCase):
    def test_hostname_and_username(self):
        with self.assertRaisesRegex(InstallRequestError, "Invalid hostname"):
            validation._require_valid_hostname("bad hostname!")
        with self.assertRaisesRegex(InstallRequestError, "Invalid username"):
            validation._require_valid_username("Bad User!")

    def test_disk_and_mode(self):
        with self.assertRaisesRegex(InstallRequestError, "Invalid disk"):
            validation.validate_install_request({"disk": "", "install_mode": "wipe", "hostname": "kyth", "username": "test"}, mock.Mock())


class ServerGapTests2(unittest.TestCase):
    def test_server_branches(self):
        h = server_mod.Handler.__new__(server_mod.Handler)
        h.server = mock.Mock(context=None)
        with self.assertRaisesRegex(RuntimeError, "no runtime context"):
            _ = h.context
        h2 = server_mod.Handler.__new__(server_mod.Handler)
        h2.headers = {"Cookie": f"bootstrap_auth={server_mod.SESSION_TOKEN}"}
        h2.send_error = mock.Mock()
        self.assertTrue(h2._require_auth())
        self.assertTrue(server_mod.Handler._is_trusted_local_url(f"http://127.0.0.1:{server_mod.PORT}/"))
        self.assertFalse(server_mod.Handler._is_trusted_local_url("http://evil.com/"))


if __name__ == "__main__":
    unittest.main()
