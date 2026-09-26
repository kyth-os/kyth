"""Live ISO: Titanoboa must still see iso.yaml when /usr is ostree-hidden."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "build_files/scripts/titanoboa-iso-wrapper.sh"
ISO = ROOT / "installer/iso.yaml"
LIVE = ROOT / "build_files/build-live-iso.sh"
WORKFLOW = ROOT / ".github/workflows/build-live-iso.yml"
VENDORED = ROOT / "build_files/titanoboa/build_iso.sh"


class TitanoboaIsoWrapperTests(unittest.TestCase):
    def test_local_registry_with_port_uses_local_image_path(self) -> None:
        live = LIVE.read_text(encoding="utf-8")
        self.assertIn('"${BASE_IMAGE}" == localhost:*/*', live)
        self.assertIn('[[ "${IS_LOCAL_IMAGE}" == true ]] && pull_flag=()', live)
        self.assertIn('if [[ "${IS_LOCAL_IMAGE}" == true ]]; then', live)

    def test_wrapper_falls_back_to_bind_mounted_iso_yaml(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("/kyth/iso.yaml", text)
        self.assertIn("iso_config_file=/rootfs/usr/lib/bootc-image-builder/iso.yaml", text)
        self.assertTrue(ISO.is_file())
        live = LIVE.read_text(encoding="utf-8")
        self.assertIn("titanoboa-iso-wrapper.sh:/src/build_iso.sh", live)
        self.assertIn("installer/iso.yaml:/kyth/iso.yaml", live)

    def test_ci_iso_build_uses_the_wrapper_not_the_unmountable_action(self) -> None:
        # The upstream action accepts no volume mounts, so its
        # hard-required /rootfs/usr/lib/bootc-image-builder/iso.yaml can
        # never see the fallback — every testing ISO build died there. CI
        # must run Titanoboa directly with the same mounts as the local
        # live-ISO script.
        yml = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("uses: Zeglius/titanoboa", yml)
        self.assertIn("build_files/titanoboa/build_iso.sh:/src/titanoboa-build_iso.sh:ro", yml)
        self.assertIn("build_files/scripts/titanoboa-iso-wrapper.sh:/src/build_iso.sh:ro", yml)
        self.assertIn("installer/iso.yaml:/kyth/iso.yaml:ro", yml)
        self.assertIn("kyth-live-${SOURCE_TAG}.iso", yml)
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("TITANOBOA_ISO:-/src/titanoboa-build_iso.sh", wrapper)
        self.assertIn("KYTH_ISO:-/kyth/iso.yaml", wrapper)

    def test_vendored_build_iso_matches_the_pinned_upstream_contract(self) -> None:
        vendored = VENDORED.read_text(encoding="utf-8")
        self.assertIn("Zeglius/titanoboa @ 7737f47", vendored)
        self.assertIn("iso_config_file=/rootfs/usr/lib/bootc-image-builder/iso.yaml", vendored)
        self.assertIn('mksquashfs /rootfs', vendored)
        self.assertIn('-o "/output/$iso_label.iso"', vendored)


if __name__ == "__main__":
    unittest.main()
