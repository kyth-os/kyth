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
    def test_candidates_tolerate_broken_context_mount_registry(self):
        context = mock.Mock()
        type(context).cleanup_mounts = mock.PropertyMock(side_effect=RuntimeError("unavailable"))
        self.assertEqual(
            finalize_artifacts.target_mount_candidates(context),
            list(finalize_artifacts.FALLBACK_TARGET_MOUNTS),
        )

    def test_candidates_deduplicate_registered_and_fallback_mounts(self):
        context = SimpleNamespace(cleanup_mounts=["/target", "/var/tmp/kyth-install-root"])
        candidates = finalize_artifacts.target_mount_candidates(context)
        self.assertEqual(candidates[0], "/target")
        self.assertEqual(candidates.count("/var/tmp/kyth-install-root"), 1)

    def test_mount_probe_requires_directory_and_rejects_unverifiable_target(self):
        with mock.patch.object(finalize_artifacts.os.path, "isdir", return_value=False):
            self.assertFalse(finalize_artifacts.mounted_target("/target", run_command=mock.Mock()))
        with mock.patch.object(finalize_artifacts.os.path, "isdir", return_value=True):
            # Fail closed: an unverifiable candidate is not a target — a
            # probe error must never declare logs "saved" into the live env.
            self.assertFalse(
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

    def test_failure_message_retries_next_mount_when_tee_reports_failure(self):
        """A nonzero tee exit (no exception) must advance to the next
        candidate instead of declaring the message written.
        """
        context = SimpleNamespace(cleanup_mounts=["/bad-write", "/target"])
        calls = []

        def run(argv, **_kwargs):
            calls.append(argv[-1])
            if argv[-1].startswith("/bad-write/"):
                return SimpleNamespace(returncode=1)
            return SimpleNamespace(returncode=0)

        with mock.patch.object(finalize_artifacts, "mounted_target", return_value=True):
            finalize_artifacts.persist_failure_message(
                mock.Mock(), context, "disk failed", persist=mock.Mock(),
                run_command=run, as_root=lambda argv: argv,
            )
        self.assertTrue(any(c.startswith("/bad-write/") for c in calls))
        self.assertTrue(any(c.startswith("/target/") for c in calls))

    def test_persist_reports_failure_honestly_and_never_claims_success(self):
        """A failed mkdir/cp must not log "persisted": the failure moves to
        the next candidate, and total failure says so out loud.
        """
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "install.log"
            source.write_text("log")
            context = SimpleNamespace(cleanup_mounts=["/flaky", "/target"])
            calls = []

            def run(argv, **_kwargs):
                calls.append(argv[0])
                if argv[0] == "cp" and "/flaky/" in argv[-1]:
                    return SimpleNamespace(returncode=1)
                return SimpleNamespace(returncode=0)

            log = mock.Mock()
            with mock.patch.object(finalize_artifacts, "mounted_target", return_value=True):
                finalize_artifacts.persist_artifacts(
                    log, context, [source],
                    run_command=run, as_root=lambda argv: argv,
                )
            messages = [call.args[0] for call in log.call_args_list]
            self.assertTrue(any("could not persist install.log" in m for m in messages))
            self.assertTrue(any("persisted to" in m and "/target/" in m for m in messages))

            log2 = mock.Mock()
            with mock.patch.object(finalize_artifacts, "mounted_target", return_value=True):
                finalize_artifacts.persist_artifacts(
                    log2, context, [source],
                    run_command=mock.Mock(return_value=SimpleNamespace(returncode=1)),
                    as_root=lambda argv: argv,
                )
            messages2 = [call.args[0] for call in log2.call_args_list]
            self.assertFalse(any("persisted to" in m for m in messages2))
            self.assertTrue(any("were NOT saved" in m for m in messages2))

    def test_persist_skips_probe_and_copy_failures_then_uses_next_mount(self):
        log = mock.Mock()
        context = SimpleNamespace(cleanup_mounts=["/broken-probe", "/broken-copy", "/target"])
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))

        def probe(mountpoint, **_kwargs):
            if mountpoint == "/broken-probe":
                raise RuntimeError("probe failed")
            return True

        def rooted(argv):
            if "/broken-copy/" in argv[-1]:
                raise RuntimeError("root wrapper failed")
            return argv

        with mock.patch.object(finalize_artifacts, "mounted_target", side_effect=probe):
            finalize_artifacts.persist_artifacts(
                log, context, [], run_command=run, as_root=rooted,
            )

        self.assertTrue(any("broken-copy" in call.args[0] for call in log.call_args_list))
        self.assertTrue(any("/target/" in call.args[0] for call in log.call_args_list))

    def test_persistence_is_noop_without_a_mounted_target(self):
        context = SimpleNamespace(cleanup_mounts=[])
        run = mock.Mock()
        with mock.patch.object(finalize_artifacts, "mounted_target", return_value=False):
            finalize_artifacts.persist_artifacts(
                mock.Mock(), context, [], run_command=run, as_root=lambda argv: argv,
            )
            finalize_artifacts.persist_failure_message(
                mock.Mock(), context, "failed", persist=mock.Mock(),
                run_command=run, as_root=lambda argv: argv,
            )
        run.assert_not_called()

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

    def test_failure_message_skips_probe_and_write_failures(self):
        context = SimpleNamespace(cleanup_mounts=["/bad-probe", "/bad-write", "/target"])
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))

        def probe(mountpoint, **_kwargs):
            if mountpoint == "/bad-probe":
                raise RuntimeError("probe failed")
            return True

        def rooted(argv):
            if "/bad-write/" in argv[-1]:
                raise RuntimeError("write setup failed")
            return argv

        with mock.patch.object(finalize_artifacts, "mounted_target", side_effect=probe):
            finalize_artifacts.persist_failure_message(
                mock.Mock(), context, "failed", persist=mock.Mock(),
                run_command=run, as_root=rooted,
            )

        self.assertIn("/target/", run.call_args.args[0][-1])


if __name__ == "__main__":
    unittest.main()
