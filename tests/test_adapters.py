from __future__ import annotations

import json
import unittest

from aclx.adapters import ACLXAdapter
from aclx.ir import frame_to_dict
from aclx.model import Clause, EscapeBlock, EscapeRef, MsgFrame, SymbolRef


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ACLXAdapter()

    def test_tool_json_round_trip(self) -> None:
        frame = MsgFrame(
            mode="c",
            body=[
                Clause(
                    ref="1",
                    slots={
                        "actor": SymbolRef("E", "agent"),
                        "action": SymbolRef("A", "plan"),
                        "object": SymbolRef("E", "task"),
                        "status": SymbolRef("Q", "goal"),
                    },
                )
            ],
            metadata={"priority": 1, "certainty": 0.9},
        )
        aclx = self.adapter.codec.encode(frame)
        tool_json = self.adapter.aclx_to_tool_json(aclx)
        rebuilt = self.adapter.tool_json_to_aclx(tool_json)

        self.assertEqual(
            frame_to_dict(self.adapter.codec.decode(rebuilt))["body"],
            frame_to_dict(frame)["body"],
        )
        self.assertIn('"b"', tool_json)
        self.assertIn('"x"', tool_json)

    def test_handoff_json_to_aclx_and_back(self) -> None:
        handoff = {
            "goal": "ship adapters",
            "completed": ["implemented codec", "implemented CLI"],
            "current_state": "adapter tests pending",
            "risks": ["coverage gap"],
            "next_actions": ["add adapter benchmarks"],
            "evidence": ["tests passing"],
            "priority": 1,
            "certainty": 0.93,
        }
        aclx = self.adapter.handoff_obj_to_aclx(handoff)
        restored = json.loads(self.adapter.aclx_to_handoff_json(aclx))

        self.assertEqual(restored["py"], 1)
        self.assertAlmostEqual(restored["cy"], 0.93)
        self.assertIn("ship adapters", restored["g"])
        self.assertIn("coverage gap", restored["r"])

    def test_long_handoff_values_use_escape_blocks(self) -> None:
        handoff = {
            "goal": "Implement the ultra-light adapter layer for ACL-X with direct tool JSON conversion.",
            "next_actions": ["Measure adapter latency over repeated round trips."],
        }
        frame = self.adapter.handoff_obj_to_frame(handoff)
        self.assertTrue(frame.escapes)
        self.assertIsInstance(frame.body[0].slots["context"], EscapeRef)

    def test_adapter_benchmark_runs(self) -> None:
        rows = self.adapter.adapter_benchmark(iterations=10)
        self.assertGreaterEqual(len(rows), 2)
        for row in rows:
            self.assertGreater(row["tool_json_chars"], 0)
            self.assertGreaterEqual(row["avg_ms"], 0)


if __name__ == "__main__":
    unittest.main()
