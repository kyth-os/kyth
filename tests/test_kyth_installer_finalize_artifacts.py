import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.phases import finalize_artifacts  # noqa: E402


class FinalizeArtifactTests(unittest.TestCase):
    def test_candidates_deduplicate_registered_and_fallback_mounts(self):
        context = SimpleNamespace(cleanup_mounts=["/target", "/var/tmp/kyth-install-root"])
        candidates = finalize_artifacts.target_mount_candidates(context)
        self.assertEqual(candidates[0], "/target")
        self.assertEqual(candidates.count("/var/tmp/kyth-install-root"), 1)

    def test_mount_probe_requires_directory_and_accepts_findmnt_probe_failure(self):
        with mock.patch.object(finalize_artifacts.os.path, "isdir", return_value=False):
            self.assertFalse(finalize_artifacts.mounted_target("/target", run_command=mock.Mock()))
        with mock.patch.object(finalize_artifacts.os.path, "isdir", return_value=True):
            self.assertTrue(
                finalize_artifacts.mounted_target(
                    "/target", run_command=mock.Mock(side_effect=OSError("findmnt missing"))
                )
            )
            self.assertFalse(
                finalize_artifacts.mounted_target(
                    "/target", run_command=mock.Mock(return_value=SimpleNamespace(returncode=1))
                )
            )

    def test_persist_copies_only_safe_regular_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "install.log"
            source.write_text("log")
            missing = Path(tmp) / "missing"
            context = SimpleNamespace(cleanup_mounts=["/target"])
            run = mock.Mock(return_value=SimpleNamespace(returncode=0))
            with mock.patch.object(finalize_artifacts, "mounted_target", return_value=True):
                finalize_artifacts.persist_artifacts(
                    mock.Mock(), context, [source, missing],
                    run_command=run, as_root=lambda argv: argv,
                )
        copy_calls = [call for call in run.call_args_list if call.args[0][0] == "cp"]
        self.assertEqual(len(copy_calls), 1)

    def test_failure_message_persists_shared_artifacts_then_human_summary(self):
        persist = mock.Mock()
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        context = SimpleNamespace(cleanup_mounts=["/target"])
        with mock.patch.object(finalize_artifacts, "mounted_target", return_value=True):
            finalize_artifacts.persist_failure_message(
                mock.Mock(), context, "disk failed", persist=persist,
                run_command=run, as_root=lambda argv: argv,
            )
        persist.assert_called_once()
        self.assertIn("disk failed", run.call_args.kwargs["input"])
        self.assertIn("failure.json", run.call_args.kwargs["input"])


if __name__ == "__main__":
    unittest.main()
