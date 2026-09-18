"""Session/bootstrap token handoff: 0600 file or pipe fd, never argv or URL."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer import app  # noqa: E402

BOOTSTRAP = "boot-token_ABC123"
SESSION = "session-token_DEF456"


class ChildTokenFileTests(unittest.TestCase):
    def test_child_tokens_are_0600_json_without_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "child-tokens.json"
            app._write_child_tokens(
                path, bootstrap_token=BOOTSTRAP, session_token=SESSION,
            )
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600)
            payload = json.loads(path.read_text(encoding="ascii"))
            self.assertEqual(
                payload, {"bootstrap_token": BOOTSTRAP, "session_token": SESSION}
            )

    def test_child_tokens_refuse_symlinks_and_empty_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.json"
            real.write_text("{}")
            link = Path(tmp) / "link.json"
            os.symlink(real, link)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                app._write_child_tokens(
                    link, bootstrap_token=BOOTSTRAP, session_token=SESSION,
                )
            with self.assertRaises(ValueError):
                app._write_child_tokens(
                    Path(tmp) / "empty.json", bootstrap_token="", session_token=SESSION,
                )

    def test_chromium_launcher_is_0600_and_carries_no_argv_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "launcher.html"
            app._write_chromium_launcher(path, port=7777, bootstrap_token=BOOTSTRAP)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            body = path.read_text(encoding="utf-8")
            self.assertIn(BOOTSTRAP, body)
            self.assertIn("http://127.0.0.1:7777/", body)


class ChildGuiCommandTests(unittest.TestCase):
    def test_shell_command_uses_tokens_file_without_secrets(self):
        cmd = app._child_gui_command(
            installer_shell="/usr/bin/kyth-installer-shell",
            chromium_bin="chromium",
            tokens_file="/run/kyth-installer/child-tokens.json",
            launcher_file="/run/kyth-installer/launcher.html",
            socket_path="/run/kyth-installer/api.sock",
        )
        self.assertEqual(
            cmd,
            ["/usr/bin/kyth-installer-shell", "--tokens-file",
             "/run/kyth-installer/child-tokens.json",
             "--socket-path", "/run/kyth-installer/api.sock"],
        )
        for secret in (BOOTSTRAP, SESSION):
            self.assertFalse(any(secret in part for part in cmd))

    def test_chromium_command_uses_file_launcher_without_token_url(self):
        cmd = app._child_gui_command(
            installer_shell=None,
            chromium_bin="chromium",
            tokens_file="/run/kyth-installer/child-tokens.json",
            launcher_file="/run/kyth-installer/launcher.html",
            socket_path=None,
        )
        self.assertEqual(cmd[0], "chromium")
        self.assertIn("--app=file:///run/kyth-installer/launcher.html", cmd)
        self.assertFalse(any("bootstrap_token=" in part for part in cmd))
        self.assertFalse(any("session-token" in part for part in cmd))

    def test_build_writes_material_and_never_embeds_secrets_in_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tokens_file = str(Path(tmp) / "child-tokens.json")
            launcher_file = str(Path(tmp) / "launcher.html")
            with mock.patch.object(app.config, "_bootstrap_token", BOOTSTRAP), \
                 mock.patch.object(app, "SESSION_TOKEN", SESSION), \
                 mock.patch.object(app, "SOCKET_PATH", None), \
                 mock.patch.object(app.shutil, "which", return_value="/usr/bin/kyth-installer-shell"):
                cmd, wrote = app._build_child_gui_command(
                    installer_shell="/usr/bin/kyth-installer-shell",
                    tokens_file=tokens_file,
                    launcher_file=launcher_file,
                    child_uid=None,
                )
            self.assertEqual(wrote, (True, False))
            self.assertIn("--tokens-file", cmd)
            self.assertNotIn("--bootstrap-token", cmd)
            self.assertNotIn("--session-token", cmd)
            for secret in (BOOTSTRAP, SESSION):
                self.assertFalse(any(secret in part for part in cmd))
            stored = json.loads(Path(tokens_file).read_text(encoding="ascii"))
            self.assertEqual(stored["bootstrap_token"], BOOTSTRAP)
            self.assertEqual(stored["session_token"], SESSION)
            self.assertEqual(stat.S_IMODE(os.stat(tokens_file).st_mode), 0o600)

    def test_build_chromium_fallback_writes_launcher_not_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            tokens_file = str(Path(tmp) / "child-tokens.json")
            launcher_file = str(Path(tmp) / "launcher.html")
            with mock.patch.object(app.config, "_bootstrap_token", BOOTSTRAP), \
                 mock.patch.object(app, "SESSION_TOKEN", SESSION), \
                 mock.patch.object(app, "SOCKET_PATH", None), \
                 mock.patch.object(app.shutil, "which", return_value=None):
                cmd, wrote = app._build_child_gui_command(
                    installer_shell=None,
                    tokens_file=tokens_file,
                    launcher_file=launcher_file,
                    child_uid=None,
                )
            self.assertEqual(wrote, (False, True))
            self.assertFalse(any("bootstrap_token=" in part for part in cmd))
            self.assertFalse(any(BOOTSTRAP in part for part in cmd))
            self.assertIn(BOOTSTRAP, Path(launcher_file).read_text(encoding="utf-8"))
            self.assertFalse(Path(tokens_file).exists())

    def test_build_refuses_socket_mode_without_native_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(app.config, "_bootstrap_token", BOOTSTRAP), \
                 mock.patch.object(app, "SOCKET_PATH", Path("/run/kyth-installer/api.sock")):
                with self.assertRaisesRegex(RuntimeError, "kyth-installer-native"):
                    app._build_child_gui_command(
                        installer_shell=None,
                        tokens_file=str(Path(tmp) / "child-tokens.json"),
                        launcher_file=str(Path(tmp) / "launcher.html"),
                        child_uid=None,
                    )


if __name__ == "__main__":
    unittest.main()
