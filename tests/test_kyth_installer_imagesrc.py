import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import imagesrc  # noqa: E402


class InstallerImageSourceTests(unittest.TestCase):
    def test_network_preflight_skips_local_images(self):
        with mock.patch.object(imagesrc, "run_command") as run_command, \
             mock.patch.object(imagesrc.socket, "create_connection") as create_connection:
            result = imagesrc._network_preflight("containers-storage:localhost/kyth")

        self.assertIsNone(result)
        run_command.assert_not_called()
        create_connection.assert_not_called()

    def test_oci_layout_is_preserved_as_an_offline_source(self):
        source = "oci:/usr/share/kyth/image:latest"

        self.assertEqual(imagesrc._source_imgref(source), source)
        self.assertIsNone(imagesrc._network_preflight(source))

    def test_network_preflight_reports_missing_default_route(self):
        with mock.patch.object(imagesrc.socket, "getaddrinfo", return_value=[]), \
             mock.patch.object(imagesrc.socket, "create_connection", side_effect=OSError("network unreachable")):

            result = imagesrc._network_preflight("docker://ghcr.io/mrtrick37/kyth:latest")

        self.assertIsInstance(result, str)
        self.assertIn("Connect", result)

    def test_install_images_returns_source_and_target_refs(self):
        image = "ghcr.io/mrtrick37/kyth:testing"
        with mock.patch.object(imagesrc, "run_command") as run_command, \
             mock.patch.object(imagesrc, "SOURCE_IMAGE", image), \
             mock.patch.object(imagesrc, "TARGET_IMAGE", image):
            src, tgt = imagesrc._install_images("fedora")

        self.assertTrue(src.startswith("docker://"))
        self.assertEqual(tgt, "ghcr.io/mrtrick37/kyth:testing")
        self.assertEqual(src, f"docker://{tgt}")
        run_command.assert_not_called()

    def test_source_imgref_empty_input_uses_default_source_image(self):
        self.assertEqual(imagesrc._source_imgref(""), imagesrc.SOURCE_IMAGE)


if __name__ == "__main__":
    unittest.main()
