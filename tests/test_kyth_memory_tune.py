"""kyth_shared.memory_tune's zram sidecar must agree with what it writes into
zram-generator.conf, and kyth-zram-swap must be able to source it directly
instead of parsing zram-generator.conf's math-expression syntax (see
build_files/scripts/branding/51-zram.sh and tests/test_kyth_boot_stability_units.py).
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import memory_tune  # noqa: E402

GB = 1024 * 1024  # /proc/meminfo-style kB per GB


class GenerateMemoryTuneZramSidecarTests(unittest.TestCase):
    """generate_memory_tune only writes zram files when dest == DEFAULT_CONF
    (the real system path) — patch that sentinel and the other real-system
    paths to a temp dir so this never touches the real /etc.
    """

    def _generate(self, mem_kb: int, tmp: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
        conf = tmp / "99-kyth-memory.conf"
        zram_conf = tmp / "zram-generator.conf"
        runtime_env = tmp / "zram-runtime.env"
        with mock.patch.object(memory_tune, "DEFAULT_CONF", conf), \
             mock.patch.object(memory_tune, "DEFAULT_ZRAM_CONF", zram_conf), \
             mock.patch.object(memory_tune, "DEFAULT_ZRAM_RUNTIME_ENV", runtime_env):
            memory_tune.generate_memory_tune(dest=conf, mem_kb=mem_kb)
        return zram_conf, runtime_env

    def test_low_tier_writes_half_ram_capped_at_8g(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zram_conf, runtime_env = self._generate(8 * GB, pathlib.Path(tmp))
            generator = zram_conf.read_text(encoding="utf-8")
            runtime = runtime_env.read_text(encoding="utf-8")

        self.assertIn("zram-size = min(ram * 0.5, 8192)", generator)
        self.assertIn("KYTH_ZRAM_PERCENT=50", runtime)
        self.assertIn("KYTH_ZRAM_CAP_MB=8192", runtime)
        self.assertIn("KYTH_ZRAM_ALGO=zstd", runtime)

    def test_mid_tier_writes_full_ram_capped_at_8g(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zram_conf, runtime_env = self._generate(20 * GB, pathlib.Path(tmp))
            generator = zram_conf.read_text(encoding="utf-8")
            runtime = runtime_env.read_text(encoding="utf-8")

        self.assertIn("zram-size = min(ram * 1.0, 8192)", generator)
        self.assertIn("KYTH_ZRAM_PERCENT=100", runtime)
        self.assertIn("KYTH_ZRAM_CAP_MB=8192", runtime)

    def test_high_tier_writes_full_ram_with_no_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zram_conf, runtime_env = self._generate(32 * GB, pathlib.Path(tmp))
            generator = zram_conf.read_text(encoding="utf-8")
            runtime = runtime_env.read_text(encoding="utf-8")

        self.assertIn("zram-size = ram\n", generator)
        self.assertIn("KYTH_ZRAM_PERCENT=100", runtime)
        self.assertIn("KYTH_ZRAM_CAP_MB=0", runtime)

    def test_not_written_for_a_non_default_test_path(self) -> None:
        """Preserve existing behavior: only the real system dest gets zram files."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            other_dest = tmp_path / "custom.conf"

            memory_tune.generate_memory_tune(dest=other_dest, mem_kb=8 * GB)

            self.assertFalse((tmp_path / "zram-generator.conf").exists())


if __name__ == "__main__":
    unittest.main()
