from __future__ import annotations

import unittest

from ctx.loader import ContextBundle, ContextLayer, estimate_tokens


class ContextLoaderTests(unittest.TestCase):
    def test_estimate_tokens_counts_text(self) -> None:
        self.assertGreaterEqual(estimate_tokens("hello world"), 2)

    def test_context_bundle_obeys_hard_limit(self) -> None:
        bundle = ContextBundle.from_layers(
            [
                ContextLayer("layer0", "always keep", token_budget=20, required=True, priority=10),
                ContextLayer("layer1", "drop me if needed " * 40, token_budget=40, priority=5),
            ]
        )
        assembled = bundle.assemble(25)
        self.assertLessEqual(estimate_tokens(assembled), 25)
        self.assertIn("layer0", assembled)


if __name__ == "__main__":
    unittest.main()
