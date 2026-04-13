from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from .codec import ACLXCodec
from .model import (
    AliasRef,
    Clause,
    DeltaPatch,
    EscapeBlock,
    EscapeRef,
    FrameRef,
    ModTag,
    MsgFrame,
    NodeRef,
    SemanticNode,
    SymbolRef,
    ThoughtFrame,
)
from .ontology import META_CODES, META_NAMES, MOD_TAG_CODES, MOD_TAG_NAMES, SLOT_CODES, SLOT_NAMES, core_pack
from .transcoder import ACLXTranscoder

TOOL_FRAME_KEYS = {
    "mode": "m",
    "pack_ref": "p",
    "version": "v",
    "session_aliases": "a",
    "nodes": "n",
    "escapes": "e",
    "body": "b",
    "deltas": "d",
    "constraints": "c",
    "proofs": "pf",
    "metadata": "x",
    "checksum": "k",
}

NODE_KEYS = {"ref": "r", "kind": "k", "symbol": "s", "attrs": "x"}
ESCAPE_KEYS = {"ref": "r", "kind": "k", "payload": "p", "mime": "m"}
CLAUSE_KEYS = {"ref": "r", "slots": "s", "mods": "m"}
DELTA_KEYS = {"target": "t", "slots": "s"}
HANDOFF_KEYS = {
    "goal": "g",
    "completed": "d",
    "current_state": "s",
    "risks": "r",
    "next_actions": "n",
    "evidence": "e",
    "priority": "py",
    "certainty": "cy",
    "scope": "sc",
    "source": "so",
}
HANDOFF_NAMES = {value: key for key, value in HANDOFF_KEYS.items()}


