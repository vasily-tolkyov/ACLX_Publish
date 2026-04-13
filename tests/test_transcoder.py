from __future__ import annotations

import unittest

from aclx.ir import frame_to_dict
from aclx.transcoder import ACLXTranscoder


class TranscoderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transcoder = ACLXTranscoder()

    def test_nl_to_aclx_and_gloss(self) -> None:
        text = "Please plan the task and report the result."
        encoded = self.transcoder.nl_to_aclx(text)
        gloss = self.transcoder.aclx_to_nl_gloss(encoded)
        self.assertIn("h|c|c0|1", encoded)
        self.assertIn("plan", gloss)
        self.assertIn("agent", gloss)

    def test_complex_text_falls_back_to_escape(self) -> None:
        text = "Design a communication language for AI agents that is dense, fast, and token efficient."
        frame = self.transcoder.nl_to_frame(text)
        data = frame_to_dict(frame)
        self.assertEqual(data["body"][0]["slots"]["context"]["type"], "escape_ref")
        self.assertEqual(data["escapes"][0]["kind"], "raw")

    def test_aclx_to_json_ir(self) -> None:
        encoded = self.transcoder.nl_to_aclx("If the tool fails, explain the error.")
        data = self.transcoder.aclx_to_json_ir(encoded)
        self.assertEqual(data["mode"], "c")
        self.assertTrue(data["body"])


if __name__ == "__main__":
    unittest.main()
