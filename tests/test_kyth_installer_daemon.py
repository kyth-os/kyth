"""Tests for the standalone root-owned installer transport service."""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files" / "kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import daemon  # noqa: E402


class InstallerDaemonTests(unittest.TestCase):
    def test_token_reader_requires_root_owned_private_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-token"
            path.write_text("A" * 43)
            with patch.object(
                daemon.os,
                "lstat",
                return_value=SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0),
            ):
                self.assertEqual(daemon._read_session_token(path), "A" * 43)

    def test_token_reader_rejects_group_readable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-token"
            path.write_text("A" * 43)
            with patch.object(
                daemon.os,
                "lstat",
                return_value=SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=0),
            ):
                with self.assertRaisesRegex(RuntimeError, "private regular file"):
                    daemon._read_session_token(path)

    def test_main_reads_token_before_constructing_service(self):
        fake_service = SimpleNamespace(serve_forever=lambda: None, server_close=lambda: None)
        with patch.object(daemon.os, "geteuid", return_value=0), \
             patch.object(daemon, "_read_session_token", return_value="A" * 43), \
             patch.object(daemon.server, "UnixSocketServer", return_value=fake_service) as make_server:
            self.assertEqual(
                daemon.main([
                    "--socket-path", "/run/kyth-installer/api.sock",
                    "--session-token-file", "/run/kyth-installer/session-token",
                    "--socket-group", "liveuser",
                    "--peer-uid", str(os.geteuid()),
                ]),
                0,
            )
        self.assertEqual(daemon.server.SESSION_TOKEN, "A" * 43)
        self.assertEqual(make_server.call_args.kwargs["socket_group"], "liveuser")
        self.assertEqual(make_server.call_args.kwargs["peer_uid"], 0)


if __name__ == "__main__":
    unittest.main()
