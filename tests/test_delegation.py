from __future__ import annotations

import json
import unittest

from aclx.delegation import ACLXDelegation


class DelegationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.delegation = ACLXDelegation()

    def test_rendered_payload_includes_task_and_aclx(self) -> None:
        payload = self.delegation.from_handoff_obj(
            {"goal": "ship adapters", "priority": 1},
            task="Continue adapter work.",
        )
        rendered = payload.render()
        self.assertTrue(rendered.startswith("Continue adapter work."))
        self.assertIn("h|c|c0|1", rendered)

    def test_aclx_only_payload_is_compact(self) -> None:
        payload = self.delegation.from_handoff_obj(
            {"goal": "ship adapters"},
            aclx_only=True,
        )
        self.assertEqual(payload.render(), payload.aclx)

    def test_payload_json_round_trip(self) -> None:
        payload = self.delegation.from_handoff_obj(
            {"goal": "ship adapters", "next_actions": ["measure latency"]},
            task="Continue from ACL-X.",
        )
        encoded = self.delegation.payload_json(payload)
        restored = self.delegation.payload_from_json(encoded)
        self.assertEqual(restored.task, "Continue from ACL-X.")
        self.assertEqual(restored.aclx, payload.aclx)


if __name__ == "__main__":
    unittest.main()
