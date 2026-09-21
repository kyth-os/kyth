import json
import subprocess  # nosec B404
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import setup_transfer


class SetupTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transfer = setup_transfer

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


    def test_extract_refuses_symlinks_under_files(self):
        st = self.transfer
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            payload = tmp / "payload" / st.ARCHIVE_PREFIX
            (payload / "files" / ".config").mkdir(parents=True)
            (payload / "files" / ".config" / "real").write_text("x")
            # Relative link passes tar's data filter but must still hit the
            # sweep: our exporter never writes symlinks, so any is hostile.
            (payload / "files" / ".config" / "evil").symlink_to("real")
            (payload / "manifest.json").write_text(json.dumps({
                "format": "KythOS setup transfer", "version": st.ARCHIVE_VERSION,
                "copied_paths": [], "flatpaks": [], "default_apps": {},
            }))
            archive = tmp / "link.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(tmp / "payload" / st.ARCHIVE_PREFIX, arcname=st.ARCHIVE_PREFIX)
            # Simulate what _safe_extract sees post-extract: sweep the payload.
            with self.assertRaisesRegex(ValueError, "symlink"):
                st._safe_extract(archive, tmp / "dest")

    def test_export_never_truncates_existing_archive(self):
        st = self.transfer
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            first = st.export_setup(str(dest))
            self.assertTrue(first.is_file())
            first_bytes = first.read_bytes()
            # Squat on the name the next export would take: it must bump to
            # a fresh name, never truncate this file.
            import datetime as _dt
            stamp = _dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            squat = dest / f"{st.ARCHIVE_PREFIX}-{stamp}.tar.gz"
            squat.write_bytes(b"squatted")
            second = st.export_setup(str(dest))
            # The squatted name survives untouched. Same second -> the
            # export bumps (-01); next second -> a fresh stamp name. Either
            # way nothing is truncated.
            self.assertEqual(squat.read_bytes(), b"squatted")
            self.assertTrue(second.is_file())
            self.assertTrue(second.name != squat.name or "-01.tar.gz" in second.name)

    def test_restore_flatpaks_rejects_flags_and_separates_positionals(self):
        st = self.transfer
        seen = []

        class Proc:
            stdout = iter(["ok\n"])
            def wait(self, timeout=None):
                return 0

        def fake_popen(argv, **kwargs):
            seen.append(argv)
            return Proc()

        apps = [{"id": "--help", "origin": "flathub"}, {"id": "org.example.App", "origin": "flathub"}]
        with patch.object(st.shutil, "which", return_value="/usr/bin/flatpak"), \
             patch.object(st, "_run") as mock_run, \
             patch.object(st.subprocess, "Popen", side_effect=fake_popen):
            mock_run.return_value = type("R", (), {"stdout": "flathub"})()
            ok, failed = st._restore_flatpaks(apps)
        self.assertEqual((ok, failed), (1, 1))
        self.assertEqual(len(seen), 1)
        self.assertIn("--", seen[0])

    def test_restore_defaults_allowlists_mime_and_desktop(self):
        st = self.transfer
        seen = []
        with patch.object(st, "_run", side_effect=lambda argv, **kw: seen.append(argv) or type("R", (), {"returncode": 0})()):
            n = st._restore_defaults({
                "text/plain": "org.kde.kwrite.desktop",
                "text/html": "--help",
                "evil/type": "org.kde.kwrite.desktop",
                "text/plain2": "x",
            })
        # Only the legit pair runs, with -- separating positionals.
        self.assertEqual(n, 1)
        self.assertEqual(seen, [["xdg-mime", "default", "--", "org.kde.kwrite.desktop", "text/plain"]])

    def test_export_dereferences_symlinks(self):
        st = self.transfer
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            (home / ".config").mkdir(parents=True)
            (home / ".config" / "real").write_text("data")
            (home / ".config" / "link").symlink_to("/etc/hostname")
            payload = Path(tmpdir) / "payload"
            payload.mkdir()
            with patch.object(st.Path, "home", return_value=home):
                self.assertTrue(st._copy_into_payload(home, payload, ".config/link"))
            copied = payload / "files" / ".config" / "link"
            self.assertTrue(copied.is_file())
            self.assertFalse(copied.is_symlink())


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
