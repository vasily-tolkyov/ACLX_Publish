from __future__ import annotations

import unittest
import json

from aclx.metrics import approx_token_count, run_benchmark
from aclx.ir import frame_to_dict
from aclx.transcoder import ACLXTranscoder


class MetricsTests(unittest.TestCase):
    def test_benchmark_runs(self) -> None:
        rows = run_benchmark(ACLXTranscoder())
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            self.assertIn("parse_ms", row)
            self.assertGreater(row["json_chars"], 0)

    def test_aclx_beats_json_ir_on_structured_message(self) -> None:
        transcoder = ACLXTranscoder()
        encoded = transcoder.nl_to_aclx("Plan the task and report the result.")
        frame = transcoder.aclx_to_frame(encoded)
        json_ir = json.dumps(frame_to_dict(frame), ensure_ascii=True, separators=(",", ":"))
        self.assertLess(approx_token_count(encoded), approx_token_count(json_ir))


if __name__ == "__main__":
    unittest.main()
