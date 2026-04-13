from __future__ import annotations

import unittest

from aclx.metrics import run_tokenizer_benchmark, tokenizer_name
from aclx.transcoder import ACLXTranscoder


class TokenizerTests(unittest.TestCase):
    def test_tokenizer_benchmark_runs(self) -> None:
        rows = run_tokenizer_benchmark(ACLXTranscoder())
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            self.assertIn("aclx_tokens", row)
            self.assertIn("tool_json_tokens", row)

    def test_tokenizer_name_present(self) -> None:
        self.assertTrue(tokenizer_name())


if __name__ == "__main__":
    unittest.main()
