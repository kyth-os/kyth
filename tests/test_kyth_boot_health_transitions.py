"""Transition contracts for kyth_shared.boot_health.

Regression coverage for:
- record_failure / mark_healthy preserving rollback history
  (rollback_attempted_for, last_rollback_error, last_rollback_at) instead of
  silently resetting it to defaults via the from-scratch constructor.
- Per-digest failure tallies surviving interleaved boots, so alternating
  between two bad deployments quarantines each at the threshold.
- from_dict round-trip and fail-closed parsing of failures_by_digest.

Mirrors the native Rust transitions in
src/kyth-shared-rs/src/system/boot_health.rs; the two implementations must
stay field-for-field aligned.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth_shared"))

from kyth_shared.boot_health import (  # noqa: E402
    BootHealthState,
    clear_quarantine,
    mark_healthy,
    note_rollback_attempted,
    quarantine_boot_message,
    record_failure,
    rollback_retry_due,
)

DIGEST_A = "sha256:aaa"
DIGEST_B = "sha256:bbb"


def failed(state: BootHealthState, digest: str, boot: str, tick: int) -> BootHealthState:
    return record_failure(state, digest, boot, "check failed", now=tick)


class RollbackHistoryTests(unittest.TestCase):
    def test_record_failure_preserves_rollback_history(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = note_rollback_attempted(state, DIGEST_A, error="exit 1", now=10)
        updated = failed(state, DIGEST_B, "boot-1", 11)
        self.assertEqual(updated.rollback_attempted_for, DIGEST_A)
        self.assertEqual(updated.last_rollback_error, "exit 1")
        self.assertEqual(updated.last_rollback_at, 10)

    def test_record_failure_for_same_digest_preserves_history(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = note_rollback_attempted(state, DIGEST_A, error="boom", now=10)
        updated = failed(state, DIGEST_A, "boot-1", 11)
        self.assertEqual(updated.rollback_attempted_for, DIGEST_A)
        self.assertEqual(updated.last_rollback_error, "boom")
        self.assertEqual(updated.last_rollback_at, 10)

    def test_mark_healthy_preserves_rollback_history(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = note_rollback_attempted(state, DIGEST_A, error="boom", now=10)
        recovered = mark_healthy(state, DIGEST_B, now=11)
        self.assertEqual(recovered.rollback_attempted_for, DIGEST_A)
        self.assertEqual(recovered.last_rollback_error, "boom")
        self.assertEqual(recovered.last_rollback_at, 10)

    def test_mark_healthy_resets_streak_but_keeps_rollback_marker(self) -> None:
        state = failed(BootHealthState(current_digest=DIGEST_A), DIGEST_A, "boot-1", 10)
        state = note_rollback_attempted(state, DIGEST_A, now=11)
        recovered = mark_healthy(state, DIGEST_A, now=12)
        self.assertEqual(recovered.failures, 0)
        self.assertEqual(recovered.last_failure_boot_id, "")
        self.assertEqual(recovered.rollback_attempted_for, DIGEST_A)


class PerDigestCountingTests(unittest.TestCase):
    def test_consecutive_failures_quarantine_at_threshold(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = failed(state, DIGEST_A, "boot-1", 1)
        state = failed(state, DIGEST_A, "boot-2", 2)
        self.assertNotIn(DIGEST_A, state.quarantined)
        state = failed(state, DIGEST_A, "boot-3", 3)
        self.assertEqual(state.status, "quarantined")
        self.assertEqual(state.quarantined[DIGEST_A].failures, 3)

    def test_alternating_digests_quarantine_each_at_threshold(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        tick = 0
        for round in range(3):
            for digest, boot in ((DIGEST_A, f"a-{round}"), (DIGEST_B, f"b-{round}")):
                tick += 1
                state = failed(state, digest, boot, tick)
        self.assertIn(DIGEST_A, state.quarantined)
        self.assertIn(DIGEST_B, state.quarantined)
        self.assertEqual(state.quarantined[DIGEST_A].failures, 3)
        self.assertEqual(state.quarantined[DIGEST_B].failures, 3)

    def test_same_boot_id_counts_once(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = failed(state, DIGEST_A, "boot-1", 1)
        duplicate = failed(state, DIGEST_A, "boot-1", 2)
        self.assertEqual(duplicate.failures, 1)
        self.assertEqual(duplicate.failures_by_digest[DIGEST_A], 1)

    def test_mark_healthy_forgives_digest_tally(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = failed(state, DIGEST_A, "boot-1", 1)
        state = failed(state, DIGEST_A, "boot-2", 2)
        state = mark_healthy(state, DIGEST_A, now=3)
        self.assertNotIn(DIGEST_A, state.failures_by_digest)
        state = failed(state, DIGEST_A, "boot-3", 4)
        self.assertEqual(state.failures_by_digest[DIGEST_A], 1)
        self.assertNotIn(DIGEST_A, state.quarantined)

    def test_clear_quarantine_resets_tally(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        for index in range(3):
            state = failed(state, DIGEST_A, f"boot-{index}", index)
        self.assertIn(DIGEST_A, state.quarantined)
        cleared = clear_quarantine(state, DIGEST_A, now=10)
        self.assertNotIn(DIGEST_A, cleared.quarantined)
        self.assertNotIn(DIGEST_A, cleared.failures_by_digest)


class RollbackRetryDueTests(unittest.TestCase):
    """Mirror of Rust rollback_retries_after_a_failed_attempt_but_not_after_success."""

    def test_retry_after_failed_attempt_but_not_after_success(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = failed(state, DIGEST_A, "boot-1", 1)
        state = failed(state, DIGEST_A, "boot-2", 2)
        before = state
        # Third red boot quarantines: first rollback attempt is due.
        state = failed(state, DIGEST_A, "boot-3", 3)
        self.assertIn(DIGEST_A, state.quarantined)
        self.assertTrue(rollback_retry_due(before, state, DIGEST_A))
        # A failed attempt records its error: the next red boot retries.
        state = note_rollback_attempted(state, DIGEST_A, error="exit 1", now=4)
        before = state
        state = failed(state, DIGEST_A, "boot-4", 5)
        self.assertTrue(rollback_retry_due(before, state, DIGEST_A))
        # Duplicate reports from the same boot must not spam rollbacks.
        duplicate = failed(state, DIGEST_A, "boot-4", 6)
        self.assertFalse(rollback_retry_due(state, duplicate, DIGEST_A))
        # A successful attempt is once-ever: later red boots stay quiet.
        state = note_rollback_attempted(state, DIGEST_A, now=7)
        before = state
        state = failed(state, DIGEST_A, "boot-5", 8)
        self.assertFalse(rollback_retry_due(before, state, DIGEST_A))
        # Unrelated digests never trigger.
        self.assertFalse(rollback_retry_due(before, state, DIGEST_B))

    def test_retry_due_ignores_a_different_digests_overwritten_attempt(self) -> None:
        """Mirror of Rust rollback_retry_due_ignores_a_different_digests_overwritten_attempt.

        rollback_attempted_for/last_rollback_error are a single global slot,
        not per-digest. Once digest A's rollback has succeeded, a later
        rollback attempt for an unrelated digest B that then FAILS must not
        make A look retry-eligible again just because it overwrote the
        global slot with B's own error.
        """
        state = BootHealthState(current_digest=DIGEST_A)
        state = failed(state, DIGEST_A, "boot-1", 1)
        state = failed(state, DIGEST_A, "boot-2", 2)
        state = failed(state, DIGEST_A, "boot-3", 3)
        self.assertIn(DIGEST_A, state.quarantined)
        # A's rollback succeeds: global slot now names A with no error.
        state = note_rollback_attempted(state, DIGEST_A, now=4)

        # B is later quarantined and its rollback fails, overwriting the
        # global slot so it now names B with an error.
        state = failed(state, DIGEST_B, "boot-4", 5)
        state = failed(state, DIGEST_B, "boot-5", 6)
        state = failed(state, DIGEST_B, "boot-6", 7)
        self.assertIn(DIGEST_B, state.quarantined)
        state = note_rollback_attempted(state, DIGEST_B, error="bootc rollback: no such deployment", now=8)

        # A fails again. The global slot now names B, not A, so A's own
        # rollback history is unknowable from these fields — the fix must
        # not treat B's error as evidence that A needs a retry.
        before = state
        state = failed(state, DIGEST_A, "boot-7", 9)
        self.assertFalse(rollback_retry_due(before, state, DIGEST_A))

    def test_unquarantined_digest_is_never_due(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = failed(state, DIGEST_A, "boot-1", 1)
        self.assertFalse(rollback_retry_due(BootHealthState(), state, DIGEST_A))


class BootMessageTests(unittest.TestCase):
    """Mirror of Rust boot_message_surfaces_quarantine_and_rollback_state."""

    def test_surfaces_quarantine_and_rollback_state(self) -> None:
        self.assertIsNone(quarantine_boot_message(BootHealthState()))
        state = BootHealthState(current_digest=DIGEST_A)
        for index, boot in enumerate(("boot-1", "boot-2", "boot-3")):
            state = failed(state, DIGEST_A, boot, index)
        message = quarantine_boot_message(state)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("quarantined after 3 failed boots", message)
        self.assertNotIn("rollback", message)
        state = note_rollback_attempted(state, DIGEST_A, error="exit 1", now=10)
        message = quarantine_boot_message(state)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("automatic rollback failed: exit 1", message)
        state = note_rollback_attempted(state, DIGEST_A, now=11)
        message = quarantine_boot_message(state)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("rolled back", message)

    def test_names_newest_quarantine(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        for index in range(3):
            state = record_failure(
                state, DIGEST_A, f"a-{index}", "alpha failed", now=index
            )
        for index in range(3):
            state = record_failure(
                state, DIGEST_B, f"b-{index}", "beta failed", now=10 + index
            )
        message = quarantine_boot_message(state)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("beta failed", message)
        self.assertNotIn("alpha failed", message)


class StateCodecTests(unittest.TestCase):
    def test_round_trip_preserves_tallies(self) -> None:
        state = BootHealthState(current_digest=DIGEST_A)
        state = failed(state, DIGEST_A, "boot-1", 1)
        state = failed(state, DIGEST_B, "boot-9", 2)
        revived = BootHealthState.from_dict(state.to_dict())
        self.assertEqual(revived.failures_by_digest, {DIGEST_A: 1, DIGEST_B: 1})
        self.assertEqual(revived.invariants(), [])

    def test_malformed_tallies_are_dropped(self) -> None:
        document = BootHealthState().to_dict()
        document["failures_by_digest"] = {
            DIGEST_A: 2,
            "sha256:neg": -1,
            "sha256:str": "three",
            "sha256:bool": True,
        }
        revived = BootHealthState.from_dict(document)
        self.assertEqual(revived.failures_by_digest, {DIGEST_A: 2})

    def test_legacy_document_without_tallies_reads_empty(self) -> None:
        revived = BootHealthState.from_dict(
            {
                "schema_version": 1,
                "status": "healthy",
                "last_healthy_digest": DIGEST_A,
            }
        )
        self.assertEqual(revived.failures_by_digest, {})
        self.assertEqual(revived.invariants(), [])

    def test_invariants_flag_negative_tally(self) -> None:
        state = BootHealthState(failures_by_digest={DIGEST_A: -1})
        self.assertTrue(
            any("failures_by_digest" in err for err in state.invariants())
        )


if __name__ == "__main__":
    unittest.main()
