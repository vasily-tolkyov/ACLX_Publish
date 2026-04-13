from __future__ import annotations

import unittest

from aclx.codec import ACLXCodec
from aclx.ir import frame_to_dict
from aclx.model import AliasRef, Clause, DeltaPatch, EscapeBlock, EscapeRef, ModTag, MsgFrame, SemanticNode, SymbolRef
from aclx.ontology import core_pack


class CodecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = core_pack()
        self.codec = ACLXCodec(self.pack)

    def test_message_frame_round_trip(self) -> None:
        frame = MsgFrame(
            mode="c",
            pack_ref=self.pack.pack_id,
            version=self.pack.version,
            session_aliases={"tsk": SymbolRef("E", "task")},
            nodes=[SemanticNode(ref="1", kind="E", symbol=SymbolRef("E", "result"), attrs={"label": "summary"})],
            escapes=[EscapeBlock(ref="1", kind="raw", payload="Plan the task and report the result.", mime="text/plain")],
            body=[
                Clause(
                    ref="1",
                    slots={
                        "actor": SymbolRef("E", "agent"),
                        "action": SymbolRef("A", "plan"),
                        "object": AliasRef("tsk"),
                        "context": EscapeRef("1"),
                        "status": SymbolRef("Q", "goal"),
                    },
                    mods=[ModTag("must", True), ModTag("prob", 0.75)],
                )
            ],
            deltas=[DeltaPatch(target=AliasRef("tsk"), slots={"status": SymbolRef("Q", "done")})],
            constraints=[SymbolRef("Q", "must")],
            proofs=[SymbolRef("E", "evidence")],
            metadata={"certainty": 0.91, "priority": 2, "scope": "team"},
        )

        encoded = self.codec.encode(frame)
        decoded = self.codec.decode(encoded)

        self.assertEqual(frame_to_dict(decoded)["body"], frame_to_dict(frame)["body"])
        self.assertEqual(frame_to_dict(decoded)["session_aliases"], frame_to_dict(frame)["session_aliases"])
        self.assertEqual(frame_to_dict(decoded)["deltas"], frame_to_dict(frame)["deltas"])
        self.assertEqual(decoded.metadata["priority"], 2)
        self.assertIsNotNone(decoded.checksum)

    def test_escape_and_node_records_round_trip(self) -> None:
        frame = MsgFrame(
            mode="c",
            pack_ref=self.pack.pack_id,
            version=self.pack.version,
            nodes=[SemanticNode(ref="n1", kind="E", symbol=SymbolRef("E", "context"), attrs={"rank": 1})],
            escapes=[EscapeBlock(ref="x1", payload={"raw": "opaque"})],
            body=[Clause(ref="f1", slots={"context": EscapeRef("x1"), "object": SymbolRef("E", "context")})],
        )
        encoded = self.codec.encode(frame)
        decoded = self.codec.decode(encoded)
        self.assertEqual(frame_to_dict(decoded)["escapes"], frame_to_dict(frame)["escapes"])
        self.assertEqual(frame_to_dict(decoded)["nodes"], frame_to_dict(frame)["nodes"])


if __name__ == "__main__":
    unittest.main()
