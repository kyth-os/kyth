from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "build_files/scripts/r2_retention.py"
SPEC = importlib.util.spec_from_file_location("r2_retention", SCRIPT)
assert SPEC and SPEC.loader
r2_retention = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r2_retention
SPEC.loader.exec_module(r2_retention)

SUFFIXES = ("", "-CHECKSUM", ".sig", ".bundle", ".intoto.jsonl", ".json")


def build_keys(channel: str, date: str, sha: str, run: int, attempt: int = 1,
               suffixes: tuple[str, ...] = SUFFIXES) -> list[str]:
    stem = f"kyth-live-{channel}-{date}-{sha}-{run}-{attempt}.iso"
    return [stem + suffix for suffix in suffixes]


class PlanDeletionsTests(unittest.TestCase):
    def test_keeps_newest_five_per_channel_and_deletes_older_sets_wholly(self):
        keys: list[str] = []
        for run in range(1, 8):  # 7 testing builds, runs 1..7 on rising dates
            keys += build_keys("testing", f"202610{run:02d}", "a94b429e", run)
        for run in range(1, 4):  # 3 latest builds: all kept
            keys += build_keys("latest", f"202608{run:02d}", "b0513646", run)
        doomed = r2_retention.plan_deletions(keys, keep=5)
        expected = sorted(
            build_keys("testing", "20261001", "a94b429e", 1)
            + build_keys("testing", "20261002", "a94b429e", 2)
        )
        self.assertEqual(doomed, expected)

    def test_channel_pointers_and_foreign_keys_are_never_planned(self):
        keys: list[str] = []
        for run in range(1, 9):
            keys += build_keys("testing", f"202610{run:02d}", "a94b429e", run)
        foreign = [
            "kyth-live-testing.iso",
            "kyth-live-testing.iso-CHECKSUM",
            "kyth-live-testing.iso.sig",
            "kyth-live-latest.iso",
            "kyth-live-latest.iso.json",
            "kyth-live-anaconda-testing.iso",
            "kyth-live-anaconda-latest.iso",
            "kyth-live-surface.iso",
            "kyth-secureboot.der",
            "README.txt",
        ]
        doomed = r2_retention.plan_deletions(keys + foreign, keep=5)
        for key in foreign:
            self.assertNotIn(key, doomed)
        self.assertEqual(len(doomed), 3 * len(SUFFIXES))

    def test_date_dominates_run_number_across_counter_eras(self):
        """Run numbers reset when the workflow is recreated (Aug builds
        carried runs ~1700, Oct builds ~990). Ordering must follow the
        build date first, or the newest builds would be purged."""
        keys: list[str] = []
        keys += build_keys("testing", "20260814", "5d6b01f3", 1736)
        keys += build_keys("testing", "20261028", "a94b429e", 993)
        self.assertEqual(r2_retention.plan_deletions(keys, keep=1),
                         sorted(build_keys("testing", "20260814", "5d6b01f3", 1736)))

    def test_same_day_builds_order_by_run_then_attempt(self):
        keys: list[str] = []
        keys += build_keys("testing", "20261025", "6f4ef4be", 984)
        keys += build_keys("testing", "20261025", "2baf8496", 986)
        keys += build_keys("testing", "20261025", "6f4ef4be", 983)
        doomed = r2_retention.plan_deletions(keys, keep=2)
        self.assertEqual(doomed, sorted(build_keys("testing", "20261025", "6f4ef4be", 983)))

    def test_partial_build_set_is_deleted_as_a_unit(self):
        keys: list[str] = []
        for run in range(1, 7):
            keys += build_keys("latest", f"202608{run:02d}", "b0513646", run)
        keys += build_keys("latest", "20260613", "31d4e50f", 684,
                           suffixes=("", ".sig"))  # partial old set
        doomed = r2_retention.plan_deletions(keys, keep=5)
        self.assertIn("kyth-live-latest-20260613-31d4e50f-684-1.iso", doomed)
        self.assertIn("kyth-live-latest-20260613-31d4e50f-684-1.iso.sig", doomed)

    def test_fewer_builds_than_keep_deletes_nothing(self):
        keys = build_keys("testing", "20261028", "a94b429e", 993)
        self.assertEqual(r2_retention.plan_deletions(keys, keep=5), [])

    def test_keep_must_be_positive(self):
        with self.assertRaises(ValueError):
            r2_retention.plan_deletions([], keep=0)


