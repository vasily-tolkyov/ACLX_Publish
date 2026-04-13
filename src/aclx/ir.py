from __future__ import annotations

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


def value_to_data(value):
    if isinstance(value, SymbolRef):
        return {"type": "symbol", "kind": value.kind, "name": value.name}
    if isinstance(value, NodeRef):
        return {"type": "node_ref", "value": value.value}
    if isinstance(value, FrameRef):
        return {"type": "frame_ref", "value": value.value}
    if isinstance(value, AliasRef):
        return {"type": "alias_ref", "value": value.value}
    if isinstance(value, EscapeRef):
        return {"type": "escape_ref", "value": value.value}
    if isinstance(value, list):
        return [value_to_data(item) for item in value]
    if isinstance(value, dict):
        return {key: value_to_data(item) for key, item in value.items()}
    return value


def value_from_data(data):
    if isinstance(data, dict) and data.get("type") == "symbol":
        return SymbolRef(kind=data["kind"], name=data["name"])
    if isinstance(data, dict) and data.get("type") == "node_ref":
        return NodeRef(value=data["value"])
    if isinstance(data, dict) and data.get("type") == "frame_ref":
        return FrameRef(value=data["value"])
    if isinstance(data, dict) and data.get("type") == "alias_ref":
        return AliasRef(value=data["value"])
    if isinstance(data, dict) and data.get("type") == "escape_ref":
        return EscapeRef(value=data["value"])
    if isinstance(data, list):
        return [value_from_data(item) for item in data]
    if isinstance(data, dict):
        return {key: value_from_data(item) for key, item in data.items()}
    return data


def frame_to_dict(frame: MsgFrame) -> dict:
    return {
        "mode": frame.mode,
        "pack_ref": frame.pack_ref,
        "version": frame.version,
        "session_aliases": {key: value_to_data(value) for key, value in frame.session_aliases.items()},
        "nodes": [
            {
                "ref": node.ref,
                "kind": node.kind,
                "symbol": value_to_data(node.symbol),
                "attrs": {key: value_to_data(value) for key, value in node.attrs.items()},
            }
            for node in frame.nodes
        ],
        "escapes": [
            {
                "ref": escape.ref,
                "kind": escape.kind,
                "payload": value_to_data(escape.payload),
                "mime": escape.mime,
            }
            for escape in frame.escapes
        ],
        "body": [
            {
                "ref": clause.ref,
                "slots": {key: value_to_data(value) for key, value in clause.slots.items()},
                "mods": [{"key": mod.key, "value": value_to_data(mod.value)} for mod in clause.mods],
            }
            for clause in frame.body
        ],
        "deltas": [
            {
                "target": value_to_data(delta.target),
                "slots": {key: value_to_data(value) for key, value in delta.slots.items()},
            }
            for delta in frame.deltas
        ],
        "constraints": [value_to_data(value) for value in frame.constraints],
        "proofs": [value_to_data(value) for value in frame.proofs],
        "metadata": {key: value_to_data(value) for key, value in frame.metadata.items()},
        "checksum": frame.checksum,
    }


def frame_from_dict(data: dict) -> MsgFrame:
    frame_type = ThoughtFrame if data.get("mode") == "t" else MsgFrame
    frame = frame_type(
        mode=data.get("mode", "c"),
        pack_ref=data.get("pack_ref", "c0"),
        version=data.get("version", "1"),
        session_aliases={key: value_from_data(value) for key, value in data.get("session_aliases", {}).items()},
        nodes=[
            SemanticNode(
                ref=node["ref"],
                kind=node.get("kind", "E"),
                symbol=value_from_data(node["symbol"]),
                attrs={key: value_from_data(value) for key, value in node.get("attrs", {}).items()},
            )
            for node in data.get("nodes", [])
        ],
        escapes=[
            EscapeBlock(
                ref=escape["ref"],
                kind=escape.get("kind", "raw"),
                payload=value_from_data(escape.get("payload", "")),
                mime=escape.get("mime"),
            )
            for escape in data.get("escapes", [])
        ],
        body=[
            Clause(
                ref=clause["ref"],
                slots={key: value_from_data(value) for key, value in clause.get("slots", {}).items()},
                mods=[ModTag(key=mod["key"], value=value_from_data(mod.get("value", True))) for mod in clause.get("mods", [])],
            )
            for clause in data.get("body", [])
        ],
        deltas=[
            DeltaPatch(
                target=value_from_data(delta["target"]),
                slots={key: value_from_data(value) for key, value in delta.get("slots", {}).items()},
            )
            for delta in data.get("deltas", [])
        ],
        constraints=[value_from_data(value) for value in data.get("constraints", [])],
        proofs=[value_from_data(value) for value in data.get("proofs", [])],
        metadata={key: value_from_data(value) for key, value in data.get("metadata", {}).items()},
        checksum=data.get("checksum"),
    )
    return frame
