"""Behavioral tests for the KythOS developer and AI container CLI."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.ai_dev import AiDev, Config, DEFAULT_IMAGE, DEFAULT_MODEL, build_parser


class AiDevTests(unittest.TestCase):
    def test_config_uses_environment_overrides(self) -> None:
        config = Config.from_environment({
            "HOME": "/home/tester",
            "KYTH_AI_DEV_BOX": "custom",
            "KYTH_AI_MODEL_DIR": "/models",
        })
        self.assertEqual(config.box, "custom")
        self.assertEqual(config.image, DEFAULT_IMAGE)
        self.assertEqual(config.model_dir, pathlib.Path("/models"))

    def test_default_model_is_parsed(self) -> None:
        args = build_parser().parse_args(["pull-model"])
        self.assertEqual(args.command, "pull-model")
        self.assertEqual(args.model, DEFAULT_MODEL)

    def test_enter_command_never_uses_a_shell(self) -> None:
        app = AiDev(Config("box", "image", pathlib.Path("/models")))
        self.assertEqual(
            app.enter_command("node", "--version"),
            ["distrobox", "enter", "box", "--", "node", "--version"],
        )

    def test_create_command_maps_nvidia(self) -> None:
        app = AiDev(Config("box", "image", pathlib.Path("/models")))
        with mock.patch.object(app, "gpu_kind", return_value="nvidia"):
            command = app.create_command()
        self.assertIn("--nvidia", command)
        self.assertIn("/models:/models:rw", command)

    def test_create_command_maps_amd_devices(self) -> None:
        app = AiDev(Config("box", "image", pathlib.Path("/models")))
        with mock.patch.object(app, "gpu_kind", return_value="amd"):
            command = app.create_command()
        flags = command[command.index("--additional-flags") + 1]
        self.assertIn("--device=/dev/kfd", flags)
        self.assertIn("--device=/dev/dri", flags)

    def test_missing_distrobox_is_an_expected_error(self) -> None:
        app = AiDev(
            Config("box", "image", pathlib.Path("/models")),
            which=lambda _command: None,
        )
        with self.assertRaisesRegex(RuntimeError, "distrobox is not installed"):
            app.require_distrobox()


if __name__ == "__main__":
    unittest.main()