class ACLXAdapter:
    def __init__(self, codec: ACLXCodec | None = None, transcoder: ACLXTranscoder | None = None):
        self.pack = core_pack()
        self.codec = codec or ACLXCodec(self.pack)
        self.transcoder = transcoder or ACLXTranscoder(self.codec)

    def aclx_to_tool_obj(self, text: str) -> dict[str, Any]:
        return self.frame_to_tool_obj(self.codec.decode(text))

    def aclx_to_tool_json(self, text: str, *, pretty: bool = False) -> str:
        obj = self.aclx_to_tool_obj(text)
        if pretty:
            return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)
        return json.dumps(obj, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    def tool_obj_to_aclx(self, data: dict[str, Any]) -> str:
        return self.codec.encode(self.tool_obj_to_frame(data))

    def tool_json_to_aclx(self, text: str) -> str:
        return self.tool_obj_to_aclx(json.loads(text))

    def frame_to_tool_obj(self, frame: MsgFrame) -> dict[str, Any]:
        obj: dict[str, Any] = {
            TOOL_FRAME_KEYS["mode"]: frame.mode,
            TOOL_FRAME_KEYS["pack_ref"]: frame.pack_ref,
            TOOL_FRAME_KEYS["version"]: frame.version,
        }
        if frame.session_aliases:
            obj[TOOL_FRAME_KEYS["session_aliases"]] = {
                alias: self._value_to_tool_obj(value)
                for alias, value in frame.session_aliases.items()
            }
        if frame.nodes:
            obj[TOOL_FRAME_KEYS["nodes"]] = [
                {
                    NODE_KEYS["ref"]: node.ref,
                    NODE_KEYS["kind"]: node.kind,
                    NODE_KEYS["symbol"]: self.pack.encode_symbol(node.symbol),
                    NODE_KEYS["attrs"]: {
                        key: self._value_to_tool_obj(value)
                        for key, value in node.attrs.items()
                    },
                }
                for node in frame.nodes
            ]
        if frame.escapes:
            obj[TOOL_FRAME_KEYS["escapes"]] = [
                {
                    ESCAPE_KEYS["ref"]: escape.ref,
                    ESCAPE_KEYS["kind"]: escape.kind,
                    ESCAPE_KEYS["payload"]: self._value_to_tool_obj(escape.payload),
                    **(
                        {ESCAPE_KEYS["mime"]: self._value_to_tool_obj(escape.mime)}
                        if escape.mime is not None
                        else {}
                    ),
                }
                for escape in frame.escapes
            ]
        if frame.body:
            obj[TOOL_FRAME_KEYS["body"]] = [
                {
                    CLAUSE_KEYS["ref"]: clause.ref,
                    CLAUSE_KEYS["slots"]: {
                        SLOT_CODES.get(key, key): self._value_to_tool_obj(value)
                        for key, value in clause.slots.items()
                    },
                    **(
                        {
                            CLAUSE_KEYS["mods"]: {
                                MOD_TAG_CODES.get(mod.key, mod.key): self._value_to_tool_obj(mod.value)
                                for mod in clause.mods
                            }
                        }
                        if clause.mods
                        else {}
                    ),
                }
                for clause in frame.body
            ]
        if frame.deltas:
            obj[TOOL_FRAME_KEYS["deltas"]] = [
                {
                    DELTA_KEYS["target"]: self._value_to_tool_obj(delta.target),
                    DELTA_KEYS["slots"]: {
                        SLOT_CODES.get(key, key): self._value_to_tool_obj(value)
                        for key, value in delta.slots.items()
                    },
                }
                for delta in frame.deltas
            ]
        if frame.constraints:
            obj[TOOL_FRAME_KEYS["constraints"]] = [
                self._value_to_tool_obj(value) for value in frame.constraints
            ]
        if frame.proofs:
            obj[TOOL_FRAME_KEYS["proofs"]] = [
                self._value_to_tool_obj(value) for value in frame.proofs
            ]
        if frame.metadata:
            obj[TOOL_FRAME_KEYS["metadata"]] = {
                META_CODES.get(key, key): self._value_to_tool_obj(value)
                for key, value in frame.metadata.items()
            }
        if frame.checksum:
            obj[TOOL_FRAME_KEYS["checksum"]] = frame.checksum
        return obj

    def tool_obj_to_frame(self, data: dict[str, Any]) -> MsgFrame:
        mode = data.get(TOOL_FRAME_KEYS["mode"], "c")
        frame_type = ThoughtFrame if mode == "t" else MsgFrame
        frame = frame_type(
            mode=mode,
            pack_ref=data.get(TOOL_FRAME_KEYS["pack_ref"], "c0"),
            version=data.get(TOOL_FRAME_KEYS["version"], "1"),
        )

        aliases = data.get(TOOL_FRAME_KEYS["session_aliases"], {})
        frame.session_aliases = {
            alias: self._tool_obj_to_value(value)
            for alias, value in aliases.items()
        }

        for node in data.get(TOOL_FRAME_KEYS["nodes"], []):
            frame.nodes.append(
                SemanticNode(
                    ref=node[NODE_KEYS["ref"]],
                    kind=node.get(NODE_KEYS["kind"], "E"),
                    symbol=self.codec.parse_symbol(node[NODE_KEYS["symbol"]]),
                    attrs={
                        key: self._tool_obj_to_value(value)
                        for key, value in node.get(NODE_KEYS["attrs"], {}).items()
                    },
                )
            )

        for escape in data.get(TOOL_FRAME_KEYS["escapes"], []):
            frame.escapes.append(
                EscapeBlock(
                    ref=escape[ESCAPE_KEYS["ref"]],
                    kind=escape.get(ESCAPE_KEYS["kind"], "raw"),
                    payload=self._tool_obj_to_value(escape.get(ESCAPE_KEYS["payload"], "")),
                    mime=self._tool_obj_to_value(escape[ESCAPE_KEYS["mime"]])
                    if ESCAPE_KEYS["mime"] in escape
                    else None,
                )
            )

        for clause in data.get(TOOL_FRAME_KEYS["body"], []):
            frame.body.append(
                Clause(
                    ref=clause[CLAUSE_KEYS["ref"]],
                    slots={
                        SLOT_NAMES.get(key, key): self._tool_obj_to_value(value)
                        for key, value in clause.get(CLAUSE_KEYS["slots"], {}).items()
                    },
                    mods=[
                        ModTag(
                            key=MOD_TAG_NAMES.get(key, key),
                            value=self._tool_obj_to_value(value),
                        )
                        for key, value in clause.get(CLAUSE_KEYS["mods"], {}).items()
                    ],
                )
            )

        for delta in data.get(TOOL_FRAME_KEYS["deltas"], []):
            frame.deltas.append(
                DeltaPatch(
                    target=self._tool_obj_to_value(delta[DELTA_KEYS["target"]]),
                    slots={
                        SLOT_NAMES.get(key, key): self._tool_obj_to_value(value)
                        for key, value in delta.get(DELTA_KEYS["slots"], {}).items()
                    },
                )
            )

        frame.constraints = [
            self._tool_obj_to_value(value)
            for value in data.get(TOOL_FRAME_KEYS["constraints"], [])
        ]
        frame.proofs = [
            self._tool_obj_to_value(value)
            for value in data.get(TOOL_FRAME_KEYS["proofs"], [])
        ]
        frame.metadata = {
            META_NAMES.get(key, key): self._tool_obj_to_value(value)
            for key, value in data.get(TOOL_FRAME_KEYS["metadata"], {}).items()
        }
        frame.checksum = data.get(TOOL_FRAME_KEYS["checksum"])
        return frame

    def frame_to_handoff_obj(self, frame: MsgFrame) -> dict[str, Any]:
        body = frame.body
        result = {
            HANDOFF_KEYS["goal"]: self._clause_contexts(frame, body, action="plan", status="goal"),
            HANDOFF_KEYS["completed"]: self._clause_contexts(frame, body, status="done"),
            HANDOFF_KEYS["current_state"]: self._clause_contexts(frame, body, object_name="state"),
            HANDOFF_KEYS["risks"]: self._clause_contexts(frame, body, status="blocked"),
            HANDOFF_KEYS["next_actions"]: self._clause_contexts(frame, body, object_name="task", action="update"),
            HANDOFF_KEYS["evidence"]: [self.transcoder._resolve_value(frame, value) for value in frame.proofs],
            HANDOFF_KEYS["priority"]: frame.metadata.get("priority"),
            HANDOFF_KEYS["certainty"]: frame.metadata.get("certainty"),
        }
        return {key: value for key, value in result.items() if value not in (None, [], "")}

    def handoff_obj_to_frame(self, data: dict[str, Any], *, mode: str = "c") -> MsgFrame:
        data = self._normalize_handoff_obj(data)
        frame_type = ThoughtFrame if mode == "t" else MsgFrame
        frame = frame_type(mode=mode, pack_ref=self.pack.pack_id, version=self.pack.version)
        if "priority" in data:
            frame.metadata["priority"] = data["priority"]
        if "certainty" in data:
            frame.metadata["certainty"] = data["certainty"]
        if "scope" in data:
            frame.metadata["scope"] = data["scope"]
        if "source" in data:
            frame.metadata["source"] = data["source"]

        counter = 1
        for goal in ensure_list(data.get("goal")):
            context = self._attach_escape(frame, counter, goal)
            frame.body.append(
                Clause(
                    ref=str(counter),
                    slots={
                        "actor": SymbolRef("E", "agent"),
                        "action": SymbolRef("A", "plan"),
                        "object": SymbolRef("E", "task"),
                        "context": context,
                        "status": SymbolRef("Q", "goal"),
                    },
                )
            )
            counter += 1

        for item in ensure_list(data.get("completed")):
            context = self._attach_escape(frame, counter, item)
            frame.body.append(
                Clause(
                    ref=str(counter),
                    slots={
                        "actor": SymbolRef("E", "agent"),
                        "action": SymbolRef("A", "report"),
                        "object": SymbolRef("E", "result"),
                        "context": context,
                        "status": SymbolRef("Q", "done"),
                    },
                )
            )
            counter += 1

        for item in ensure_list(data.get("current_state")):
            context = self._attach_escape(frame, counter, item)
            frame.body.append(
                Clause(
                    ref=str(counter),
                    slots={
                        "actor": SymbolRef("E", "agent"),
                        "action": SymbolRef("A", "update"),
                        "object": SymbolRef("E", "state"),
                        "context": context,
                    },
                )
            )
            counter += 1

        for item in ensure_list(data.get("risks")):
            context = self._attach_escape(frame, counter, item)
            frame.body.append(
                Clause(
                    ref=str(counter),
                    slots={
                        "actor": SymbolRef("E", "agent"),
                        "action": SymbolRef("A", "explain"),
                        "object": SymbolRef("E", "error"),
                        "context": context,
                        "status": SymbolRef("Q", "blocked"),
                    },
                )
            )
            counter += 1

        for item in ensure_list(data.get("next_actions")):
            context = self._attach_escape(frame, counter, item)
            frame.body.append(
                Clause(
                    ref=str(counter),
                    slots={
                        "actor": SymbolRef("E", "agent"),
                        "action": SymbolRef("A", "update"),
                        "object": SymbolRef("E", "task"),
                        "context": context,
                        "status": SymbolRef("Q", "open"),
                    },
                )
            )
            counter += 1

        for item in ensure_list(data.get("evidence")):
            if isinstance(item, str) and not item:
                continue
            if isinstance(item, str) and len(item) > 24:
                context = self._attach_escape(frame, counter, item)
                frame.proofs.append(context)
                counter += 1
            else:
                frame.proofs.append(item)

        return frame

    def handoff_obj_to_aclx(self, data: dict[str, Any], *, mode: str = "c") -> str:
        return self.codec.encode(self.handoff_obj_to_frame(data, mode=mode))

    def handoff_json_to_aclx(self, text: str, *, mode: str = "c") -> str:
        return self.handoff_obj_to_aclx(json.loads(text), mode=mode)

    def aclx_to_handoff_json(self, text: str, *, pretty: bool = False) -> str:
        handoff = self.frame_to_handoff_obj(self.codec.decode(text))
        if pretty:
            return json.dumps(handoff, ensure_ascii=True, indent=2, sort_keys=True)
        return json.dumps(handoff, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    def adapter_benchmark(self, iterations: int = 1000) -> list[dict[str, Any]]:
        samples = [
            self.transcoder.nl_to_aclx("Plan the task and report the result."),
            self.handoff_obj_to_aclx(
                {
                    "goal": "Continue ACL-X adapter work.",
                    "completed": ["Implemented codec and transcoder."],
                    "current_state": "Adapters are being added.",
                    "risks": ["Coverage is still limited."],
                    "next_actions": ["Implement tool JSON adapter.", "Add benchmarks."],
                    "evidence": ["tests passing"],
                    "priority": 1,
                    "certainty": 0.9,
                }
            ),
        ]
        rows = []
        for index, sample in enumerate(samples, start=1):
            start = perf_counter()
            for _ in range(iterations):
                tool_obj = self.aclx_to_tool_obj(sample)
                self.tool_obj_to_aclx(tool_obj)
            elapsed_ms = (perf_counter() - start) * 1000
            rows.append(
                {
                    "sample": f"s{index}",
                    "iterations": iterations,
                    "avg_ms": round(elapsed_ms / iterations, 6),
                    "aclx_chars": len(sample),
                    "tool_json_chars": len(self.aclx_to_tool_json(sample)),
                }
            )
        return rows

    def _value_to_tool_obj(self, value: Any) -> Any:
        if isinstance(value, SymbolRef):
            return self.pack.encode_symbol(value)
        if isinstance(value, NodeRef):
            return f"%{value.value}"
        if isinstance(value, FrameRef):
            return f"${value.value}"
        if isinstance(value, AliasRef):
            return f"@{value.value}"
        if isinstance(value, EscapeRef):
            return f"!{value.value}"
        if isinstance(value, list):
            return [self._value_to_tool_obj(item) for item in value]
        if isinstance(value, dict):
            return {key: self._value_to_tool_obj(item) for key, item in value.items()}
        return value

    def _tool_obj_to_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.codec.parse_value(value)
        if isinstance(value, list):
            return [self._tool_obj_to_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._tool_obj_to_value(item) for key, item in value.items()}
        return value

    def _attach_escape(self, frame: MsgFrame, counter: int, value: Any) -> Any:
        if isinstance(value, str) and self._is_short_atom(value):
            return value
        ref = str(counter)
        mime = "text/plain" if isinstance(value, str) else "application/json"
        frame.escapes.append(EscapeBlock(ref=ref, kind="raw", payload=value, mime=mime))
        return EscapeRef(ref)

    def _is_short_atom(self, value: str) -> bool:
        return len(value) <= 24 and all(ch.isalnum() or ch in "._:-/" for ch in value)

    def _clause_contexts(
        self,
        frame: MsgFrame,
        clauses: list[Clause],
        *,
        action: str | None = None,
        status: str | None = None,
        object_name: str | None = None,
    ) -> list[str]:
        values = []
        for clause in clauses:
            if action is not None and not self._slot_matches(clause.slots.get("action"), "A", action):
                continue
            if status is not None and not self._slot_matches(clause.slots.get("status"), "Q", status):
                continue
            if object_name is not None and not self._slot_matches(clause.slots.get("object"), "E", object_name):
                continue
            context = clause.slots.get("context")
            if context is None:
                values.append(self.transcoder.frame_to_gloss(MsgFrame(body=[clause])))
            else:
                values.append(self.transcoder._resolve_value(frame, context))
        return values

    def _slot_matches(self, value: Any, kind: str, name: str) -> bool:
        return isinstance(value, SymbolRef) and value.kind == kind and value.name == name

    def _normalize_handoff_obj(self, data: dict[str, Any]) -> dict[str, Any]:
        normalized = {}
        for key, value in data.items():
            normalized[HANDOFF_NAMES.get(key, key)] = value
        return normalized


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
