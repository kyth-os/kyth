"""Static contracts for resumable GHCR publication throttling."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublishBackoffTests(unittest.TestCase):
    def test_secondary_rate_limit_has_bounded_exponential_backoff(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        self.assertIn("for attempt in 1 2 3 4 5", workflow)
        self.assertIn('grep -Fqi "secondary rate limit"', workflow)
        self.assertIn("60 * (2 ** (attempt - 1))", workflow)
        self.assertIn('2>&1 | tee "${PUBLISH_LOG}"', workflow)
        self.assertIn('[[ "${publish_succeeded}" == true ]]', workflow)

    def test_non_throttle_errors_fail_without_backoff(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        self.assertIn('exit "${copy_status}"', workflow)
        self.assertIn("copy_status=${PIPESTATUS[0]}", workflow)


if __name__ == "__main__":
    unittest.main()
