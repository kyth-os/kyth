"""Unit tests for the shared configuration module."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import config


class ConfigTests(unittest.TestCase):
    def test_load_toml_config_missing_file(self):
        defaults = {"a": 1, "b": "default"}
        res = config.load_toml_config("missing.toml", default_config=defaults)
        self.assertEqual(res, defaults)

    @mock.patch("pathlib.Path.is_file")
    @mock.patch("builtins.open", new_callable=mock.mock_open, read_data=b"a = 2\nc = 3")
    def test_load_toml_config_exists(self, mock_file, mock_is_file):
        mock_is_file.return_value = True
        defaults = {"a": 1, "b": "default"}
        res = config.load_toml_config("test.toml", default_config=defaults)
        self.assertEqual(res, {"a": 2, "b": "default", "c": 3})

    @mock.patch("pathlib.Path.is_file")
    @mock.patch("builtins.open", new_callable=mock.mock_open, read_data=b"[section]\na = 2\nc = 3")
    def test_load_toml_config_with_section(self, mock_file, mock_is_file):
        mock_is_file.return_value = True
        defaults = {"a": 1, "b": "default"}
        res = config.load_toml_config("test.toml", default_config=defaults, section_name="section")
        self.assertEqual(res, {"a": 2, "b": "default", "c": 3})


if __name__ == "__main__":
    unittest.main()
