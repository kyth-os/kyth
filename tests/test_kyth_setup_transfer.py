import importlib.util
from importlib.machinery import SourceFileLoader
import json
import subprocess  # nosec B404
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tarfile
import tempfile


def _load_setup_transfer():
    path = Path(__file__).resolve().parents[1] / "build_files" / "kyth-setup-transfer"
    loader = SourceFileLoader("kyth_setup_transfer", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetupTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transfer = _load_setup_transfer()

    @patch("subprocess.run")
    def test_installed_flatpaks_parsing(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["flatpak"],
            returncode=0,
            stdout="com.valvesoftware.Steam\tflathub\norg.inkscape.Inkscape\tflathub-user\n",
            stderr=""
        )
        flatpaks = self.transfer._installed_flatpaks()
        self.assertEqual(len(flatpaks), 2)
        self.assertEqual(flatpaks[0]["id"], "com.valvesoftware.Steam")
        self.assertEqual(flatpaks[0]["origin"], "flathub")
        self.assertEqual(flatpaks[1]["id"], "org.inkscape.Inkscape")
        self.assertEqual(flatpaks[1]["origin"], "flathub-user")

    @patch("subprocess.run")
    def test_default_apps(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["xdg-mime"],
            returncode=0,
            stdout="org.mozilla.firefox.desktop\n",
            stderr=""
        )
        defaults = self.transfer._default_apps()
        self.assertIn("text/html", defaults)
        self.assertEqual(defaults["text/html"], "org.mozilla.firefox.desktop")

    def test_is_allowed_restore_path(self):
        # Valid config paths
        self.assertTrue(self.transfer._is_allowed_restore_path(".config/kdeglobals"))
        self.assertTrue(self.transfer._is_allowed_restore_path(".config/MangoHud"))
        # Valid desktop files
        self.assertTrue(self.transfer._is_allowed_restore_path(".local/share/applications/kyth-test.desktop"))
        # Invalid paths
        self.assertFalse(self.transfer._is_allowed_restore_path("/etc/passwd"))
        self.assertFalse(self.transfer._is_allowed_restore_path("~/.bashrc"))
        self.assertFalse(self.transfer._is_allowed_restore_path("../etc/passwd"))
        self.assertFalse(self.transfer._is_allowed_restore_path(".local/share/applications/normal.desktop"))

    @patch("subprocess.run")
    def test_export_setup(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr=""
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock home directory structure
            home_dir = Path(tmpdir) / "home"
            home_dir.mkdir()
            
            # Write a dummy config file
            dummy_config = home_dir / ".config" / "kdeglobals"
            dummy_config.parent.mkdir(parents=True, exist_ok=True)
            dummy_config.write_text("dummy-kde-settings", encoding="utf-8")

            # Mock Path.home() to return our temp home directory
            with patch.object(Path, "home", return_value=home_dir):
                archive = self.transfer.export_setup(str(home_dir / "backup"))
                
                self.assertTrue(archive.exists())
                self.assertTrue(tarfile.is_tarfile(archive))
                
                # Check tar file contents
                with tarfile.open(archive, "r:gz") as tar:
                    members = {m.name for m in tar.getmembers()}
                    self.assertIn("kyth-setup/manifest.json", members)
                    self.assertIn("kyth-setup/files/.config/kdeglobals", members)
                    
                    # Read manifest
                    manifest_file = tar.extractfile("kyth-setup/manifest.json")
                    self.assertIsNotNone(manifest_file)
                    manifest = json.loads(manifest_file.read().decode("utf-8"))
                    self.assertEqual(manifest["format"], "KythOS setup transfer")
                    self.assertEqual(manifest["version"], 1)
                    self.assertIn(".config/kdeglobals", manifest["copied_paths"])

    def test_safe_extract_prevents_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "unsafe.tar.gz"
            # Create a tar file containing an unsafe path
            with tarfile.open(archive_path, "w:gz") as tar:
                # Add an entry that attempts path traversal outside the extraction root
                ti = tarfile.TarInfo(name="../outside.txt")
                ti.size = 12
                tar.addfile(ti, fileobj=BytesIO(b"unsafe_content"))

            dest_path = Path(tmpdir) / "extract"
            dest_path.mkdir()

            with self.assertRaises(ValueError) as ctx:
                self.transfer._safe_extract(archive_path, dest_path)
            self.assertIn("Unsafe archive path", str(ctx.exception))


class BytesIO(MagicMock):
    """Helper for mocking tarball files."""
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.offset = 0

    def read(self, size=-1):
        if size < 0:
            res = self.data[self.offset:]
            self.offset = len(self.data)
            return res
        res = self.data[self.offset:self.offset+size]
        self.offset += size
        return res


if __name__ == "__main__":
    unittest.main()
