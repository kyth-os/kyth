"""Parity contracts for kyth_installer.plan_types against the native port.

Decodes the same tests/fixtures/installer_plan.json fixture the Rust
system::installer_plan tests decode, pinning field names, defaults, and
accessor semantics (ResolvedInstallPlan.disk raising on an unresolved
plan) on both sides. Execution stays in Python; the fixture keeps the
Rust shape honest.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files" / "kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer.context import InstallRequest  # noqa: E402
from kyth_installer.plan_types import InstallPlan, PlanReport, ResolvedInstallPlan  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "installer_plan.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PlanFixtureTests(unittest.TestCase):
    def test_report_decodes_the_shared_fixture(self) -> None:
        raw = load_fixture()["report"]
        report = PlanReport(
            **{**raw, "errors": tuple(raw["errors"]), "warnings": tuple(raw["warnings"])}
        )
        self.assertTrue(report.valid)
        self.assertEqual(report.mode, "guided")
        self.assertEqual(report.disk, "/dev/nvme0n1")
        self.assertEqual(report.required_bytes, 34359738368)
        self.assertGreater(report.available_bytes, report.required_bytes)
        self.assertTrue(report.is_gpt)
        self.assertFalse(report.needs_bios_boot)
        self.assertEqual(report.errors, ())
        self.assertEqual(report.warnings, ("Windows partition will shrink",))

    def test_resolved_plan_accessors_match_native_semantics(self) -> None:
        raw = load_fixture()["plan"]
        plan = ResolvedInstallPlan(
            request=InstallRequest(**raw["request"]),
            storage=InstallPlan(**raw["storage"]),
            source_ref=raw["source_ref"],
            target_ref=raw["target_ref"],
            source_digest=raw["source_digest"],
            source_kind=raw["source_kind"],
            source_verified=raw["source_verified"],
        )
        self.assertEqual(plan.mode, "guided")
        self.assertEqual(plan.disk, "/dev/nvme0n1")
        self.assertEqual(plan.target_partition, "/dev/nvme0n1p3")
        self.assertEqual(plan.efi_partition, "/dev/nvme0n1p1")
        self.assertEqual(plan.kernel, "fedora")
        self.assertEqual(plan.source_kind, "network")
        self.assertTrue(plan.source_verified)

    def test_disk_accessor_rejects_an_unresolved_plan(self) -> None:
        plan = ResolvedInstallPlan(
            request=InstallRequest(),
            storage=InstallPlan(mode="guided"),
            source_ref="x",
            target_ref="y",
        )
        with self.assertRaisesRegex(RuntimeError, "no target disk"):
            _ = plan.disk
        empty = ResolvedInstallPlan(
            request=InstallRequest(),
            storage=InstallPlan(mode="guided", disk=""),
            source_ref="x",
            target_ref="y",
        )
        with self.assertRaisesRegex(RuntimeError, "no target disk"):
            _ = empty.disk

    def test_request_defaults_match_native_defaults(self) -> None:
        request = InstallRequest()
        self.assertEqual(request.install_mode, "wipe")
        self.assertEqual(request.hostname, "kyth")
        self.assertEqual(request.timezone, "UTC")
        self.assertEqual(request.locale, "en_US.UTF-8")
        self.assertEqual(request.keymap, "us")
        self.assertEqual(request.kernel, "fedora")


if __name__ == "__main__":
    unittest.main()
