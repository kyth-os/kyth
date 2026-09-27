"""Behavioral checks for build-time third-party archive extraction."""
from __future__ import annotations

import io
import pathlib
import subprocess
import tarfile
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMON = ROOT / "build_files/scripts/lib/thirdparty-common.sh"


def _extract(archive: pathlib.Path, destination: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; safe_extract_tar "$2" "$3"',
            "bash",
            str(COMMON),
            str(archive),
            str(destination),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


class ThirdPartyArchiveSecurityTests(unittest.TestCase):
    def test_extracts_regular_files_into_new_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            archive = root / "safe.tar"
            with tarfile.open(archive, "w") as bundle:
                info = tarfile.TarInfo("package/tool")
                payload = b"trusted after digest verification"
                info.size = len(payload)
                bundle.addfile(info, io.BytesIO(payload))

            destination = root / "output"
            result = _extract(archive, destination)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((destination / "package/tool").read_bytes(), payload)

    def test_rejects_path_traversal_without_writing_outside(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            archive = root / "traversal.tar"
            with tarfile.open(archive, "w") as bundle:
                info = tarfile.TarInfo("../outside")
                info.size = 3
                bundle.addfile(info, io.BytesIO(b"bad"))

            result = _extract(archive, root / "output")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "outside").exists())

    def test_rejects_symlinks_that_escape_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            archive = root / "link.tar"
            with tarfile.open(archive, "w") as bundle:
                info = tarfile.TarInfo("package/link")
                info.type = tarfile.SYMTYPE
                info.linkname = "../../outside"
                bundle.addfile(info)

            result = _extract(archive, root / "output")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "output/package/link").exists())


if __name__ == "__main__":
    unittest.main()
