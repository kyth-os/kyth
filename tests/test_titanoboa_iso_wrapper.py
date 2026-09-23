"""Live ISO: Titanoboa must still see iso.yaml when /usr is ostree-hidden."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "build_files/scripts/titanoboa-iso-wrapper.sh"
ISO = ROOT / "installer/iso.yaml"
LIVE = ROOT / "build_files/build-live-iso.sh"


class TitanoboaIsoWrapperTests(unittest.TestCase):
    def test_wrapper_falls_back_to_bind_mounted_iso_yaml(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("/kyth/iso.yaml", text)
        self.assertIn("iso_config_file=/rootfs/usr/lib/bootc-image-builder/iso.yaml", text)
        self.assertTrue(ISO.is_file())
        live = LIVE.read_text(encoding="utf-8")
        self.assertIn("titanoboa-iso-wrapper.sh:/src/build_iso.sh", live)
        self.assertIn("installer/iso.yaml:/kyth/iso.yaml", live)


if __name__ == "__main__":
    unittest.main()