class FakeRunner:
    """Stands in for the aws CLI. Serves canned list pages in order and
    records the keys named by every delete-objects payload file."""

    def __init__(self, pages: list[dict]):
        self.pages = list(pages)
        self.deleted: list[str] = []
        self.list_tokens: list[str | None] = []

    def __call__(self, argv: list[str]) -> dict:
        if "list-objects-v2" in argv:
            if "--continuation-token" in argv:
                self.list_tokens.append(argv[argv.index("--continuation-token") + 1])
            else:
                self.list_tokens.append(None)
            return self.pages.pop(0)
        if "delete-objects" in argv:
            payload_ref = next(a for a in argv if a.startswith("file://"))
            payload = json.loads(Path(payload_ref[len("file://"):]).read_text())
            self.deleted.extend(obj["Key"] for obj in payload["Objects"])
            return {}
        raise AssertionError(f"unexpected argv: {argv}")


def objects_page(keys: list[str], truncated: bool = False, token: str | None = None) -> dict:
    page: dict = {"Contents": [{"Key": key, "Size": 1000} for key in keys],
                  "IsTruncated": truncated}
    if token:
        page["NextContinuationToken"] = token
    return page


class ApplyRetentionTests(unittest.TestCase):
    def test_paginates_listing_and_deletes_only_planned_keys(self):
        old = build_keys("testing", "20261001", "a94b429e", 1)
        keys: list[str] = list(old)
        for run in range(2, 7):
            keys += build_keys("testing", f"202610{run:02d}", "a94b429e", run)
        keys.append("kyth-live-testing.iso")
        runner = FakeRunner([
            objects_page(keys[:20], truncated=True, token="tok-1"),
            objects_page(keys[20:]),
        ])
        seen, deleted = r2_retention.apply_retention(
            runner, "kyth-releases", "https://acct.r2.cloudflarestorage.com", keep=5)
        self.assertEqual(seen, 6)
        self.assertEqual(deleted, len(old))
        self.assertEqual(sorted(runner.deleted), sorted(old))
        self.assertEqual(runner.list_tokens, [None, "tok-1"])

    def test_dry_run_deletes_nothing(self):
        keys: list[str] = []
        for run in range(1, 8):
            keys += build_keys("testing", f"202610{run:02d}", "a94b429e", run)
        runner = FakeRunner([objects_page(keys)])
        _, deleted = r2_retention.apply_retention(
            runner, "kyth-releases", "https://acct.r2.cloudflarestorage.com",
            keep=5, dry_run=True)
        self.assertEqual(deleted, 0)
        self.assertEqual(runner.deleted, [])

    def test_delete_batches_never_exceed_the_s3_limit(self):
        keys: list[str] = []
        for run in range(1, 208):  # 207 builds, keep 5 -> 202 sets * 6 files
            keys += build_keys("testing", f"2026{run:04d}", "a94b429e", run)
        batch_sizes: list[int] = []

        class CountingRunner(FakeRunner):
            def __call__(self, argv: list[str]) -> dict:
                if "delete-objects" in argv:
                    payload_ref = next(a for a in argv if a.startswith("file://"))
                    payload = json.loads(Path(payload_ref[len("file://"):]).read_text())
                    batch_sizes.append(len(payload["Objects"]))
                return super().__call__(argv)

        runner = CountingRunner([objects_page(keys)])
        _, deleted = r2_retention.apply_retention(
            runner, "kyth-releases", "https://acct.r2.cloudflarestorage.com", keep=5)
        self.assertEqual(deleted, 202 * len(SUFFIXES))
        self.assertTrue(batch_sizes)
        self.assertTrue(all(size <= 1000 for size in batch_sizes))

    def test_listing_failure_propagates_as_runtime_error(self):
        def failing_runner(argv: list[str]) -> dict:
            raise RuntimeError("aws exploded")

        with self.assertRaises(RuntimeError):
            r2_retention.apply_retention(
                failing_runner, "kyth-releases",
                "https://acct.r2.cloudflarestorage.com", keep=5)

    def test_main_rejects_keep_below_one(self):
        with self.assertRaises(SystemExit):
            r2_retention.main(
                ["--bucket", "kyth-releases",
                 "--endpoint-url", "https://acct.r2.cloudflarestorage.com",
                 "--keep", "0"],
                runner=FakeRunner([]),
            )


class UploadActionContractTests(unittest.TestCase):
    def test_action_runs_retention_after_upload_without_failing_releases(self):
        action = (ROOT / ".github/actions/upload-r2/action.yml").read_text(encoding="utf-8")
        self.assertIn("r2_retention.py", action)
        self.assertIn("continue-on-error: true", action)
        self.assertIn('default: "5"', action)
        # retention step must come after the upload step it cleans up behind
        self.assertLess(action.index("aws s3 cp"), action.index("r2_retention.py"))


if __name__ == "__main__":
    unittest.main()
