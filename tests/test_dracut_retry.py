from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


RETRY_SCRIPT = Path(__file__).parents[1] / "build_files/scripts/lib/dracut-retry.sh"


class DracutRetryTests(unittest.TestCase):
    def _run(self, dracut_body: str) -> tuple[subprocess.CompletedProcess[str], int, bool]:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            counter = root / "counter"
            output = root / "initramfs"
            dracut = bin_dir / "dracut"
            dracut.write_text(
                "#!/bin/bash\n"
                f"counter={counter!s}\n"
                'count=$(cat "$counter" 2>/dev/null || echo 0)\n'
                'count=$((count + 1))\n'
                'printf "%s" "$count" >"$counter"\n'
                'output="${@: -1}"\n'
                f"{dracut_body}\n",
                encoding="utf-8",
            )
            dracut.chmod(0o755)
            lsinitrd = bin_dir / "lsinitrd"
            lsinitrd.write_text(
                '#!/bin/bash\ngrep -qx valid "$1"\n',
                encoding="utf-8",
            )
            lsinitrd.chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; kyth_build_initramfs "$2" --no-hostonly',
                    "dracut-retry-test",
                    str(RETRY_SCRIPT),
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            return result, int(counter.read_text(encoding="utf-8")), output.exists()

    def test_retries_a_segmentation_fault_from_a_clean_output(self) -> None:
        result, attempts, output_exists = self._run(
            'if ((count == 1)); then printf partial >"$output"; exit 139; fi\n'
            'printf "valid\\n" >"$output"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(attempts, 2)
        self.assertTrue(output_exists)
        self.assertIn("Retrying initramfs generation", result.stderr)

    def test_removes_output_after_both_attempts_fail(self) -> None:
        result, attempts, output_exists = self._run(
            'printf partial >"$output"\nexit 139',
        )

        self.assertEqual(result.returncode, 139)
        self.assertEqual(attempts, 2)
        self.assertFalse(output_exists)


if __name__ == "__main__":
    unittest.main()
