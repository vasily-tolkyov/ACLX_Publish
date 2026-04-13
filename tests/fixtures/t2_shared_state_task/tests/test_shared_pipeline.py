from __future__ import annotations

import unittest

from src.shared_pipeline import collect_ready_steps


class SharedPipelineTests(unittest.TestCase):
    def test_empty_steps(self) -> None:
        self.assertEqual(collect_ready_steps([]), [])

    def test_preserves_first_seen_order_when_deduping(self) -> None:
        steps = ["build", " lint ", "Build", "", "test", "lint", "deploy"]
        self.assertEqual(collect_ready_steps(steps), ["build", "lint", "test", "deploy"])


if __name__ == "__main__":
    unittest.main()
