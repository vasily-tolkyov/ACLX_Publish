from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Scalar = str | int | float | bool | None
StructuredValue = Scalar | list["StructuredValue"] | dict[str, "StructuredValue"]
Value = Any


@dataclass(frozen=True, slots=True)
class SymbolRef:
    kind: str
    name: str


@dataclass(frozen=True, slots=True)
class NodeRef:
    value: str


@dataclass(frozen=True, slots=True)
class FrameRef:
    value: str


@dataclass(frozen=True, slots=True)
class AliasRef:
    value: str


@dataclass(frozen=True, slots=True)
class EscapeRef:
    value: str


@dataclass(frozen=True, slots=True)
class ModTag:
    key: str
    value: StructuredValue = True


@dataclass(slots=True)
class EscapeBlock:
    ref: str
    kind: str = "raw"
    payload: StructuredValue = ""
    mime: str | None = None


@dataclass(slots=True)
class SemanticNode:
    ref: str
    kind: str
    symbol: SymbolRef
    attrs: dict[str, Value] = field(default_factory=dict)


@dataclass(slots=True)
class Clause:
    ref: str
    slots: dict[str, Value] = field(default_factory=dict)
    mods: list[ModTag] = field(default_factory=list)


@dataclass(slots=True)
class DeltaPatch:
    target: Value
    slots: dict[str, Value] = field(default_factory=dict)


@dataclass(slots=True)
class OntologyPack:
    pack_id: str
    version: str
    symbol_table: dict[str, dict[str, str]]
    defaults: dict[str, StructuredValue] = field(default_factory=dict)
    labels: dict[str, dict[str, str]] = field(default_factory=dict)
    reverse_symbol_table: dict[str, dict[str, str]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.reverse_symbol_table = {
            kind: {code: name for name, code in table.items()}
            for kind, table in self.symbol_table.items()
        }

    def encode_symbol(self, symbol: SymbolRef) -> str:
        table = self.symbol_table.get(symbol.kind)
        if table is None:
            raise KeyError(f"Unknown symbol kind: {symbol.kind}")
        try:
            code = table[symbol.name]
        except KeyError as exc:
            raise KeyError(f"Unknown symbol name {symbol.kind}:{symbol.name}") from exc
        return f"{symbol.kind}.{code}"

    def decode_symbol(self, kind: str, code: str) -> SymbolRef:
        table = self.reverse_symbol_table.get(kind)
        if table is None:
            raise KeyError(f"Unknown symbol kind: {kind}")
        try:
            name = table[code]
        except KeyError as exc:
            raise KeyError(f"Unknown symbol code {kind}.{code}") from exc
        return SymbolRef(kind=kind, name=name)

    def label_for_symbol(self, symbol: SymbolRef) -> str:
        table = self.labels.get(symbol.kind, {})
        return table.get(symbol.name, symbol.name)


@dataclass(slots=True)
class MsgFrame:
    mode: str = "c"
    pack_ref: str = "c0"
    version: str = "1"
    session_aliases: dict[str, Value] = field(default_factory=dict)
    nodes: list[SemanticNode] = field(default_factory=list)
    escapes: list[EscapeBlock] = field(default_factory=list)
    body: list[Clause] = field(default_factory=list)
    deltas: list[DeltaPatch] = field(default_factory=list)
    constraints: list[Value] = field(default_factory=list)
    proofs: list[Value] = field(default_factory=list)
    metadata: dict[str, Value] = field(default_factory=dict)
    checksum: str | None = None


@dataclass(slots=True)
class ThoughtFrame(MsgFrame):
    mode: str = "t"
