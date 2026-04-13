from __future__ import annotations

import unittest

from aclx.codec import ACLXCodec
from aclx.model import Clause, ModTag, MsgFrame, SymbolRef, ThoughtFrame
from aclx.ontology import core_pack


class LayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.codec = ACLXCodec(core_pack())

    def test_thought_frame_omits_checksum(self) -> None:
        frame = ThoughtFrame(
            mode="t",
            pack_ref="c0",
            version="1",
            body=[Clause(ref="1", slots={"action": SymbolRef("A", "think"), "object": SymbolRef("E", "task")})],
            metadata={"scope": "session"},
        )
        encoded = self.codec.encode(frame)
        self.assertNotIn("~k|", encoded)
        decoded = self.codec.decode(encoded)
        self.assertEqual(decoded.mode, "t")
        self.assertEqual(decoded.body[0].slots["action"].name, "think")

    def test_checksum_validation_fails_on_tamper(self) -> None:
        frame = MsgFrame(
            mode="c",
            pack_ref="c0",
            version="1",
            body=[Clause(ref="1", slots={"action": SymbolRef("A", "report"), "object": SymbolRef("E", "result")}, mods=[ModTag("must", True)])],
        )
        encoded = self.codec.encode(frame)
        tampered = encoded[:-1] + ("0" if encoded[-1] != "0" else "1")
        with self.assertRaises(ValueError):
            self.codec.decode(tampered)


if __name__ == "__main__":
    unittest.main()
