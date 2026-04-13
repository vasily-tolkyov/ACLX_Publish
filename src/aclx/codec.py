from __future__ import annotations

import hashlib
import json
import re

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
from .ontology import META_CODES, META_NAMES, MOD_TAG_CODES, MOD_TAG_NAMES, SLOT_CODES, SLOT_NAMES, get_pack

NUMBER_RE = re.compile(r"^-?(?:\d+(?:\.\d+)?|\.\d+)$")
SYMBOL_RE = re.compile(r"^([ERAQXL])\.([A-Za-z0-9]+)$")
ATOM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:/-]*$")


class ACLXCodec:
    def __init__(self, pack=None):
        self.pack = pack or get_pack("c0", "1")

    def encode(self, frame: MsgFrame) -> str:
        records: list[str] = [f"h|{frame.mode}|{frame.pack_ref}|{frame.version}"]

        for alias, value in sorted(frame.session_aliases.items()):
            records.append(f"a|{alias}|{self.serialize_value(value)}")

        for node in frame.nodes:
            attrs = self.serialize_pairs(node.attrs) if node.attrs else ""
            parts = [f"n|%{node.ref}|{self.pack.encode_symbol(node.symbol)}"]
            if attrs:
                parts.append(attrs)
            records.append("|".join(parts))

        for escape in frame.escapes:
            payload = self.serialize_value(escape.payload)
            parts = [f"e|!{escape.ref}|{escape.kind}|{payload}"]
            if escape.mime is not None:
                parts.append(self.serialize_value(escape.mime))
            records.append("|".join(parts))

        for clause in frame.body:
            slot_pairs = self.serialize_pairs(clause.slots, key_codes=SLOT_CODES)
            mod_pairs = self.serialize_mods(clause.mods)
            parts = [f"f|${clause.ref}", slot_pairs]
            if mod_pairs:
                parts.append(mod_pairs)
            records.append("|".join(parts))

        for delta in frame.deltas:
            slot_pairs = self.serialize_pairs(delta.slots, key_codes=SLOT_CODES)
            records.append(f"d|{self.serialize_value(delta.target)}|{slot_pairs}")

        for value in frame.constraints:
            records.append(f"r|{self.serialize_value(value)}")

        for value in frame.proofs:
            records.append(f"p|{self.serialize_value(value)}")

        metadata = self.expand_metadata(frame)
        if metadata:
            records.append(f"m|{self.serialize_pairs(metadata, key_codes=META_CODES)}")

        payload = "~".join(records)
        if frame.mode == "c":
            checksum = self.checksum(payload)
            records.append(f"k|{checksum}")
        return "~".join(records)

    def decode(self, text: str) -> MsgFrame:
        if not text:
            raise ValueError("ACL-X payload is empty")

        raw_records = split_top_level(text, "~")
        header_fields = split_top_level(raw_records[0], "|")
        if len(header_fields) != 4 or header_fields[0] != "h":
            raise ValueError("ACL-X payload is missing a valid header")

        _, mode, pack_id, version = header_fields
        self.pack = get_pack(pack_id, version)
        frame_type = ThoughtFrame if mode == "t" else MsgFrame
        frame = frame_type(mode=mode, pack_ref=pack_id, version=version)

        checksum_seen = None
        payload_without_checksum = []

        for record in raw_records:
            fields = split_top_level(record, "|")
            tag = fields[0]
            if tag != "k":
                payload_without_checksum.append(record)
            if tag == "h":
                continue
            if tag == "a":
                if len(fields) != 3:
                    raise ValueError(f"Invalid alias record: {record}")
                frame.session_aliases[fields[1]] = self.parse_value(fields[2])
            elif tag == "n":
                if len(fields) not in {3, 4}:
                    raise ValueError(f"Invalid node record: {record}")
                frame.nodes.append(
                    SemanticNode(
                        ref=fields[1][1:] if fields[1].startswith("%") else fields[1],
                        kind=fields[2].split(".", 1)[0],
                        symbol=self.parse_symbol(fields[2]),
                        attrs=self.parse_pairs(fields[3]) if len(fields) == 4 else {},
                    )
                )
            elif tag == "e":
                if len(fields) not in {4, 5}:
                    raise ValueError(f"Invalid escape record: {record}")
                frame.escapes.append(
                    EscapeBlock(
                        ref=fields[1][1:] if fields[1].startswith("!") else fields[1],
                        kind=fields[2],
                        payload=self.parse_value(fields[3]),
                        mime=self.parse_value(fields[4]) if len(fields) == 5 else None,
                    )
                )
            elif tag == "f":
                if len(fields) not in {2, 3, 4}:
                    raise ValueError(f"Invalid clause record: {record}")
                slots = self.parse_pairs(fields[2], key_names=SLOT_NAMES) if len(fields) >= 3 and fields[2] else {}
                mods = self.parse_mods(fields[3]) if len(fields) == 4 else []
                frame.body.append(
                    Clause(
                        ref=fields[1][1:] if fields[1].startswith("$") else fields[1],
                        slots=slots,
                        mods=mods,
                    )
                )
            elif tag == "d":
                if len(fields) != 3:
                    raise ValueError(f"Invalid delta record: {record}")
                frame.deltas.append(
                    DeltaPatch(
                        target=self.parse_value(fields[1]),
                        slots=self.parse_pairs(fields[2], key_names=SLOT_NAMES),
                    )
                )
            elif tag == "r":
                if len(fields) != 2:
                    raise ValueError(f"Invalid constraint record: {record}")
                frame.constraints.append(self.parse_value(fields[1]))
            elif tag == "p":
                if len(fields) != 2:
                    raise ValueError(f"Invalid proof record: {record}")
                frame.proofs.append(self.parse_value(fields[1]))
            elif tag == "m":
                if len(fields) != 2:
                    raise ValueError(f"Invalid metadata record: {record}")
                frame.metadata = self.parse_pairs(fields[1], key_names=META_NAMES)
            elif tag == "k":
                if len(fields) != 2:
                    raise ValueError(f"Invalid checksum record: {record}")
                checksum_seen = fields[1]
            else:
                raise ValueError(f"Unknown record tag: {tag}")

        if mode == "c":
            if checksum_seen is None:
                raise ValueError("C-layer payload is missing a checksum")
            expected = self.checksum("~".join(payload_without_checksum))
            if checksum_seen != expected:
                raise ValueError(f"Checksum mismatch: expected {expected}, got {checksum_seen}")
            frame.checksum = checksum_seen
        else:
            frame.checksum = checksum_seen
        return frame

    def expand_metadata(self, frame: MsgFrame) -> dict:
        if frame.mode == "c":
            return dict(frame.metadata)
        compact = dict(frame.metadata)
        for key, default in self.pack.defaults.get("metadata", {}).items():
            if compact.get(key) == default:
                compact.pop(key)
        return compact

    def serialize_pairs(self, mapping: dict, key_codes: dict[str, str] | None = None) -> str:
        if not mapping:
            return ""
        pieces = []
        for key, value in self._ordered_items(mapping, key_codes):
            encoded_key = key_codes.get(key, key) if key_codes else key
            pieces.append(f"{encoded_key}={self.serialize_value(value)}")
        return ";".join(pieces)

    def parse_pairs(self, text: str, key_names: dict[str, str] | None = None) -> dict:
        if not text:
            return {}
        result = {}
        for pair in split_top_level(text, ";"):
            if not pair:
                continue
            pieces = split_top_level(pair, "=")
            if len(pieces) != 2:
                raise ValueError(f"Invalid pair: {pair}")
            key = key_names.get(pieces[0], pieces[0]) if key_names else pieces[0]
            result[key] = self.parse_value(pieces[1])
        return result

    def serialize_mods(self, mods: list[ModTag]) -> str:
        if not mods:
            return ""
        pieces = []
        for mod in mods:
            code = MOD_TAG_CODES.get(mod.key, mod.key)
            pieces.append(f"{code}={self.serialize_value(mod.value)}")
        return ";".join(pieces)

    def parse_mods(self, text: str) -> list[ModTag]:
        if not text:
            return []
        mods = []
        for pair in split_top_level(text, ";"):
            if not pair:
                continue
            pieces = split_top_level(pair, "=")
            if len(pieces) != 2:
                raise ValueError(f"Invalid mod pair: {pair}")
            key = MOD_TAG_NAMES.get(pieces[0], pieces[0])
            mods.append(ModTag(key=key, value=self.parse_value(pieces[1])))
        return mods

    def serialize_value(self, value) -> str:
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
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            text = f"{value:.6g}"
            if text.startswith("0."):
                return text[1:]
            if text.startswith("-0."):
                return "-" + text[2:]
            return text
        if isinstance(value, str):
            if ATOM_RE.match(value):
                return value
            return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        raise TypeError(f"Unsupported ACL-X value: {value!r}")

    def parse_value(self, token: str):
        if not token:
            return ""
        symbol_match = SYMBOL_RE.match(token)
        if symbol_match:
            return self.parse_symbol(token)
        if token.startswith("%"):
            return NodeRef(token[1:])
        if token.startswith("$"):
            return FrameRef(token[1:])
        if token.startswith("@"):
            return AliasRef(token[1:])
        if token.startswith("!"):
            return EscapeRef(token[1:])
        if token == "true":
            return True
        if token == "false":
            return False
        if token == "null":
            return None
        if NUMBER_RE.match(token):
            if "." in token:
                return float(token)
            return int(token)
        if token[0] in '"[{':
            return json.loads(token)
        return token

    def parse_symbol(self, token: str) -> SymbolRef:
        match = SYMBOL_RE.match(token)
        if not match:
            raise ValueError(f"Invalid symbol token: {token}")
        kind, code = match.groups()
        return self.pack.decode_symbol(kind, code)

    @staticmethod
    def checksum(payload: str) -> str:
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]

    @staticmethod
    def _ordered_items(mapping: dict, key_codes: dict[str, str] | None = None):
        if key_codes:
            ordered = [key for key in key_codes if key in mapping]
            extras = sorted(key for key in mapping if key not in key_codes)
            keys = ordered + extras
        else:
            keys = list(mapping)
        for key in keys:
            yield key, mapping[key]


def split_top_level(text: str, delimiter: str) -> list[str]:
    if delimiter not in text:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escaping = False
    for char in text:
        if in_string:
            current.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            current.append(char)
            continue
        if char in "[{(":
            depth += 1
        elif char in "]})":
            depth = max(0, depth - 1)
        elif char == delimiter and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts
