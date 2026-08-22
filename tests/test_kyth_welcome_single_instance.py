"""System Hub app helpers: single-instance activate payloads."""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.instance_ipc import (  # noqa: E402
    decode_activate_message,
    encode_activate_message,
    instance_server_window,
    retarget_instance_server,
)


class HubSingleInstanceMessageTests(unittest.TestCase):
    def test_encode_raise_only(self):
        self.assertEqual(encode_activate_message(None), b"show:")
        self.assertEqual(encode_activate_message(""), b"show:")

    def test_encode_with_page(self):
        self.assertEqual(encode_activate_message("Update"), b"show:Update")

    def test_decode_raise_only(self):
        self.assertIsNone(decode_activate_message(b"show:"))
        self.assertIsNone(decode_activate_message(b"show"))

    def test_decode_page(self):
        self.assertEqual(decode_activate_message(b"show:Gaming"), "Gaming")
        self.assertEqual(decode_activate_message(b"show: Update "), "Update")

    def test_decode_ignores_unrelated(self):
        self.assertIsNone(decode_activate_message(b"ping"))

    def test_retarget_swaps_the_window_pointer(self):
        server = type("Server", (), {})()
        wizard = object()
        hub = object()
        retarget_instance_server(server, wizard)
        self.assertIs(instance_server_window(server), wizard)
        retarget_instance_server(server, hub)
        self.assertIs(instance_server_window(server), hub)


if __name__ == "__main__":
    unittest.main()
