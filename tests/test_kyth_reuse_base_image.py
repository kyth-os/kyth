"""Unit tests for reuse-base-image.py — match / mismatch / missing labels."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reuse_base_image", ROOT / "build_files" / "scripts" / "reuse-base-image.py"
)
assert SPEC and SPEC.loader
reuse_base_image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reuse_base_image)


DIGEST = "sha256:" + ("a" * 64)


def _inspect_payload(labels: dict[str, str] | None = None, digest: str = DIGEST) -> dict:
    return {
        "manifest": {"digest": digest},
        "image": {"config": {"Labels": labels or {}}},
    }


class SourceHashTests(unittest.TestCase):
    def test_hash_is_stable_for_the_same_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            (root / "build.sh").write_text("#!/bin/bash\n", encoding="utf-8")
            first = reuse_base_image.source_hash(root)
            second = reuse_base_image.source_hash(root)
        self.assertEqual(first, second)
        self.assertEqual(64, len(first))

    def test_hash_changes_when_a_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "Dockerfile"
            path.write_text("FROM scratch\n", encoding="utf-8")
            before = reuse_base_image.source_hash(root)
            path.write_text("FROM alpine\n", encoding="utf-8")
            after = reuse_base_image.source_hash(root)
        self.assertNotEqual(before, after)


class InspectParseTests(unittest.TestCase):
    def test_extracts_digest_and_labels_from_buildx_json(self):
        payload = _inspect_payload(
            {
                reuse_base_image.LABEL_UPSTREAM: "ghcr.io/ublue-os/kinoite-main:44@sha256:" + ("b" * 64),
                reuse_base_image.LABEL_FLAVOR: "cachy",
            }
        )
        self.assertEqual(DIGEST, reuse_base_image.extract_digest(payload))
        labels = reuse_base_image.extract_labels(payload)
        self.assertEqual("cachy", labels[reuse_base_image.LABEL_FLAVOR])


class DecideReuseTests(unittest.TestCase):
    def _expected(self) -> dict[str, str]:
        return {
            reuse_base_image.LABEL_UPSTREAM: "upstream@sha256:" + ("b" * 64),
            reuse_base_image.LABEL_FLAVOR: "fedora",
            reuse_base_image.LABEL_KERNEL: "unused",
            reuse_base_image.LABEL_SRC: "c" * 64,
        }

    def test_match_reuses_the_digest(self):
        labels = self._expected()
        decision = reuse_base_image.decide_reuse(
            labels=labels,
            digest=DIGEST,
            upstream=labels[reuse_base_image.LABEL_UPSTREAM],
            flavor="fedora",
            kernel="unused",
            src_hash=labels[reuse_base_image.LABEL_SRC],
        )
        self.assertEqual({"reuse": True, "digest": DIGEST, "reason": "match"}, decision)

    def test_missing_labels_rebuild(self):
        decision = reuse_base_image.decide_reuse(
            labels={},
            digest=DIGEST,
            upstream="upstream",
            flavor="fedora",
            kernel="unused",
            src_hash="abc",
        )
        self.assertEqual(False, decision["reuse"])
        self.assertEqual("missing-labels", decision["reason"])

    def test_label_mismatch_rebuilds(self):
        labels = self._expected()
        decision = reuse_base_image.decide_reuse(
            labels=labels,
            digest=DIGEST,
            upstream=labels[reuse_base_image.LABEL_UPSTREAM],
            flavor="cachy",
            kernel="unused",
            src_hash=labels[reuse_base_image.LABEL_SRC],
        )
        self.assertEqual(False, decision["reuse"])
        self.assertEqual("label-mismatch", decision["reason"])

    def test_missing_digest_rebuilds_even_when_labels_match(self):
        labels = self._expected()
        decision = reuse_base_image.decide_reuse(
            labels=labels,
            digest=None,
            upstream=labels[reuse_base_image.LABEL_UPSTREAM],
            flavor="fedora",
            kernel="unused",
            src_hash=labels[reuse_base_image.LABEL_SRC],
        )
        self.assertEqual(False, decision["reuse"])
        self.assertEqual("missing-digest", decision["reason"])


class DecideCommandTests(unittest.TestCase):
    def test_inspect_failure_prints_rebuild_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            stdout = StringIO()
            args = mock.Mock(
                source_root=root,
                ref="ghcr.io/example/kyth:base-testing",
                upstream="upstream",
                flavor="fedora",
                kernel="unused",
            )
            with mock.patch.object(reuse_base_image, "inspect_ref", return_value=None), mock.patch(
                "sys.stdout", stdout
            ):
                exit_code = reuse_base_image.cmd_decide(args)
        self.assertEqual(0, exit_code)
        self.assertEqual(
            {"reuse": False, "digest": None, "reason": "inspect-failed"},
            json.loads(stdout.getvalue()),
        )


if __name__ == "__main__":
    unittest.main()
